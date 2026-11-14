# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.layout on a small repository: what it allows, and each rule it reports."""

import shutil
import subprocess
from pathlib import Path

from pybrokkr.layout import check

ALLOWED = [
    "pyproject.toml",
    "include/lib/core/store.hpp",
    "src/core/store.cpp",
    "tests/unit/core/store.cpp",
    "benchmarks/core/insert.cpp",
    "benchmarks/support/cells.hpp",
    "benchmarks/results/host-A1.json",
    "python/src/pylib/__init__.pyi",
    "python/src/pylib/py.typed",
    "python/src/pylib/core/__init__.py",
    "typings/clang/__init__.pyi",
    "typings/clang/cindex.pyi",
    "experiments/configs/resources/cluster-16cpu.json",
    "tests/support/data/planning/astar/gripper.json",
    "tests/support/generators/planning/generate_astar.py",
    "tests/__init__.py",
    "tests/integration/python/casters_module.cpp",
    "tests/integration/python/casters.py",
    "benchmarks/tools/test_tools.py",
    "python/src/pylib/core/store.cpp",
    "python/src/pylib/explore/session.py",
    "python/pyproject.toml",
    "python/native/CMakeLists.txt",
    "python/native/oneTBB/CMakeLists.txt",
    "python/native/oneTBB/licenses/third-party-programs.txt",
    "python/native/gtl/settings-struct.patch",
    "python/native/gtl/package/gtlConfig.cmake.in",
]


def repository(path: Path, files: list[str]) -> Path:
    """A git repository at `path` tracking `files`, each empty."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(path)], check=True)
    for each in files:
        (path / each).parent.mkdir(parents=True, exist_ok=True)
        (path / each).write_text("")
    subprocess.run([git, "-C", str(path), "add", "."], check=True)
    return path


def test_allowed_files_have_no_findings(tmp_path: Path) -> None:
    assert check(repository(tmp_path, ALLOWED)) == []


def test_each_rule_reports(tmp_path: Path) -> None:
    files = [
        *ALLOWED,
        "include/lib/core/store.cpp",  # a source under include/
        "profiling/run.cpp",  # profiling/ is benchmarks/
        "tests/unit/missing/store.cpp",  # mirrors no component
        "typings/lab/reports/absolute.pyi",  # no __init__.pyi in typings/lab/ nor typings/lab/reports/
        "python/src/pylib/core/__init__.pyi",  # a stub below the package's root
        "python/src/pylib/search/ground/astar.cpp",  # bindings of no component
    ]
    found = {(each.path, each.rule) for each in check(repository(tmp_path, files))}
    assert ("include/lib/core/store.cpp", "no pattern allows it") in found
    assert ("profiling/run.cpp", "no pattern allows it") in found
    assert ("tests/unit/missing/", "mirrors no component under include/ or src/") in found
    assert ("typings/lab/", "has no __init__.pyi") in found
    assert ("typings/lab/reports/", "has no __init__.pyi") in found
    assert ("python/src/pylib/core/__init__.pyi", "no pattern allows it") in found
    assert ("python/src/pylib/search/", "mirrors no component under include/ or src/") in found
    assert ("python/src/pylib/search/ground/", "mirrors no component under include/ or src/") in found
