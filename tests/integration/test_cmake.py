# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""The CMake helpers' contract.

find_package(brokkr) before project() (found as scikit-build-core finds it, the package dir on CMAKE_PREFIX_PATH), the
rpath and prefix helpers, the locator, the version reader and the stub patching scripts.
"""

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import pybrokkr


def test_find_package_before_project(tmp_path: Path) -> None:
    cmake = _require_cmake()
    (tmp_path / "pyproject.toml").write_text('[tool.x]\nversion = "9.9"\n[project]\nname = "demo"\nversion = "1.2.3"\n')
    (tmp_path / "CMakeLists.txt").write_text(
        textwrap.dedent(
            """\
            cmake_minimum_required(VERSION 3.21)
            find_package(brokkr REQUIRED)
            brokkr_read_project_version(DEMO_VERSION "${CMAKE_CURRENT_SOURCE_DIR}/pyproject.toml")
            project(demo VERSION "${DEMO_VERSION}" LANGUAGES NONE)
            include(GNUInstallDirs)
            brokkr_register_python_native_runtime_prefix("pyprovider")
            brokkr_make_python_native_runtime_rpath_string(rpath "$ORIGIN" "../")
            message(STATUS "version=${PROJECT_VERSION} rpath=${rpath}")
            """
        )
    )
    prefix = Path(pybrokkr.__file__).parent
    out = subprocess.run(
        [cmake, "-S", str(tmp_path), "-B", str(tmp_path / "build"), f"-DCMAKE_PREFIX_PATH={prefix}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "version=1.2.3 rpath=$ORIGIN:$ORIGIN/../pyprovider/lib" in out


def _require_cmake() -> str:
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("cmake is required for the cmake helper contract tests")
    return cmake


def _helpers_path() -> Path:
    helpers = Path(pybrokkr.cmake_dir()) / "brokkrPythonHelpers.cmake"
    assert helpers.is_file(), f"helpers module missing from wheel: {helpers}"
    return helpers


def test_helper_functions_contract(tmp_path: Path) -> None:
    cmake = _require_cmake()
    helpers = _helpers_path()

    dependency_prefix = tmp_path / "dependency"
    (dependency_prefix / "lib").mkdir(parents=True)

    script = tmp_path / "contract.cmake"
    script.write_text(
        textwrap.dedent(
            f"""
            cmake_minimum_required(VERSION 3.21)
            set(CMAKE_INSTALL_LIBDIR lib64)
            include("{helpers.as_posix()}")

            # libdir detection: prefix only has lib/, CMAKE_INSTALL_LIBDIR is lib64
            brokkr_register_python_native_runtime_prefix("pyyggdrasil" "{dependency_prefix.as_posix()}")
            # no second argument: falls back to CMAKE_INSTALL_LIBDIR
            brokkr_register_python_native_runtime_prefix("pypddl/native")

            brokkr_make_python_native_runtime_rpaths(runtime_rpaths "$ORIGIN" "../")
            if(NOT runtime_rpaths STREQUAL "$ORIGIN;$ORIGIN/../pyyggdrasil/lib;$ORIGIN/../pypddl/native/lib64")
                message(FATAL_ERROR "unexpected rpath list: ${{runtime_rpaths}}")
            endif()

            brokkr_make_python_native_runtime_rpath_string(runtime_rpath "@loader_path" "../../../")
            set(expected_rpath "@loader_path:@loader_path/../../../pyyggdrasil/lib")
            string(APPEND expected_rpath ":@loader_path/../../../pypddl/native/lib64")
            if(NOT runtime_rpath STREQUAL expected_rpath)
                message(FATAL_ERROR "unexpected rpath string: ${{runtime_rpath}}")
            endif()

            # include-dir registration only records existing directories
            brokkr_register_native_dependency_prefix("{dependency_prefix.as_posix()}")
            if(BROKKR_NATIVE_DEPENDENCY_INCLUDE_DIRECTORIES)
                message(FATAL_ERROR "prefix without include/ must not register: "
                                    "${{BROKKR_NATIVE_DEPENDENCY_INCLUDE_DIRECTORIES}}")
            endif()

            # manual override: preset out-var is respected and prepended to CMAKE_PREFIX_PATH
            set(OVERRIDE_PREFIX "{dependency_prefix.as_posix()}")
            brokkr_find_python_native_prefix(nonexistent_package OVERRIDE_PREFIX)
            if(NOT OVERRIDE_PREFIX STREQUAL "{dependency_prefix.as_posix()}")
                message(FATAL_ERROR "manual override was clobbered: ${{OVERRIDE_PREFIX}}")
            endif()
            if(NOT "{dependency_prefix.as_posix()}" IN_LIST CMAKE_PREFIX_PATH)
                message(FATAL_ERROR "override prefix missing from CMAKE_PREFIX_PATH")
            endif()
            """
        ),
        encoding="utf-8",
    )

    subprocess.run([cmake, "-P", str(script)], check=True)


@pytest.mark.parametrize("script", ["read_project_version", "patch_python_stubs"])
def test_cmake_script(tmp_path: Path, script: str) -> None:
    cmake = _require_cmake()
    subprocess.run(
        [
            cmake,
            f"-DBROKKR_CMAKE_DIR={pybrokkr.cmake_dir()}",
            f"-DBROKKR_TEST_BINARY_DIR={tmp_path}",
            "-P",
            str(Path(__file__).parents[1] / "support" / "data" / "cmake" / f"{script}.cmake"),
        ],
        check=True,
    )


def test_locate_finds_brokkr_through_python(tmp_path: Path) -> None:
    """A package config's consumer need not know brokkr: brokkrLocate.cmake asks the Python that has pybrokkr."""
    cmake = _require_cmake()
    locate = Path(pybrokkr.cmake_dir()) / "brokkrLocate.cmake"
    (tmp_path / "CMakeLists.txt").write_text(
        textwrap.dedent(
            f"""\
            cmake_minimum_required(VERSION 3.21)
            project(consumer LANGUAGES NONE)
            include("{locate.as_posix()}")
            if(NOT COMMAND brokkr_find_python_native_prefix)
                message(FATAL_ERROR "brokkr helpers missing")
            endif()
            message(STATUS "located ${{brokkr_DIR}}")
            """
        )
    )
    result = subprocess.run(
        [cmake, "-S", str(tmp_path), "-B", str(tmp_path / "build"), f"-DPython_EXECUTABLE={sys.executable}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"located {pybrokkr.cmake_dir()}" in result.stdout
