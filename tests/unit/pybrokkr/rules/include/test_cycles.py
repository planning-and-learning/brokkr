# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.rules.include.cycles on a small repository: how an include resolves, and each cycle it reports."""

import itertools
import shutil
import subprocess
from pathlib import Path

from pybrokkr.rules.include.cycles import check, cycles, graph

FILES = {
    "include/lib/a.hpp": '#include "lib/b.hpp"\n#include <vector>\n',  # through include/; <vector> is no edge
    "include/lib/b.hpp": '#include "c.hpp"\n',  # relative to its directory
    "include/lib/c.hpp": '#include "lib/a.hpp"\n',  # closes a -> b -> c -> a
    "include/lib/d.hpp": '#include "lib/d.hpp"\n',  # includes itself
    "src/e.cpp": '#include "lib/a.hpp"\n',  # into the cycle, not part of it
}


def repository(path: Path) -> Path:
    """A git repository at `path` tracking FILES."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(path)], check=True)
    for each, content in FILES.items():
        (path / each).parent.mkdir(parents=True, exist_ok=True)
        (path / each).write_text(content)
    subprocess.run([git, "-C", str(path), "add", "."], check=True)
    return path


def test_an_include_resolves_to_a_tracked_file(tmp_path: Path) -> None:
    edges = graph(repository(tmp_path), list(FILES))
    assert edges["include/lib/a.hpp"] == {"include/lib/b.hpp"}
    assert edges["include/lib/b.hpp"] == {"include/lib/c.hpp"}
    assert edges["src/e.cpp"] == {"include/lib/a.hpp"}


def test_each_cycle_is_reported_in_include_order(tmp_path: Path) -> None:
    found = {tuple(cycle) for cycle in cycles(graph(repository(tmp_path), list(FILES)))}
    assert ("include/lib/d.hpp", "include/lib/d.hpp") in found
    assert len(found) == 2
    (cycle,) = found - {("include/lib/d.hpp", "include/lib/d.hpp")}
    assert len(cycle) == 4
    for including, included in itertools.pairwise(cycle):
        assert included in graph(tmp_path, list(FILES))[including]


def test_no_cycle_no_finding(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "include/lib/c.hpp").write_text("")
    (root / "include/lib/d.hpp").write_text("")
    assert check(root) == []
