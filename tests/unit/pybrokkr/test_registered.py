# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.registered on a small repository: what counts as built or run, and what it reports."""

import shutil
import subprocess
from pathlib import Path

from pybrokkr.registered import check

FILES = {
    "src/core/store.cpp": "",  # a source of a target
    "src/core/pool.cpp": "",  # built by nothing
    "tests/CMakeLists.txt": "foreach(test queues)\n  add_executable(test_${test} unit/${test}.cpp)\nendforeach()\n",
    "tests/unit/queues.cpp": "",  # named by the loop
    "tests/unit/sets.cpp": "",  # named nowhere
    "tests/laws/container.cpp": "",  # included by a generated source
    "tests/laws/surface.cpp": "",  # included by a tracked source
    "tests/unit/all.cpp": '#include "../laws/surface.cpp"\n',
    "tests/rules/test_names.py": "",  # pytest finds it
    "tests/rules/exposure.py": "",  # named in tests/rules/CMakeLists.txt
    "tests/rules/CMakeLists.txt": "add_test(NAME exposure COMMAND python ${CMAKE_CURRENT_SOURCE_DIR}/exposure.py)\n",
    "tests/rules/shared.py": "",  # imported by exposure.py
    "tests/rules/budget.py": "",  # run by nothing
    "tests/support/generators/generate.py": "",  # a generator, run by hand
    "tests/__init__.py": "",
}


def repository(path: Path) -> Path:
    """A git repository at `path` tracking FILES."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(path)], check=True)
    for each, content in FILES.items():
        (path / each).parent.mkdir(parents=True, exist_ok=True)
        (path / each).write_text(content)
    (path / "tests/rules/exposure.py").write_text("import shared\n")
    subprocess.run([git, "-C", str(path), "add", "."], check=True)
    return path


def test_reports_what_nothing_builds_or_runs(tmp_path: Path) -> None:
    root = repository(tmp_path / "repository")
    generated = tmp_path / "build" / "container_0.cpp"
    generated.parent.mkdir()
    generated.write_text(f'#include "{root}/tests/laws/container.cpp"\n')
    sources = {root / "src/core/store.cpp", root / "tests/unit/all.cpp", generated}
    assert {(each.path, each.rule) for each in check(root, sources)} == {
        ("src/core/pool.cpp", "built by no target, included by nothing, named in no CMake file"),
        ("tests/unit/sets.cpp", "built by no target, included by nothing, named in no CMake file"),
        ("tests/rules/budget.py", "collected by no pytest run, named in no CMake file, imported by nothing"),
    }
