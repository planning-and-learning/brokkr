# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""brokkr_add_rule_tests in a configured project: the tests it registers and the sources it writes."""

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

import pybrokkr


def test_registers_the_rules_and_writes_every_targets_sources(tmp_path: Path) -> None:
    cmake, ctest, git = shutil.which("cmake"), shutil.which("ctest"), shutil.which("git")
    if cmake is None or ctest is None or git is None:
        pytest.skip("cmake, ctest and git are required")
    source = tmp_path / "demo"
    (source / "src").mkdir(parents=True)
    (source / "tests").mkdir()
    subprocess.run([git, "init", "-q", str(source)], check=True)
    (source / "src/a.cpp").write_text("int a() { return 0; }\n")
    (source / "src/b.cpp").write_text("int b() { return 0; }\n")
    (source / "CMakeLists.txt").write_text(
        textwrap.dedent(
            """\
            cmake_minimum_required(VERSION 3.21)
            find_package(brokkr REQUIRED)
            project(demo LANGUAGES CXX)
            enable_testing()
            add_library(demo STATIC src/a.cpp)
            add_subdirectory(tests)
            target_sources(demo PRIVATE src/b.cpp)
            """
        )
    )
    (source / "tests/CMakeLists.txt").write_text("brokkr_add_rule_tests()\n")
    build = tmp_path / "build"
    prefix = Path(pybrokkr.__file__).parent
    subprocess.run([cmake, "-S", str(source), "-B", str(build), f"-DCMAKE_PREFIX_PATH={prefix}"], check=True)
    # Written once the project's directories are all read: b.cpp is added after the call.
    assert (build / "brokkr/sources.txt").read_text().split() == [str(source / "src/a.cpp"), str(source / "src/b.cpp")]
    listed = subprocess.run(
        [ctest, "--test-dir", str(build), "-N", "-L", "rules"], check=True, capture_output=True, text=True
    )
    assert "layout" in listed.stdout
    assert "registered" in listed.stdout
