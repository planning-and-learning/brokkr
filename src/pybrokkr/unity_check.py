# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""File-local functions that a unity batch would put into one translation unit, found with libclang (from PyPI).

A batch (``brokkr_unity_directories``, template rules, rule 11) compiles the sources of a directory as one TU. A name
that two of them declare twice then fails to compile, except functions with internal linkage (``static``, or in an
anonymous namespace) of one name and different parameters: they become overloads of each other, and a call may resolve
to another file's function without an error. This reports them, for each directory given:

    python -m pybrokkr.unity_check --compile-commands build/compile_commands.json src/a src/b

with the build configured to compile each source on its own (``<PROJECT>_UNITY_BUILD=OFF``), so that the compile
commands list every source.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

import clang.cindex as ci

from pybrokkr.fallbacks import flags_of, resource_dir

FUNCTIONS = {ci.CursorKind.FUNCTION_DECL, ci.CursorKind.FUNCTION_TEMPLATE}


def qualified(cursor: ci.Cursor) -> str:
    """The qualified name of `cursor`, an anonymous namespace as ``(anonymous)``."""
    parts: list[str] = []
    at: ci.Cursor | None = cursor
    while at is not None and at.kind != ci.CursorKind.TRANSLATION_UNIT:
        parts.append(at.spelling or "(anonymous)")
        at = at.semantic_parent
    return "::".join(reversed(parts))


def file_local_functions(entry: dict[str, str], clang_headers: str) -> set[str]:
    """The functions with internal linkage that the source itself declares (not its headers), by qualified name."""
    source = entry["file"]
    flags = [*flags_of(entry), "-resource-dir", clang_headers]
    unit = ci.Index.create().parse(source, args=flags, options=ci.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES)
    found: set[str] = set()
    for cursor in unit.cursor.walk_preorder():
        location = cursor.location.file
        if cursor.kind in FUNCTIONS and location is not None and location.name == source:
            name = qualified(cursor)
            if cursor.linkage == ci.LinkageKind.INTERNAL or "(anonymous)" in name:
                found.add(name)
    return found


def main() -> int:
    """Report each directory's file-local functions declared in more than one of its sources; 1 where any is."""
    parser = argparse.ArgumentParser(
        prog="python -m pybrokkr.unity_check", description=(__doc__ or "").partition("\n\n")[0]
    )
    parser.add_argument("--compile-commands", required=True, type=Path)
    parser.add_argument("directories", nargs="+", type=Path)
    arguments = parser.parse_args()
    entries = json.loads(arguments.compile_commands.read_text())
    clang_headers = resource_dir()
    shared_anywhere = False
    for directory in arguments.directories:
        sources = [e for e in entries if Path(e["file"]).resolve().parent == directory.resolve()]
        owners: dict[str, set[str]] = collections.defaultdict(set)
        for entry in sources:
            for function in file_local_functions(entry, clang_headers):
                owners[function].add(Path(entry["file"]).name)
        shared = {name: files for name, files in owners.items() if len(files) > 1}
        shared_anywhere = shared_anywhere or bool(shared)
        sys.stdout.write(f"{directory}: {len(sources)} sources, {len(shared)} shared\n")
        for name, files in sorted(shared.items()):
            sys.stdout.write(f"    {name}  <- {', '.join(sorted(files))}\n")
    return 1 if shared_anywhere else 0


if __name__ == "__main__":
    sys.exit(main())
