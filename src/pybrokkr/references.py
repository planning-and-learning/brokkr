# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a source file refers to, read from its text: the headers a C++ file includes, the modules a Python file imports.

The layout's rules about use (pybrokkr.layout, pybrokkr.registered) ask these of every tracked file. Neither needs a
build: an include is read as it is written, not resolved against the include paths.
"""

import ast
import re
from pathlib import Path, PurePosixPath

INCLUDE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"]+)[>"]', re.MULTILINE)
CPP = (".cpp", ".hpp")


def includes_of(path: Path) -> set[str]:
    """The targets of the ``#include`` directives of the C++ file at `path`, as written; none for a missing file."""
    if not path.is_file():
        return set()
    return set(INCLUDE.findall(path.read_text(errors="replace")))


def imports_of(path: Path) -> set[str]:
    """The modules the Python file at `path` imports, absolute ones only; none for a file that does not parse.

    ``from a.b import c`` gives ``a.b`` and ``a.b.c``, as ``c`` may be a module of the package ``a.b``.
    """
    if not path.is_file():
        return set()
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def included_paths(repository: Path, files: list[str]) -> set[str]:
    """Every include target of the tracked C++ `files`, as written and resolved against the including file's directory.

    A tracked file is included where its path ends with one of these (pybrokkr.references.is_included).
    """
    targets: set[str] = set()
    for each in files:
        if not each.endswith(CPP):
            continue
        directory = PurePosixPath(each).parent
        for target in includes_of(repository / each):
            targets.add(normalized(PurePosixPath(target)))
            targets.add(normalized(directory / target))
    return targets


def is_included(path: str, targets: set[str]) -> bool:
    """Whether the tracked file `path` is an include target: one of `targets` names it, or its path ends with one."""
    parts = PurePosixPath(path).parts
    return any("/".join(parts[start:]) in targets for start in range(len(parts)))


def normalized(path: PurePosixPath) -> str:
    """`path` without ``.`` and with each ``..`` taken against the part before it; a leading ``..`` is dropped."""
    parts: list[str] = []
    for part in path.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)
