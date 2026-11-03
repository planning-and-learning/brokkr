# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""PEP 517 build backend for provider wheels: scikit-build-core with a shared pre-build setup and wheel post-processing.

A provider wheel ships a native library with its nanobind module and lets other wheels build against it (its
``native_prefix()``). A repo's backend module instantiates :class:`ProviderBackend` with its package, the providers it
builds against, and its options, then re-exports the hooks (``install_hooks(globals())``).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from scikit_build_core import build as scikit_build

# PEP 517 config_settings: keys map to a string or a list of strings.
ConfigSettings = dict[str, str | list[str]]


def is_disabled(value: str) -> bool:
    """Whether an environment switch's value (0, false, off, no) turns its feature off."""
    return value.upper() in {"0", "FALSE", "OFF", "NO"}


def _is_versioned_shared_object(name: str) -> bool:
    marker = ".so."
    if marker not in name:
        return False
    version = name.rsplit(marker, maxsplit=1)[1]
    return bool(version) and all(component.isdigit() for component in version.split("."))


def is_native_library(path: Path) -> bool:
    """Whether ``path`` is a shared library (a numerically versioned .so included), what a wheel strips by default."""
    name = path.name
    return name.endswith((".so", ".dylib", ".pyd", ".dll")) or _is_versioned_shared_object(name)


def _strip_args(*, unneeded: bool) -> list[str]:
    if platform.system() == "Darwin":
        return ["-x"]
    return ["--strip-unneeded" if unneeded else "--strip-debug"]


def _record_digest(path: Path) -> tuple[str, str]:
    content = path.read_bytes()
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}", str(len(content))


def _rewrite_record(wheel_root: Path) -> None:
    record_files = list(wheel_root.glob("*.dist-info/RECORD"))
    if len(record_files) != 1:
        msg = f"expected exactly one RECORD file, found {len(record_files)}"
        raise RuntimeError(msg)

    record_file = record_files[0]
    rows: list[tuple[str, str, str]] = []
    for path in sorted(wheel_root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(wheel_root).as_posix()
        if path == record_file:
            rows.append((relative_path, "", ""))
        else:
            digest, size = _record_digest(path)
            rows.append((relative_path, digest, size))

    with record_file.open("w", newline="") as out:
        csv.writer(out).writerows(rows)


def repack_wheel(wheel_path: Path, wheel_root: Path) -> None:
    """Rewrite the RECORD of the unpacked ``wheel_root`` and zip it back into ``wheel_path``."""
    _rewrite_record(wheel_root)
    replacement_path = wheel_path.with_suffix(".tmp")
    with zipfile.ZipFile(replacement_path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for path in sorted(wheel_root.rglob("*")):
            if path.is_file():
                wheel.write(path, path.relative_to(wheel_root).as_posix())
    replacement_path.replace(wheel_path)


def _native_library_dirs(native_prefixes: Sequence[Path]) -> list[Path]:
    return [path for prefix in native_prefixes for path in sorted(Path(prefix).glob("lib*")) if path.is_dir()]


def _prepend_env_paths(name: str, paths: Sequence[Path]) -> None:
    existing = os.environ.get(name, "")
    entries = [str(path) for path in paths]
    if existing:
        entries.append(existing)
    os.environ[name] = os.pathsep.join(entries)


def _prepend_cmake_args(*args: str) -> None:
    existing = shlex.split(os.environ.get("CMAKE_ARGS", ""))
    os.environ["CMAKE_ARGS"] = shlex.join([*args, *existing])


@dataclass
class ProviderBackend:
    """PEP 517 hooks for a provider wheel that consumes sibling provider wheels.

    Attributes:
        package: the python package the wheel ships (e.g. "pypddl").
        providers: provider packages whose native prefixes feed the build, in
            rpath order (e.g. ("pypddl", "pyyggdrasil") for pytyr); each has a
            ``native_prefix()``. Empty for a wheel that builds against none.
        prefix_defines: provider -> CMake variable set to its native prefix
            (e.g. {"pyyggdrasil": "YGGDRASIL_NATIVE_PREFIX"}).
        before_build: optional callable run first in every build (e.g. building
            the native dependencies into the prefix the wheel bundles).
        cmake_defines: static -D arguments prepended to CMAKE_ARGS.
        extra_cmake_defines: optional callable returning additional -D
            arguments, evaluated at build time (for env-dependent defines).
        rename_packages: packages whose private-module references are rewritten
            in the wheel's *.pyi stubs (<p>._<p> -> <p>). Defaults to the
            package and its providers.
        jobs_env / strip_env: environment variable names controlling build
            parallelism and wheel stripping.
        fix_stubs: whether the backend publishes the private module's stubs
            (off where CMake already does, brokkr_patch_python_stubs).
        should_strip / strip_unneeded: which files of the wheel are stripped,
            and whether of all unneeded symbols (else of debug information).
    """

    package: str
    providers: Sequence[str]
    _: KW_ONLY
    prefix_defines: Mapping[str, str] | None = None
    before_build: Callable[[], None] | None = None
    cmake_defines: Sequence[str] = ()
    extra_cmake_defines: Callable[[], Sequence[str]] | None = None
    rename_packages: Sequence[str] | None = None
    jobs_env: str = ""
    strip_env: str = ""
    fix_stubs: bool = True
    should_strip: Callable[[Path], bool] = is_native_library
    strip_unneeded: bool = False

    def __post_init__(self) -> None:
        """Check the providers and fill in the defaults that depend on the package."""
        self.providers = tuple(self.providers)
        self.prefix_defines = dict(self.prefix_defines or {})
        if unknown := set(self.prefix_defines) - set(self.providers):
            msg = f"prefix_defines names packages that are not providers: {sorted(unknown)}"
            raise ValueError(msg)
        self.cmake_defines = tuple(self.cmake_defines)
        if self.rename_packages is None:
            self.rename_packages = (self.package, *self.providers)
        self.jobs_env = self.jobs_env or f"{self.package.upper()}_JOBS"
        self.strip_env = self.strip_env or f"{self.package.upper()}_STRIP_WHEEL"

    # -- pre-build ---------------------------------------------------------

    def num_jobs(self) -> int:
        """The number of parallel build jobs: the jobs variable, else the CPU count."""
        raw_jobs = os.environ.get(self.jobs_env, str(os.cpu_count() or 1))
        try:
            jobs = int(raw_jobs)
        except ValueError as err:
            msg = f"{self.jobs_env} must be a positive integer"
            raise ValueError(msg) from err
        if jobs <= 0:
            msg = f"{self.jobs_env} must be a positive integer"
            raise ValueError(msg)
        return jobs

    def _native_prefixes(self) -> list[Path]:
        prefixes: list[Path] = []
        for provider in self.providers:
            module = importlib.import_module(provider)
            native_prefix: Callable[[], str] = module.native_prefix
            prefixes.append(Path(native_prefix()).resolve())
        return prefixes

    def prepare_native_build(self) -> None:
        """Run the pre-build hook, then point CMake and the loader at the providers' native prefixes."""
        if self.before_build is not None:
            self.before_build()
        native_prefixes = self._native_prefixes()
        native_library_dirs = _native_library_dirs(native_prefixes)

        os.environ.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", str(self.num_jobs()))
        if native_library_dirs:
            _prepend_env_paths("LD_LIBRARY_PATH", native_library_dirs)
            _prepend_env_paths("DYLD_LIBRARY_PATH", native_library_dirs)

        defines: list[str] = []
        if native_prefixes:
            defines.append(f"-DCMAKE_PREFIX_PATH={';'.join(str(prefix) for prefix in native_prefixes)}")
        prefix_of = dict(zip(self.providers, native_prefixes, strict=True))
        defines += [f"-D{variable}={prefix_of[provider]}" for provider, variable in (self.prefix_defines or {}).items()]
        defines += [f"-DPython_EXECUTABLE={sys.executable}", *self.cmake_defines]
        if self.extra_cmake_defines is not None:
            defines.extend(self.extra_cmake_defines())
        _prepend_cmake_args(*defines)

    # -- wheel post-processing ---------------------------------------------

    def _patch_stub_text(self, text: str) -> str:
        for rename_package in self.rename_packages or ():
            text = text.replace(f"{rename_package}._{rename_package}.", f"{rename_package}.")
            text = text.replace(f"{rename_package}._{rename_package}", rename_package)
        # nanobind stubgen emits bare `os.PathLike` for filesystem::path params; subscript it so
        # strict type checkers do not see PathLike[Unknown].
        return re.sub(r"os\.PathLike(?!\[)", "os.PathLike[str]", text)

    def _fix_stubs(self, wheel_root: Path) -> None:
        package_root = wheel_root / self.package

        def install_stub(path: Path, target: Path) -> None:
            package_dir = target.with_suffix("")
            if package_dir.is_dir():
                target = package_dir / "__init__.pyi"

            # Handwritten (or otherwise pre-existing) public stubs win over
            # generated ones, matching brokkr_patch_python_stubs.
            if target.exists():
                return

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._patch_stub_text(path.read_text(encoding="utf-8")), encoding="utf-8")

        private_stub_roots = sorted(
            path
            for path in package_root.glob(f"_{self.package}*")
            if path.is_dir() and (path.name == f"_{self.package}" or path.name.startswith(f"_{self.package}."))
        )
        for private_stub_root in private_stub_roots:
            for path in sorted(private_stub_root.rglob("*.pyi")):
                install_stub(path, package_root / path.relative_to(private_stub_root))
            shutil.rmtree(private_stub_root)

        for path in sorted(wheel_root.rglob("*.pyi")):
            path.write_text(self._patch_stub_text(path.read_text(encoding="utf-8")), encoding="utf-8")

    def _strip_native_libraries(self, wheel_root: Path) -> None:
        if is_disabled(os.environ.get(self.strip_env, "ON")):
            return

        strip = shutil.which("strip")
        if strip is None:
            return

        for path in wheel_root.rglob("*"):
            if path.is_file() and self.should_strip(path):
                subprocess.run(
                    [strip, *_strip_args(unneeded=self.strip_unneeded), str(path)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def _process_wheel(self, wheel_path: Path, *, strip: bool = True) -> None:
        if not self.fix_stubs and not strip:
            return
        with TemporaryDirectory(prefix=f"{self.package}-wheel-") as tmp:
            wheel_root = Path(tmp) / "wheel"
            with zipfile.ZipFile(wheel_path) as wheel:
                wheel.extractall(wheel_root)
                # extractall drops permissions: keep executables (bundled tools) executable.
                for info in wheel.infolist():
                    if mode := (info.external_attr >> 16) & 0o777:
                        (wheel_root / info.filename).chmod(mode)

            if self.fix_stubs:
                self._fix_stubs(wheel_root)
            if strip:
                self._strip_native_libraries(wheel_root)

            repack_wheel(wheel_path, wheel_root)

    # -- PEP 517 hooks -------------------------------------------------------

    def get_requires_for_build_wheel(self, config_settings: ConfigSettings | None = None) -> list[str]:
        """PEP 517 hook: scikit-build-core's build requirements for a wheel."""
        return scikit_build.get_requires_for_build_wheel(config_settings)

    def get_requires_for_build_editable(self, config_settings: ConfigSettings | None = None) -> list[str]:
        """PEP 517 hook: scikit-build-core's build requirements for an editable wheel."""
        return scikit_build.get_requires_for_build_editable(config_settings)

    def prepare_metadata_for_build_wheel(
        self, metadata_directory: str, config_settings: ConfigSettings | None = None
    ) -> str:
        """PEP 517 hook: the wheel's metadata, from scikit-build-core."""
        return scikit_build.prepare_metadata_for_build_wheel(metadata_directory, config_settings)

    def build_wheel(
        self,
        wheel_directory: str,
        config_settings: ConfigSettings | None = None,
        metadata_directory: str | None = None,
    ) -> str:
        """PEP 517 hook: build the wheel against the providers, then fix its stubs and strip it."""
        self.prepare_native_build()
        wheel_filename = scikit_build.build_wheel(wheel_directory, config_settings, metadata_directory)
        self._process_wheel(Path(wheel_directory) / wheel_filename)
        return wheel_filename

    def build_editable(
        self,
        wheel_directory: str,
        config_settings: ConfigSettings | None = None,
        metadata_directory: str | None = None,
    ) -> str:
        """PEP 517 hook: build an editable wheel against the providers."""
        self.prepare_native_build()
        wheel_filename = scikit_build.build_editable(wheel_directory, config_settings, metadata_directory)
        self._process_wheel(Path(wheel_directory) / wheel_filename, strip=False)
        return wheel_filename

    def build_sdist(self, sdist_directory: str, config_settings: ConfigSettings | None = None) -> str:
        """PEP 517 hook: the source distribution, from scikit-build-core."""
        return scikit_build.build_sdist(sdist_directory, config_settings)

    def install_hooks(self, namespace: dict[str, object]) -> None:
        """Export the PEP 517 hook functions into a backend module namespace."""
        namespace["get_requires_for_build_wheel"] = self.get_requires_for_build_wheel
        namespace["get_requires_for_build_editable"] = self.get_requires_for_build_editable
        namespace["prepare_metadata_for_build_wheel"] = self.prepare_metadata_for_build_wheel
        namespace["build_wheel"] = self.build_wheel
        namespace["build_editable"] = self.build_editable
        namespace["build_sdist"] = self.build_sdist
