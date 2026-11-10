# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr: build tooling for native C++ libraries shipped as Python wheels.

- CMake helpers (``find_package(brokkr)``): bundled native prefixes, relative rpaths into sibling provider wheels,
  install-time runtime-path fixup and stub post-processing, the pyproject version for ``project(VERSION)``.
- A PEP 517 backend around scikit-build-core (:mod:`pybrokkr.build_backend`).
"""

from pathlib import Path

__version__ = "0.1.1"


def cmake_dir() -> str:
    """The directory holding brokkrConfig.cmake, for ``-Dbrokkr_DIR=...``."""
    return str(Path(__file__).resolve().parent / "cmake")
