# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.layout on a small repository: what it allows, and each rule it reports."""

import shutil
import subprocess
from pathlib import Path

import pytest

from pybrokkr.layout import REQUIRED, REQUIRED_OF_A_LIBRARY, check

# What each file of the small repository holds, where a rule reads it; every other file is empty.
CONTENTS = {
    "tests/unit/core/store.cpp": '#include "lib/core/store.hpp"\n',
    "python/tests/core/test_store.py": "from pylib import core\n",
}
ALLOWED = [
    *REQUIRED,
    *REQUIRED_OF_A_LIBRARY,
    "python/tests/core/test_store.py",
    "python/tests/downstream/test_python_import.py",
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


def repository(path: Path, files: list[str], contents: dict[str, str] | None = None) -> Path:
    """A git repository at `path` tracking `files`, each holding `contents` of it, else CONTENTS, else nothing."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(path)], check=True)
    for each in files:
        (path / each).parent.mkdir(parents=True, exist_ok=True)
        (path / each).write_text((contents or {}).get(each, CONTENTS.get(each, "")))
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


def test_a_python_package_has_no_findings(tmp_path: Path) -> None:
    files = [
        *REQUIRED,
        "src/pytool/__init__.py",
        "src/pytool/py.typed",
        "src/pytool/check.py",
        "src/pytool/cmake/toolConfig.cmake",
        "tests/unit/pytool/test_check.py",
        "tests/integration/test_cmake.py",
        "tests/support/data/cmake/prelude.cmake",
    ]
    contents = {"tests/unit/pytool/test_check.py": "from pytool.check import run\n"}
    assert check(repository(tmp_path, files, contents)) == []


def test_brokkr_follows_its_own_layout() -> None:
    root = Path(__file__).parents[3]
    if not (root / ".git").exists():
        pytest.skip("the layout is checked on a checkout: a source archive tracks no files")
    assert check(root) == []


@pytest.mark.parametrize("required", [*REQUIRED, *REQUIRED_OF_A_LIBRARY])
def test_a_required_file_is_missing(tmp_path: Path, required: str) -> None:
    files = [each for each in ALLOWED if each != required]
    assert [(each.path, each.rule) for each in check(repository(tmp_path, files))] == [(required, "required, missing")]


def test_a_repository_is_a_library_or_a_package(tmp_path: Path) -> None:
    found = {(each.path, each.rule) for each in check(repository(tmp_path, [*REQUIRED, "docs/index.rst"]))}
    assert found == {("", "holds no library (include/<lib>/) and no Python package (src/py<name>/)")}


def test_include_holds_one_library(tmp_path: Path) -> None:
    found = {(each.path, each.rule) for each in check(repository(tmp_path, [*ALLOWED, "include/other/core.hpp"]))}
    assert ("include/", "holds more than the library's directory: lib, other") in found


def test_a_unit_test_refers_to_its_component(tmp_path: Path) -> None:
    files = [
        *ALLOWED,
        "include/lib/core/pool.hpp",
        "include/lib/search/astar.hpp",
        "src/search/detail.hpp",
        "tests/unit/search/astar.cpp",  # includes another component only
        "tests/unit/search/detail.cpp",  # includes a header its component keeps under src/
        "tests/unit/core/pool.cpp",  # includes its component's header
        "python/tests/core/test_pool.py",  # imports the package that holds its component
        "python/tests/core/test_other.py",  # imports nothing of the package
        "python/tests/core/helpers.py",  # no test
    ]
    contents = {
        "tests/unit/search/astar.cpp": '#include "lib/core/store.hpp"\n#include <lib/search.hpp>\n',
        "tests/unit/search/detail.cpp": '#include "search/detail.hpp"\n#include "lib/search/astar.hpp"\n',
        "tests/unit/core/pool.cpp": "#  include <lib/core/pool.hpp>\n",
        "python/tests/core/test_pool.py": "import pylib\n",
        "python/tests/core/test_other.py": "import json\n",
    }
    found = {(each.path, each.rule) for each in check(repository(tmp_path, files, contents))}
    assert found == {("python/tests/core/test_other.py", "imports nothing of its component (pylib.core)")}
    contents["tests/unit/search/astar.cpp"] = '#include "lib/core/store.hpp"\n'
    contents["tests/unit/search/detail.cpp"] = '#include "search/detail.hpp"\n'
    found = {(each.path, each.rule) for each in check(repository(tmp_path / "again", files, contents))}
    assert found == {
        ("python/tests/core/test_other.py", "imports nothing of its component (pylib.core)"),
        ("tests/unit/search/astar.cpp", "includes no header of its component (lib/search)"),
        ("include/lib/search/astar.hpp", "included by nothing"),
    }


def test_a_header_is_included(tmp_path: Path) -> None:
    files = [*ALLOWED, "include/lib/core/pool.hpp", "include/lib/core/detail/pool_impl.hpp", "include/lib/lib.hpp"]
    contents = {"include/lib/core/pool.hpp": '#include "detail/pool_impl.hpp"\n'}
    found = {(each.path, each.rule) for each in check(repository(tmp_path, files, contents))}
    # pool_impl.hpp is included relative to pool.hpp; lib.hpp is an entry header; nothing includes pool.hpp.
    assert found == {("include/lib/core/pool.hpp", "included by nothing")}
