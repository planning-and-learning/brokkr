# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every tracked source is built and every test script is run, checked against the configured build.

The layout (pybrokkr.layout) says where a file may be; this says that the build uses it. A test source that no
``CMakeLists.txt`` names passes the layout, is never compiled, and its tests never run.

- A C++ source (``.cpp`` under ``src/``, ``tests/``, ``benchmarks/``, ``exe/``, ``examples/``, ``python/``) is a source
  of a CMake target, is included by a source or a tracked file, or is named in a CMake file of its directory or of one
  above it (a source a test compiles itself, or one a loop over names adds).
- A Python script under ``tests/`` is a test pytest finds by its name (``test_*.py``), is named in a CMake file of its
  directory or of one above it, or is imported by a tracked Python file.

    python -m pybrokkr.registered --sources build/brokkr/sources.txt <repository>

``sources.txt`` lists the sources of every target, one absolute path per line: ``brokkr_add_rule_tests()`` writes it
when the build is configured. It is CMake's own list, so it holds each source of a unity batch too, which
``compile_commands.json`` does not. Reports each finding as ``<repository>/<path>: <rule>`` and exits 1 where any is
found.
"""

import argparse
import re
import sys
from pathlib import Path, PurePosixPath

from pybrokkr.layout import Finding, tracked
from pybrokkr.references import CPP, imports_of, included_paths, includes_of, is_included

SOURCE_ROOTS = ("src/", "tests/", "benchmarks/", "exe/", "examples/", "python/")
SCRIPT_ROOTS = ("tests/",)
# What a tracked Python file under tests/ may be without being run: a package, pytest's own, a generator of test data.
NOT_RUN = re.compile(r"(?:.*/)?(?:__init__|conftest)\.py|tests/support/.*")


def cmake_texts(repository: Path, files: list[str]) -> dict[PurePosixPath, str]:
    """The text of the tracked CMake files (CMakeLists.txt, *.cmake), by the directory each is in."""
    texts: dict[PurePosixPath, str] = {}
    for each in files:
        path = PurePosixPath(each)
        if (path.name == "CMakeLists.txt" or path.suffix == ".cmake") and (repository / each).is_file():
            texts[path.parent] = texts.get(path.parent, "") + (repository / each).read_text(errors="replace")
    return texts


def named(path: str, texts: dict[PurePosixPath, str]) -> bool:
    """Whether a CMake file of the directory of `path`, or of one above it, names it.

    By its file name, with or without its suffix, as a word: ``add_executable(a a.cpp)``, or ``foreach(test a b)`` with
    ``${test}.cpp``.
    """
    name = PurePosixPath(path)
    words = [re.compile(rf"(?<![A-Za-z0-9_]){re.escape(each)}(?![A-Za-z0-9_])") for each in (name.name, name.stem)]
    return any(word.search(texts.get(directory, "")) for directory in name.parents for word in words)


def unbuilt(repository: Path, files: list[str], sources: set[Path]) -> list[Finding]:
    """The tracked C++ sources that no target builds, nothing includes, and no CMake file names."""
    root = repository.resolve()
    built = {str(each.relative_to(root)) for each in sources if each.is_relative_to(root)}
    targets = included_paths(repository, files)
    # A generated source (in the build directory) may include a tracked one: a test compiled once per subject.
    # It names it by its absolute path, as CMake wrote it.
    for each in sources:
        if each.suffix in CPP and not each.is_relative_to(root):
            targets |= {target.removeprefix(f"{root}/") for target in includes_of(each)}
    texts = cmake_texts(repository, files)
    return [
        Finding(each, "built by no target, included by nothing, named in no CMake file")
        for each in files
        if each.endswith(".cpp")
        and each.startswith(SOURCE_ROOTS)
        and each not in built
        and not is_included(each, targets)
        and not named(each, texts)
    ]


def unrun(repository: Path, files: list[str]) -> list[Finding]:
    """The tracked Python scripts under tests/ that pytest does not find, no CMake file names, and nothing imports."""
    texts = cmake_texts(repository, files)
    imported: set[str] = set()
    for each in files:
        if each.endswith(".py"):
            imported |= imports_of(repository / each)
    modules = {name.rsplit(".", 1)[-1] for name in imported}
    return [
        Finding(each, "collected by no pytest run, named in no CMake file, imported by nothing")
        for each in files
        if each.endswith(".py")
        and each.startswith(SCRIPT_ROOTS)
        and not NOT_RUN.fullmatch(each)
        and not PurePosixPath(each).name.startswith("test_")
        and not named(each, texts)
        and PurePosixPath(each).stem not in modules
    ]


def check(repository: Path, sources: set[Path]) -> list[Finding]:
    """Every finding in `repository`, whose targets build `sources`."""
    files = tracked(repository)
    return unbuilt(repository, files, sources) + unrun(repository, files)


def main() -> int:
    """Report the sources no target builds and the test scripts nothing runs; 1 where any is found."""
    parser = argparse.ArgumentParser(
        prog="python -m pybrokkr.registered", description=(__doc__ or "").partition("\n\n")[0]
    )
    parser.add_argument(
        "--sources", required=True, type=Path, help="the targets' sources, as brokkr_add_rule_tests writes them"
    )
    parser.add_argument("repository", type=Path)
    arguments = parser.parse_args()
    sources = {Path(line).resolve() for line in arguments.sources.read_text().splitlines() if line}
    findings = check(arguments.repository, sources)
    for each in findings:
        sys.stdout.write(f"{arguments.repository}/{each.path}: {each.rule}\n")
    sys.stdout.write(f"{arguments.repository}: {len(findings)} findings\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
