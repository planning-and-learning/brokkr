# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""The include graph of a repository, as docs/include_rules.rst checks it: no header includes itself.

An ``#include`` is read as it is written (pybrokkr.rules.references), in every ``#if`` branch, and resolved to a
tracked file: against the including file's directory, then under ``include/``, ``src/`` and ``python/src/``. An
include of a file the repository does not track (the standard library, a dependency) is no edge.

    python -m pybrokkr.rules I4
"""

from graphlib import CycleError, TopologicalSorter
from pathlib import Path, PurePosixPath

from pybrokkr.rules.layout.files import Finding, tracked
from pybrokkr.rules.references import CPP, includes_of, normalized

ROOTS = ("include", "src", "python/src")


def graph(repository: Path, files: list[str]) -> dict[str, set[str]]:
    """Each tracked C++ file of `files` and the tracked files it includes."""
    present = set(files)
    edges: dict[str, set[str]] = {}
    for each in files:
        if not each.endswith(CPP):
            continue
        directory = PurePosixPath(each).parent
        edges[each] = set()
        for target in includes_of(repository / each):
            candidates = [normalized(directory / target), *(normalized(PurePosixPath(r, target)) for r in ROOTS)]
            resolved = next((c for c in candidates if c in present), None)
            if resolved is not None:
                edges[each].add(resolved)
    return edges


def cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """Cycles of `edges`, each listing files that include the next: one is found, broken at its first include, again."""
    found: list[list[str]] = []
    remaining = {node: set(targets) for node, targets in edges.items()}
    while True:
        try:
            # TopologicalSorter takes each node's predecessors; an include is one, the order does not matter here.
            TopologicalSorter(remaining).prepare()
        except CycleError as error:
            # graphlib lists a cycle from each predecessor to its successor, here from the included to the including.
            cycle: list[str] = list(reversed(error.args[1]))
            found.append(cycle)
            remaining[cycle[0]].remove(cycle[1])  # KeyError, not an endless loop, if the cycle were read backwards
        else:
            return found


def check(repository: Path, _sources: set[Path] | None = None) -> list[Finding]:
    """A finding for each cycle of includes in `repository`, at its first file."""
    found = cycles(graph(repository, tracked(repository)))
    return [Finding(cycle[0], "includes itself: " + " -> ".join(cycle)) for cycle in found]
