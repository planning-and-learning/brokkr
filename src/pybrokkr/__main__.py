# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""``python -m pybrokkr --cmake-dir``: where CMake finds brokkr in a manual configure."""

import argparse

from pybrokkr import __version__, cmake_dir

parser = argparse.ArgumentParser(prog="python -m pybrokkr")
parser.add_argument("--cmake-dir", action="store_true", help="print the directory holding brokkrConfig.cmake")
parser.add_argument("--version", action="version", version=__version__)
if parser.parse_args().cmake_dir:
    print(cmake_dir())
else:
    parser.print_help()
