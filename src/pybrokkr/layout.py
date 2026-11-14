# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""The directory layout of a library, as docs/directory_layout.rst states it: each file allowed, each structure kept.

A tracked file (``git ls-files``, relative to the repository root) is allowed where one pattern of the layout matches it
whole. Two rules are about structure and are checked beside the patterns:

- mirroring: a directory under ``tests/unit/``, under ``benchmarks/`` (other than ``support/``, ``suites/``,
  ``results/``, ``tools/``), or of the Python package that holds binding sources (or is a parent of one that does),
  names a component that exists under ``include/<lib>/`` or ``src/``;
- stub packages: every directory under ``typings/`` has an ``__init__.pyi``.

    python -m pybrokkr.layout <repository>...

reports each finding as ``<repository>/<path>: <rule>``, then a summary per repository, and exits 1 where any is found.
The library's name is the one directory under ``include/``.
"""

import argparse
import collections
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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


def patterns(lib: str) -> list[tuple[str, re.Pattern[str]]]:
    """The layout's patterns for library `lib`, by kind, in the order docs/directory_layout.rst lists them."""
    n, d = NAME, DIRS
    listed = [
        (
            "root",
            "|".join(map(re.escape, ROOT_FILES)),
        ),
        ("ci", r"\.github/workflows/[a-z0-9_-]+\.yml"),
        ("directory files", rf"(?:{n}/)+(?:README\.md|\.clang-tidy)"),
        ("include", rf"include/{lib}/{d}{n}\.hpp"),
        ("src", rf"src/{d}(?:{n}\.(?:cpp|hpp)|CMakeLists\.txt)"),
        ("exe, examples", rf"(?:exe|examples|python/examples)/{d}(?:{n}\.(?:cpp|hpp|py)|CMakeLists\.txt)"),
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
        ("share", rf"share/{lib}/{d}{n}\.json"),
        ("cmake", rf"cmake/{lib}_{n}\.cmake|cmake/{n}\.py"),
        ("typings", rf"typings/{n}/{d}(?:__init__|{n})\.pyi"),
    ]
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


def library_of(files: list[str]) -> str:
    """The library's name: the one directory under include/."""
    names = {match.group(1) for each in files if (match := re.match(r"include/([^/]+)/", each))}
    if len(names) != 1:
        msg = f"include/ must hold one directory, the library's; it holds {sorted(names) or 'none'}"
        raise ValueError(msg)
    return names.pop()


def directories(files: list[str], root: str) -> set[str]:
    """Every directory under `root` that holds a tracked file, at any depth, relative to `root`."""
    found: set[str] = set()
    for each in files:
        if each.startswith(root):
            parts = PurePosixPath(each[len(root) :]).parts[:-1]
            found.update("/".join(parts[: depth + 1]) for depth in range(len(parts)))
    return found


def unmatched(files: list[str], lib: str) -> list[Finding]:
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


def unmirrored(files: list[str], lib: str) -> list[Finding]:
    """The directories of tests/unit/, benchmarks/ and the Python package that name no component of the library."""
    components = directories(files, f"include/{lib}/") | directories(files, "src/")
    mirrored = {
        "tests/unit": directories(files, "tests/unit/"),
        "benchmarks": {each for each in directories(files, "benchmarks/") if each.split("/")[0] not in BENCHMARK_PARTS},
    }
    packages = {match.group(1) for each in files if (match := re.match(rf"python/src/(py{NAME})/", each))}
    mirrored.update({f"python/src/{package}": binding_directories(files, package) for package in packages})
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


def check(repository: Path) -> list[Finding]:
    """Every finding of the layout in `repository`."""
    files = tracked(repository)
    lib = library_of(files)
    return unmatched(files, lib) + unmirrored(files, lib) + unpackaged(files)


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
