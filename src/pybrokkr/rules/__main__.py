# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""One command for every rule a check decides, whichever module checks it.

    python -m pybrokkr.rules <rule>... [-C <repository>] [--sources <file>] [--compile-commands <file>] [-j <jobs>]

A rule is selected by its ID (``L1``), its name (``layout-allowed-files``), the letter of its page (``L``: every rule
of the page that has a check), its class (``decidable``) or ``all``. A rule that needs the configured build (L7) reads
the targets' sources from ``--sources``, by default ``<repository>/build/brokkr/sources.txt``, where
``brokkr_add_rule_tests()`` writes them. Without them, a rule named by its ID or name is an error, and one selected by
a page, a class or ``all`` is reported as not checked. Reports each finding as
``<repository>/<path>: <ID> (<name>): <what>`` and exits 1 where any is found.
"""

import argparse
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pybrokkr.rules.include import cycles
from pybrokkr.rules.layout import files, registered
from pybrokkr.rules.schema import records


@dataclass(frozen=True)
class Inputs:
    """What a rule may need beyond the repository: the build's sources (L7), its compile database (S)."""

    sources: set[Path]
    compile_commands: Path | None
    jobs: int


@dataclass(frozen=True)
class Rule:
    """A rule of the docs that a check decides: its name, its class, its check, and the input it needs, if any."""

    name: str
    kind: str
    run: Callable[[Path, Inputs], list[files.Finding]]
    needs: str = ""


def _layout_rule(rule: str) -> Callable[[Path, Inputs], list[files.Finding]]:
    return lambda repository, _: files.check(repository, [rule])


def _schema_rule(rule: str) -> Callable[[Path, Inputs], list[files.Finding]]:
    def run(repository: Path, inputs: Inputs) -> list[files.Finding]:
        if inputs.compile_commands is None:
            message = f"{rule} needs a compile database"
            raise ValueError(message)
        return records.check(repository.resolve(), inputs.compile_commands.resolve(), inputs.jobs)[rule]

    return run


RULES: dict[str, Rule] = {
    **{rule: Rule(name, "decidable", _layout_rule(rule)) for rule, (name, _) in files.RULES.items()},
    "L7": Rule(
        "layout-sources-built",
        "decidable",
        lambda repository, inputs: registered.check(repository, inputs.sources),
        "sources",
    ),
    "I4": Rule("include-no-cycles", "decidable", lambda repository, _: cycles.check(repository)),
    "S1": Rule("schema-record-data", "decidable", _schema_rule("S1"), "compile commands"),
    "S2": Rule("schema-record-view", "decidable", _schema_rule("S2"), "compile commands"),
    "S3": Rule("schema-record-binding", "decidable", _schema_rule("S3"), "compile commands"),
}


def selected(names: list[str]) -> list[str]:
    """The IDs `names` select, in the order of RULES; a name that selects no rule raises ValueError."""
    chosen: set[str] = set()
    for each in names:
        match = [
            rule
            for rule, info in RULES.items()
            if each in {"all", rule, info.name, info.kind} or (re.fullmatch("[A-Z]", each) and rule[0] == each)
        ]
        if not match:
            message = f"{each}: no rule with a check has this ID, name, page letter or class"
            raise ValueError(message)
        chosen.update(match)
    return [rule for rule in RULES if rule in chosen]


def found(given: Path | None, repository: Path, defaults: list[str]) -> Path | None:
    """`given`, else the first of `defaults` (under `repository`) that exists; none where none does."""
    if given is not None:
        return given
    return next((repository / each for each in defaults if (repository / each).is_file()), None)


def main() -> int:
    """Report the findings of the rules selected in the repository; 1 where any is found."""
    parser = argparse.ArgumentParser(prog="python -m pybrokkr.rules", description=(__doc__ or "").partition("\n\n")[0])
    parser.add_argument("rules", nargs="+", help="IDs, names, page letters, classes, or all")
    parser.add_argument("-C", dest="repository", type=Path, default=Path(), help="the repository (default: here)")
    parser.add_argument("--sources", type=Path, help="the targets' sources (default: build/brokkr/sources.txt)")
    parser.add_argument("--compile-commands", type=Path, help="the compile database (default: under build/)")
    parser.add_argument(
        "-j", "--jobs", type=int, default=os.cpu_count() or 1, help="files parsed at once (default: the number of cores)"
    )
    arguments = parser.parse_args()
    try:
        rules = selected(arguments.rules)
    except ValueError as error:
        parser.error(str(error))
    repository: Path = arguments.repository
    paths = {
        "sources": found(arguments.sources, repository, ["build/brokkr/sources.txt"]),
        "compile commands": found(
            arguments.compile_commands,
            repository,
            ["build/compile_commands.json", "build/peachycheck/compile_commands.json"],
        ),
    }
    missing = {rule: RULES[rule].needs for rule in rules if RULES[rule].needs and paths[RULES[rule].needs] is None}
    named = [rule for rule in missing if rule in arguments.rules or RULES[rule].name in arguments.rules]
    if named:
        parser.error(f"{', '.join(named)}: needs the {missing[named[0]]} of a configured build: none under build/")
    sources = paths["sources"]
    inputs = Inputs(
        {Path(line).resolve() for line in sources.read_text().splitlines() if line} if sources else set[Path](),
        paths["compile commands"],
        arguments.jobs,
    )
    count = 0
    for rule in rules:
        if rule in missing:
            sys.stdout.write(f"{rule} ({RULES[rule].name}): not checked, no {missing[rule]} under build/\n")
            continue
        for each in RULES[rule].run(repository, inputs):
            sys.stdout.write(f"{repository}/{each.path}: {rule} ({RULES[rule].name}): {each.rule}\n")
            count += 1
    checked = [rule for rule in rules if rule not in missing]
    sys.stdout.write(f"{repository}: {count} findings ({', '.join(checked)})\n")
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main())
