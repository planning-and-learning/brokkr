# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.rules: which rules a selection names, and that a selected rule reports only its own findings."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pybrokkr.rules.__main__ import RULES, selected
from pybrokkr.rules.layout.files import REQUIRED


def test_a_rule_is_selected_by_id_name_page_class_or_all() -> None:
    assert selected(["L1.2"]) == ["L1.2"]
    # A rule's ID selects its parts: L1 (the layout) is L1.1 to L1.7.
    assert selected(["L1"]) == [f"L1.{part}" for part in range(1, 8)]
    assert selected(["layout-mirroring", "L1.1"]) == ["L1.1", "L1.3"]
    assert selected(["L"]) == [rule for rule in RULES if rule.startswith("L")]
    assert selected(["decidable"]) == [rule for rule in RULES if RULES[rule].kind == "decidable"]
    assert selected(["all"]) == list(RULES)


@pytest.mark.parametrize("name", ["L99", "T", "judgment", "layout-unknown"])
def test_a_name_that_selects_nothing_is_an_error(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        selected([name])


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    """``python -m pybrokkr.rules`` with `arguments`."""
    command = [sys.executable, "-m", "pybrokkr.rules", *arguments]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_a_rule_reports_only_its_findings(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True)
    # pyproject.toml is missing (L1.2) and profiling/ is not allowed (L1.1).
    for each in [*REQUIRED[1:], "src/pytool/__init__.py", "profiling/run.py"]:
        (tmp_path / each).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / each).write_text("")
    subprocess.run([git, "-C", str(tmp_path), "add", "."], check=True)
    result = run("L1.2", "-C", str(tmp_path))
    assert result.returncode == 1
    assert f"{tmp_path}/pyproject.toml: L1.2 (layout-required-files): required, missing\n" in result.stdout
    assert "profiling" not in result.stdout
    assert "profiling/run.py: L1.1 (layout-allowed-files)" in run("L1.1", "-C", str(tmp_path)).stdout


def test_a_rule_that_needs_the_build_without_it(tmp_path: Path) -> None:
    named = run("L1.7", "-C", str(tmp_path))
    assert named.returncode == 2
    assert "L1.7: needs the sources of a configured build" in named.stderr
    page = run("L", "-C", str(Path(__file__).parents[4]))
    assert "L1.7 (layout-sources-built): not checked" in page.stdout
    assert page.stdout.endswith("findings (L1.1, L1.2, L1.3, L1.4, L1.5, L1.6)\n")
