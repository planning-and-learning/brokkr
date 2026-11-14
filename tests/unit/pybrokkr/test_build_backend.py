# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later

import base64
import csv
import hashlib
import io
import os
import shlex
import shutil
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from scikit_build_core import build as scikit_build

from pybrokkr import build_backend
from pybrokkr.build_backend import ProviderBackend


def _backend() -> ProviderBackend:
    return ProviderBackend(
        package="consumer",
        providers=("provider", "pyyggdrasil"),
        prefix_defines={"pyyggdrasil": "YGGDRASIL_NATIVE_PREFIX"},
        cmake_defines=("-DCONSUMER=ON",),
        extra_cmake_defines=lambda: ("-DEXTRA=ON",),
        jobs_env="CONSUMER_JOBS",
    )


def _fake_provider(name: str, prefix: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def native_prefix() -> Path:
        return prefix

    provider = types.ModuleType(name)
    monkeypatch.setattr(provider, "native_prefix", native_prefix, raising=False)
    monkeypatch.setitem(sys.modules, name, provider)


def _write_wheel(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, content in sorted(files.items()):
            wheel.writestr(name, content)


def _read_wheel(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as wheel:
        return {name: wheel.read(name).decode() for name in wheel.namelist() if not name.endswith("/")}


@pytest.mark.parametrize("provider_name", ["provider", "provider with spaces"])
def test_jobs_and_native_build_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider_name: str) -> None:
    backend = _backend()
    monkeypatch.delenv("CONSUMER_JOBS", raising=False)
    monkeypatch.setattr(os, "cpu_count", lambda: 4)
    assert backend.num_jobs() == 4
    monkeypatch.setenv("CONSUMER_JOBS", "6")
    assert backend.num_jobs() == 6

    provider_prefix = tmp_path / provider_name
    provider_library = provider_prefix / "lib"
    provider_library.mkdir(parents=True)
    yggdrasil_prefix = tmp_path / "yggdrasil"
    yggdrasil_library = yggdrasil_prefix / "lib64"
    yggdrasil_library.mkdir(parents=True)
    _fake_provider("provider", provider_prefix, monkeypatch)
    _fake_provider("pyyggdrasil", yggdrasil_prefix, monkeypatch)

    monkeypatch.setenv("CMAKE_ARGS", "-DUSER_OPTION=ON '-DUSER_PATH=/user path'")
    monkeypatch.delenv("CMAKE_BUILD_PARALLEL_LEVEL", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing/ld")
    monkeypatch.setenv("DYLD_LIBRARY_PATH", "/existing/dyld")

    backend.prepare_native_build()

    assert os.environ["CMAKE_BUILD_PARALLEL_LEVEL"] == "6"
    assert os.environ["LD_LIBRARY_PATH"] == os.pathsep.join(
        (str(provider_library), str(yggdrasil_library), "/existing/ld")
    )
    assert os.environ["DYLD_LIBRARY_PATH"] == os.pathsep.join(
        (str(provider_library), str(yggdrasil_library), "/existing/dyld")
    )
    assert shlex.split(os.environ["CMAKE_ARGS"]) == [
        f"-DCMAKE_PREFIX_PATH={provider_prefix.resolve()};{yggdrasil_prefix.resolve()}",
        f"-DYGGDRASIL_NATIVE_PREFIX={yggdrasil_prefix.resolve()}",
        f"-DPython_EXECUTABLE={sys.executable}",
        "-DCONSUMER=ON",
        "-DEXTRA=ON",
        "-DUSER_OPTION=ON",
        "-DUSER_PATH=/user path",
    ]


def test_num_jobs_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _backend()
    for value in ("0", "-1", "many"):
        monkeypatch.setenv("CONSUMER_JOBS", value)
        with pytest.raises(ValueError, match="positive integer"):
            backend.num_jobs()


@pytest.mark.parametrize("private_root", ["_consumer", "_consumer.cpython-313-x86_64-linux-gnu"])
@pytest.mark.parametrize("mode", ["wheel", "disabled_strip", "missing_strip", "editable"])
def test_default_stub_rewriting_and_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, private_root: str, mode: str
) -> None:
    backend = _backend()
    assert backend.rename_packages == ("consumer", "provider", "pyyggdrasil")
    assert ProviderBackend("consumer", ("pyyggdrasil",), rename_packages=()).rename_packages == ()

    wheel_path = tmp_path / "consumer-1.0.0-py3-none-any.whl"
    generated_stub = (
        "ref: consumer._consumer.api provider._provider pyyggdrasil._pyyggdrasil\n"
        "def load(path: os.PathLike, typed: os.PathLike[str]) -> None: ...\n"
    )
    native_library = "consumer/native/lib/libconsumer.so"
    _write_wheel(
        wheel_path,
        {
            "consumer/__init__.pyi": "from . import api as api\n",
            "consumer/api/__init__.py": "",
            "consumer/py.typed": "",
            f"consumer/{private_root}/__init__.pyi": "generated root must not replace public\n",
            f"consumer/{private_root}/api.pyi": generated_stub,
            native_library: "unstripped library\n",
            "consumer-1.0.0.dist-info/RECORD": "",
        },
    )

    def build(*_args: object) -> str:
        return wheel_path.name

    def strip_library(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        Path(command[-1]).write_bytes(b"stripped library\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(backend, "prepare_native_build", lambda: None)
    monkeypatch.setattr(scikit_build, "build_editable" if mode == "editable" else "build_wheel", build)
    monkeypatch.setenv("CONSUMER_STRIP_WHEEL", "OFF" if mode == "disabled_strip" else "ON")
    with (
        patch.object(shutil, "which", return_value=None if mode == "missing_strip" else "/fake/strip"),
        patch.object(zipfile.ZipFile, "extractall", autospec=True, side_effect=zipfile.ZipFile.extractall) as extract,
        patch.object(build_backend, "repack_wheel", wraps=build_backend.repack_wheel) as repack,
        patch.object(subprocess, "run", side_effect=strip_library) as strip,
    ):
        hook = backend.build_editable if mode == "editable" else backend.build_wheel
        assert hook(str(tmp_path)) == wheel_path.name
        assert extract.call_count == repack.call_count == 1
        assert strip.call_count == (1 if mode == "wheel" else 0)

    files = _read_wheel(wheel_path)
    public_stub = "consumer/api/__init__.pyi"
    assert files["consumer/__init__.pyi"] == "from . import api as api\n"
    assert files[public_stub] == (
        "ref: consumer.api provider pyyggdrasil\n"
        "def load(path: os.PathLike[str], typed: os.PathLike[str]) -> None: ...\n"
    )
    assert not any(name.startswith(f"consumer/{private_root}/") for name in files)
    assert files[native_library] == ("stripped library\n" if mode == "wheel" else "unstripped library\n")

    record_path = "consumer-1.0.0.dist-info/RECORD"
    record = {row[0]: row[1:] for row in csv.reader(io.StringIO(files[record_path]))}
    assert f"consumer/{private_root}/api.pyi" not in record
    for name in (public_stub, native_library):
        content = files[name].encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        assert record[name] == [f"sha256={digest}", str(len(content))]
    assert record["consumer/py.typed"][1] == "0"
    assert record[record_path] == ["", ""]


def test_is_disabled() -> None:
    for value in ("0", "false", "False", "OFF", "no"):
        assert build_backend.is_disabled(value)
    for value in ("1", "true", "ON", "yes", ""):
        assert not build_backend.is_disabled(value)


@pytest.mark.parametrize(
    ("name", "native"),
    [
        ("module.so", True),
        ("module.cpython-312-x86_64-linux-gnu.so", True),
        ("libtbb.so.12.16", True),
        ("module.dylib", True),
        ("module.pyd", True),
        ("module.dll", True),
        ("module.py", False),
        ("module.so.txt", False),
        ("module.so.", False),
        ("module.so.12a", False),
        ("module.so.12.16a", False),
    ],
)
def test_is_native_library(tmp_path: Path, name: str, native: bool) -> None:
    assert build_backend.is_native_library(tmp_path / name) is native


def test_rewrite_record_requires_exactly_one_record_file(tmp_path: Path) -> None:
    wheel_root = tmp_path / "wheel"
    wheel_root.mkdir()
    with pytest.raises(RuntimeError, match="expected exactly one RECORD file, found 0"):
        build_backend.repack_wheel(tmp_path / "x.whl", wheel_root)
    for name in ("first", "second"):
        (wheel_root / f"{name}.dist-info").mkdir()
        (wheel_root / f"{name}.dist-info" / "RECORD").write_text("")
    with pytest.raises(RuntimeError, match="expected exactly one RECORD file, found 2"):
        build_backend.repack_wheel(tmp_path / "x.whl", wheel_root)


def test_processing_keeps_executable_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wheel_path = tmp_path / "consumer-1.0.0-py3-none-any.whl"
    executable = zipfile.ZipInfo("consumer/bin/tool")
    executable.external_attr = 0o755 << 16
    with zipfile.ZipFile(wheel_path, "w") as wheel:
        wheel.writestr(executable, b"native executable")
        wheel.writestr("consumer-1.0.0.dist-info/RECORD", "")

    backend = ProviderBackend("consumer", (), fix_stubs=False, should_strip=lambda path: path.name == "tool")
    monkeypatch.setenv("CONSUMER_STRIP_WHEEL", "ON")
    monkeypatch.setattr(backend, "prepare_native_build", lambda: None)

    def build(*_args: object) -> str:
        return wheel_path.name

    monkeypatch.setattr(scikit_build, "build_wheel", build)
    with patch.object(shutil, "which", return_value="/fake/strip"), patch.object(subprocess, "run") as strip:
        assert backend.build_wheel(str(tmp_path)) == wheel_path.name
    strip.assert_called_once()
    with zipfile.ZipFile(wheel_path) as wheel:
        assert (wheel.getinfo(executable.filename).external_attr >> 16) & 0o777 == 0o755
