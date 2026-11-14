# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""The directory layout of a repository, as docs/directory_layout.rst states it: each file allowed, each structure kept.

A tracked file (``git ls-files``, relative to the repository root) is allowed where one pattern of the layout matches it
whole. The rules about structure are checked beside the patterns:

- required files: every repository has the standard files (``REQUIRED``), a library those of its build too
  (``REQUIRED_OF_A_LIBRARY``);
- mirroring: a directory under ``tests/unit/``, under ``benchmarks/`` (other than ``support/``, ``suites/``,
  ``results/``, ``tools/``), or of the Python package that holds binding sources (or is a parent of one that does),
  names a component that exists under ``include/<lib>/`` or ``src/``;
- stub packages: every directory under ``typings/`` has an ``__init__.pyi``;
- unit tests refer to their component: a C++ test under ``tests/unit/<component>/`` includes a header of that
  component; a Python test (``test_*.py``) imports the component's module or a package that holds it;
- headers are included: a header under ``include/<lib>/<component>/`` is included by another tracked file.

    python -m pybrokkr.layout <repository>...

reports each finding as ``<repository>/<path>: <rule>``, then a summary per repository, and exits 1 where any is found.
A repository is a library where ``include/`` holds one directory, the library's name; without ``include/`` it is a
Python package under ``src/py<name>/``.
"""

import argparse
import collections
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pybrokkr.references import imports_of, included_paths, includes_of, normalized

NAME = r"[a-z0-9_]+"
DIRS = rf"(?:{NAME}/)*"
BENCHMARK_PARTS = ("support", "suites", "results", "tools")
DEPENDENCY = r"[A-Za-z0-9_]+"  # a vendored dependency, by its upstream name (oneTBB)
ROOT_FILES = (
    "pyproject.toml",
    "CMakeLists.txt",
    "Config.cmake.in",
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "Apptainer",
    "peachycheck.yml",
    "ruff.toml",
    "pyrightconfig.json",
    ".gitignore",
    ".gitattributes",
    ".clang-format",
    ".clang-tidy",
)
# What every repository has, and what a library (a repository with include/<lib>/) has besides.
REQUIRED = (
    "pyproject.toml",
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "peachycheck.yml",
    ".gitignore",
    "ruff.toml",
    "pyrightconfig.json",
    ".github/workflows/peachycheck.yml",
)
REQUIRED_OF_A_LIBRARY = ("CMakeLists.txt", "Config.cmake.in", ".clang-format", ".clang-tidy")
# The Python tests that build a module against the installed package, as a downstream library does: of no component.
DOWNSTREAM = "python/tests/downstream/"


def patterns(lib: str | None) -> list[tuple[str, re.Pattern[str]]]:
    """The layout's patterns by kind: those of every repository, then those of library `lib` or of a Python package."""
    n, d = NAME, DIRS
    listed = [
        (
            "root",
            "|".join(map(re.escape, ROOT_FILES)),
        ),
        ("ci", r"\.github/workflows/[a-z0-9_-]+\.yml"),
        ("directory files", rf"(?:{n}/)+(?:README\.md|\.clang-tidy)"),
        ("exe, examples", rf"(?:exe|examples|python/examples)/{d}(?:{n}\.(?:cpp|hpp|py)|CMakeLists\.txt)"),
        (
            "tests",
            rf"tests/(?:CMakeLists\.txt|__init__\.py|(?:rules|laws|tables|cost|unit|integration|support)/{d}(?:{n}\.(?:cpp|hpp|py)|CMakeLists\.txt))",
        ),
        ("test data", rf"tests/support/data/{d}[a-z0-9_.-]+"),
        ("test generators", rf"tests/support/generators/{d}{n}\.py"),
        (
            "docs",
            "|".join(
                [
                    rf"docs/{d}(?:[a-z0-9_-]+\.rst|conf\.py|requirements\.txt|[a-z0-9_-]+\.(?:svg|png))",
                    rf"docs/_ext/{n}\.py",
                    r"docs/[A-Z][A-Z0-9_]*\.md",
                ]
            ),
        ),
        ("LaTeX", r"docs/[a-z0-9_-]+/[a-z0-9_-]+\.(?:tex|bib|svg|png)"),
        (
            "benchmarks",
            "|".join(
                [
                    rf"benchmarks/(?:{d})?CMakeLists\.txt",
                    rf"benchmarks/(?!(?:{'|'.join(BENCHMARK_PARTS)})/){d}{n}\.cpp",
                    rf"benchmarks/support/(?:{n}\.(?:hpp|cpp)|{n}\.[a-z]+\.in)",
                    rf"benchmarks/suites/{n}\.json",
                    r"benchmarks/results/[A-Za-z0-9_.-]+\.json",
                    rf"benchmarks/tools/{n}\.py",
                ]
            ),
        ),
        ("experiments", rf"experiments/(?:README\.md|{n}\.(?:py|sh))|experiments/configs/{n}/{d}[a-z0-9_.-]+\.json"),
        ("typings", rf"typings/{n}/{d}(?:__init__|{n})\.pyi"),
    ]
    of_a_library = [
        ("include", rf"include/{lib}/{d}{n}\.hpp"),
        ("src", rf"src/{d}(?:{n}\.(?:cpp|hpp)|CMakeLists\.txt)"),
        ("python", rf"python/{n}_build_backend\.py|python/(?:src/)?CMakeLists\.txt|python/src/module\.cpp"),
        (
            "python package",
            rf"python/src/py{n}/{d}(?:{n}\.(?:cpp|hpp|py)|CMakeLists\.txt)|python/src/py{n}/(?:__init__\.pyi|py\.typed)",
        ),
        ("python tests", rf"python/tests/{d}(?:{n}\.(?:py|cpp)|CMakeLists\.txt|pyproject\.toml)"),
        (
            "native dependencies",
            "|".join(
                [
                    r"python/pyproject\.toml",
                    r"python/native/(?:CMakeLists\.txt|README\.md|LICENSE|CORRESPONDING_SOURCE\.md|SOURCES\.json|source_manifest\.cmake)",
                    rf"python/native/{DEPENDENCY}/(?:CMakeLists\.txt|{n}\.cmake|[a-z0-9_-]+\.patch)",
                    rf"python/native/{DEPENDENCY}/package/(?:CMakeLists\.txt|[A-Za-z0-9_]+Config\.cmake\.in)",
                    rf"python/native/{DEPENDENCY}/licenses/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+",
                ]
            ),
        ),
        ("share", rf"share/{lib}/{d}{n}\.json"),
        ("cmake", rf"cmake/{lib}_{n}\.cmake|cmake/{n}\.py"),
    ]
    # A repository that is one Python package: its modules, and the CMake modules it installs (brokkrConfig.cmake).
    of_a_package = [
        ("python-only package", rf"src/py{n}/{d}{n}\.py|src/py{n}/py\.typed|src/py{n}/cmake/[A-Za-z0-9_]+\.cmake"),
    ]
    listed += of_a_package if lib is None else of_a_library
    return [(kind, re.compile(pattern)) for kind, pattern in listed]


@dataclass(frozen=True)
class Finding:
    """A tracked path the layout does not allow, and the rule it breaks."""

    path: str
    rule: str


def tracked(repository: Path) -> list[str]:
    """The files git tracks in `repository`, relative to its root."""
    git = shutil.which("git")
    if git is None:
        msg = "pybrokkr.layout needs git on PATH"
        raise FileNotFoundError(msg)
    listed = subprocess.run([git, "-C", str(repository), "ls-files"], capture_output=True, text=True, check=True)
    return listed.stdout.splitlines()


def libraries(files: list[str]) -> list[str]:
    """The directories under include/: a library's repository has one, named as the library."""
    return sorted({match.group(1) for each in files if (match := re.match(r"include/([^/]+)/", each))})


def packages(files: list[str]) -> list[str]:
    """The Python packages: python/src/py<name>/ of a library, src/py<name>/ of a repository that is one package."""
    found = {match.group(1) for each in files if (match := re.match(rf"(?:python/)?src/(py{NAME})/", each))}
    return sorted(found)


def library_of(files: list[str]) -> str | None:
    """The library's name: the one directory under include/; none for a repository that is no library."""
    names = libraries(files)
    return names[0] if len(names) == 1 else None


def unidentified(files: list[str]) -> list[Finding]:
    """What keeps the repository from being a library or a Python package."""
    names = libraries(files)
    if len(names) > 1:
        return [Finding("include/", f"holds more than the library's directory: {', '.join(names)}")]
    if not names and not packages(files):
        return [Finding("", "holds no library (include/<lib>/) and no Python package (src/py<name>/)")]
    return []


def missing(files: list[str], lib: str | None) -> list[Finding]:
    """The required files that are not tracked."""
    present = set(files)
    required = REQUIRED + (REQUIRED_OF_A_LIBRARY if lib is not None else ())
    return [Finding(each, "required, missing") for each in required if each not in present]


def directories(files: list[str], root: str) -> set[str]:
    """Every directory under `root` that holds a tracked file, at any depth, relative to `root`."""
    found: set[str] = set()
    for each in files:
        if each.startswith(root):
            parts = PurePosixPath(each[len(root) :]).parts[:-1]
            found.update("/".join(parts[: depth + 1]) for depth in range(len(parts)))
    return found


def unmatched(files: list[str], lib: str | None) -> list[Finding]:
    """The files no pattern of the layout allows."""
    compiled = patterns(lib)
    return [Finding(each, "no pattern allows it") for each in files if not any(p.fullmatch(each) for _, p in compiled)]


def binding_directories(files: list[str], package: str) -> set[str]:
    """The directories of Python package `package` with binding sources (.cpp, .hpp), and their parents.

    These mirror C++ components; a directory of Python code only need not.
    """
    root = f"python/src/{package}/"
    found: set[str] = set()
    for each in files:
        if each.startswith(root) and each.endswith((".cpp", ".hpp")):
            parts = PurePosixPath(each[len(root) :]).parts[:-1]
            found.update("/".join(parts[: depth + 1]) for depth in range(len(parts)))
    return found


def unmirrored(files: list[str], lib: str | None) -> list[Finding]:
    """The directories of tests/unit/, benchmarks/ and the Python package that name no component of the library."""
    components = directories(files, "src/")
    if lib is not None:
        components |= directories(files, f"include/{lib}/")
    mirrored = {
        "tests/unit": directories(files, "tests/unit/"),
        "benchmarks": {each for each in directories(files, "benchmarks/") if each.split("/")[0] not in BENCHMARK_PARTS},
    }
    bound = {match.group(1) for each in files if (match := re.match(rf"python/src/(py{NAME})/", each))}
    mirrored.update({f"python/src/{package}": binding_directories(files, package) for package in bound})
    return [
        Finding(f"{shown}/{directory}/", "mirrors no component under include/ or src/")
        for shown, found in sorted(mirrored.items())
        for directory in sorted(found)
        if directory not in components
    ]


def unpackaged(files: list[str]) -> list[Finding]:
    """The directories under typings/ without an __init__.pyi."""
    stubbed = directories(files, "typings/")
    present = set(files)
    return [
        Finding(f"typings/{each}/", "has no __init__.pyi")
        for each in sorted(stubbed)
        if f"typings/{each}/__init__.pyi" not in present
    ]


def includes_component(test: str, component: str, lib: str, repository: Path, present: set[str]) -> bool:
    """Whether the C++ test includes a header of `component`: a public one, the component's own, or one under src/."""
    public = f"{lib}/{component}/" if component else f"{lib}/"
    private = f"src/{component}/" if component else "src/"
    directory = PurePosixPath(test).parent
    for target in includes_of(repository / test):
        if target.startswith(public) or (component and target == f"{lib}/{component}.hpp"):
            return True
        # A header the sources keep to themselves: named from src/, or relative to the test.
        beside = normalized(directory / target)
        if any(each.startswith(private) and each in present for each in (f"src/{target}", beside)):
            return True
    return False


def related(name: str, module: str) -> bool:
    """Whether the imported `name` is `module`, a module of it, or a package that holds it."""
    return name == module or name.startswith(module + ".") or module.startswith(name + ".")


def unreferencing(repository: Path, files: list[str], lib: str | None) -> list[Finding]:
    """The unit tests that refer to nothing of the component whose directory they are in.

    A C++ test under tests/unit/<component>/ includes a header of the component. A Python test (test_*.py) under
    tests/unit/<component>/ or python/tests/<component>/ imports the component's module (py<lib>.<component> for the
    bindings), a module of it, or a package that holds it: Python reaches a submodule through its package. A Python
    test at the top of either directory names no component and is not asked, nor is python/tests/downstream/.
    """
    present = set(files)
    roots = {"tests/unit/": [""]} | {"python/tests/": [f"{package}." for package in packages(files)]}
    found: list[Finding] = []
    for each in files:
        path = PurePosixPath(each)
        root = next((root for root in roots if each.startswith(root)), None)
        if root is None:
            continue
        component = "/".join(path.parts[2:-1])
        if each.endswith(".cpp") and root == "tests/unit/" and lib is not None:
            if not includes_component(each, component, lib, repository, present):
                found.append(Finding(each, f"includes no header of its component ({lib}/{component or '...'})"))
        elif path.name.startswith("test_") and each.endswith(".py") and component and not each.startswith(DOWNSTREAM):
            modules = [prefix + component.replace("/", ".") for prefix in roots[root]]
            imported = imports_of(repository / each)
            if not any(related(name, module) for name in imported for module in modules):
                found.append(Finding(each, f"imports nothing of its component ({' or '.join(modules)})"))
    return found


def unincluded(repository: Path, files: list[str], lib: str | None) -> list[Finding]:
    """The headers of a component that no tracked file includes; a header at the top of include/<lib>/ is an entry."""
    if lib is None:
        return []
    targets = included_paths(repository, files)
    return [
        Finding(each, "included by nothing")
        for each in files
        if each.startswith(f"include/{lib}/")
        and each.endswith(".hpp")
        and PurePosixPath(each).parent != PurePosixPath("include", lib)
        and each.removeprefix("include/") not in targets
        and each not in targets
    ]


def check(repository: Path) -> list[Finding]:
    """Every finding of the layout in `repository`."""
    files = tracked(repository)
    lib = library_of(files)
    return (
        unidentified(files)
        + unmatched(files, lib)
        + missing(files, lib)
        + unmirrored(files, lib)
        + unpackaged(files)
        + unreferencing(repository, files, lib)
        + unincluded(repository, files, lib)
    )


def where(path: str) -> str:
    """The directory a finding is counted under: its first two levels, or the root for a file in it."""
    parts = PurePosixPath(path).parts
    directory = parts[:-1] if not path.endswith("/") else parts
    return "/".join(directory[:2]) + "/" if directory else "(root)"


def summary(findings: list[Finding]) -> str:
    """The findings counted by rule and by the directory they are in (two levels deep)."""
    counted = collections.Counter((each.rule, where(each.path)) for each in findings)
    return "\n".join(f"  {count:5d}  {where}  ({rule})" for (rule, where), count in counted.most_common())


def main() -> int:
    """Report the layout's findings in each repository given; 1 where any is found."""
    parser = argparse.ArgumentParser(prog="python -m pybrokkr.layout", description=(__doc__ or "").partition("\n\n")[0])
    parser.add_argument("repositories", nargs="+", type=Path)
    parser.add_argument("--summary", action="store_true", help="only the counts by rule and directory")
    arguments = parser.parse_args()
    found_any = False
    for repository in arguments.repositories:
        findings = check(repository)
        found_any = found_any or bool(findings)
        if not arguments.summary:
            for each in findings:
                sys.stdout.write(f"{repository}/{each.path}: {each.rule}\n")
        sys.stdout.write(f"{repository}: {len(findings)} findings\n")
        if findings:
            sys.stdout.write(summary(findings) + "\n")
    return 1 if found_any else 0


if __name__ == "__main__":
    sys.exit(main())
