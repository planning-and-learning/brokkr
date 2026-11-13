# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""Silent fallbacks in a C++ project, found with clang's own parser (libclang, from PyPI).

A fallback is code that detects that something it needs does not hold (a capability, a successful result, a value)
and proceeds without reporting it: it discards what failed, or manufactures a value in its place (error hiding,
failing slowly; Rinard's failure-oblivious computing does both on purpose). Only the shapes whose failure path has
no code of its own are reported, so that every finding is one (sound, not complete):

- skipped capability: ``if constexpr (requires ...) S`` without ``else``, the ``requires`` not negated, S not leaving
  (return, throw, break, continue): where the type lacks it, nothing happens instead of a compile error;
- discarded failure: a ``catch`` with an empty handler: where the operation fails, execution goes on;
- substituted value: ``value_or(v)``: where the value is missing, v takes its place.

An alternative, which meets the same contract another way (a derived operation's default, dispatch on a
representation), is written as an overload or with an ``else`` of its own, and is not reported.

    python -m pybrokkr.fallbacks --compile-commands build/compile_commands.json

parses every source of the project that the build compiles (with its flags), and reports each finding in the project's
own files (its headers included), by shape, file and function. It only reports.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import clang.cindex as ci

SHAPES = {
    "skipped capability": "if constexpr (requires ...) without else",
    "discarded failure": "catch with an empty handler",
    "substituted value": "value_or",
}
# The directories of a project that are not its own code.
EXCLUDED_DIRECTORIES = frozenset({"build", ".venv", "venv", "dependencies-install", "_deps", "third_party", "external"})
FUNCTIONS = {
    ci.CursorKind.FUNCTION_DECL,
    ci.CursorKind.CXX_METHOD,
    ci.CursorKind.FUNCTION_TEMPLATE,
    ci.CursorKind.CONSTRUCTOR,
    ci.CursorKind.DESTRUCTOR,
    ci.CursorKind.CONVERSION_FUNCTION,
}
# The classes whose name a member function's finding carries.
CLASSES = {
    ci.CursorKind.CLASS_DECL,
    ci.CursorKind.STRUCT_DECL,
    ci.CursorKind.CLASS_TEMPLATE,
    ci.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION,
}
# The statements that leave where they stand: a then statement ending in one has the code after the if as its else.
LEAVING = {ci.CursorKind.RETURN_STMT, ci.CursorKind.BREAK_STMT, ci.CursorKind.CONTINUE_STMT}
# The children of an if before its else: its condition and its then statement.
CONDITION_AND_THEN = 2
# The characters of code a finding quotes.
QUOTED = 90
# The parse errors written per source before going on.
ERRORS_WRITTEN = 3


@dataclass(frozen=True, order=True)
class Finding:
    """A finding: its shape, where it is, the function it is in, and the code it quotes."""

    shape: str
    file: str
    line: int
    function: str
    code: str


def say(line: str) -> None:
    """Writes one line of the report."""
    sys.stdout.write(line + "\n")


def own(path: str | None, root: Path) -> str | None:
    """`path` relative to `root`, where it is the project's own file; else none."""
    if path is None:
        return None
    try:
        relative = Path(path).resolve().relative_to(root)
    except ValueError:
        return None
    return None if relative.parts and relative.parts[0] in EXCLUDED_DIRECTORIES else str(relative)


def resource_dir() -> str:
    """Clang's own headers (stddef.h, ...), which the PyPI wheel does not carry: those of the clang installed."""
    clang = shutil.which("clang++") or shutil.which("clang")
    if clang is None:
        sys.exit("pybrokkr.fallbacks: needs clang++ for clang's own headers (clang++ -print-resource-dir)")
    return subprocess.run([clang, "-print-resource-dir"], capture_output=True, text=True, check=True).stdout.strip()


def flags_of(entry: dict[str, str]) -> list[str]:
    """The flags of a compile command that parsing needs: includes, definitions and the standard."""
    words = shlex.split(entry["command"]) if "command" in entry else list(entry["arguments"])
    flags: list[str] = []
    take_next = False
    for word in words[1:]:
        if take_next:
            flags.append(word)
            take_next = False
        elif word in {"-isystem", "-iquote", "-include", "-I", "-D"}:
            flags.append(word)
            take_next = True
        elif word.startswith(("-I", "-isystem", "-iquote", "-D", "-std")):
            flags.append(word)
    return flags


def kind_of(cursor: ci.Cursor) -> ci.CursorKind | None:
    """The kind of `cursor`; none for a kind newer than these Python bindings, which no rule is about."""
    try:
        return cursor.kind
    except ValueError:
        return None


def tokens_of(cursor: ci.Cursor) -> list[str]:
    """The spellings of the tokens of `cursor`."""
    return [token.spelling for token in cursor.get_tokens()]


def leaves(statement: ci.Cursor) -> bool:
    """Whether `statement` ends by leaving where it stands (return, throw, break, continue), or a block's last does."""
    if kind_of(statement) == ci.CursorKind.COMPOUND_STMT:
        children = list(statement.get_children())
        return bool(children) and leaves(children[-1])
    return kind_of(statement) in LEAVING or tokens_of(statement)[:1] == ["throw"]


def branches(statement: ci.Cursor) -> tuple[ci.Cursor | None, ci.Cursor | None]:
    """The then and else statements of an if (else none where it has none)."""
    children = list(statement.get_children())
    tokens = list(statement.get_tokens())
    # The then statement is the last child but one where an `else` follows it, else the last.
    if len(children) >= CONDITION_AND_THEN:
        then = children[-2]
        # A then statement's extent ends before its `;`.
        after = [token.spelling for token in tokens if token.extent.start.offset >= then.extent.end.offset]
        after = after[1:] if after[:1] == [";"] else after
        if after[:1] == ["else"]:
            return then, children[-1]
    return (children[-1] if children else None), None


def quote(cursor: ci.Cursor) -> str:
    """The first characters of `cursor`'s code, on one line."""
    text = " ".join(tokens_of(cursor))
    return text if len(text) <= QUOTED else text[: QUOTED - 3] + "..."


def condition_of(statement: ci.Cursor, then: ci.Cursor | None) -> list[str]:
    """The tokens of an if before its then statement: `if constexpr (` and its condition."""
    end = then.extent.start.offset if then is not None else statement.extent.end.offset
    return [token.spelling for token in statement.get_tokens() if token.extent.start.offset < end]


def required(condition: list[str]) -> bool:
    """Whether a condition requires a capability: a requires expression, not negated."""
    return any(spelled == "requires" and (at == 0 or condition[at - 1] != "!") for at, spelled in enumerate(condition))


def check(cursor: ci.Cursor) -> Iterator[tuple[str, str]]:
    """The fallbacks `cursor` is, with the code each quotes."""
    kind = kind_of(cursor)
    if kind == ci.CursorKind.IF_STMT:
        then, otherwise = branches(cursor)
        condition = condition_of(cursor, then)
        skipped = otherwise is None and then is not None and not leaves(then)
        if condition[:2] == ["if", "constexpr"] and required(condition) and skipped:
            yield "skipped capability", quote(cursor)
    elif kind == ci.CursorKind.CXX_CATCH_STMT:
        handler = [child for child in cursor.get_children() if kind_of(child) == ci.CursorKind.COMPOUND_STMT]
        if handler and not list(handler[-1].get_children()):
            yield "discarded failure", quote(cursor)
    elif kind == ci.CursorKind.MEMBER_REF_EXPR and cursor.spelling == "value_or":
        yield "substituted value", quote(cursor)


def walk(cursor: ci.Cursor, root: Path, function: str, found: list[Finding]) -> None:
    """Collects the findings under `cursor`, in the project's own files, with the function each is in."""
    for child in cursor.get_children():
        file = own(child.location.file.name if child.location.file else None, root)
        if file is None:
            continue
        inner = function
        kind = kind_of(child)
        if kind in FUNCTIONS:
            parent = child.semantic_parent
            in_class = parent is not None and kind_of(parent) in CLASSES
            inner = f"{parent.spelling}::{child.spelling}" if parent is not None and in_class else child.spelling
        # Code a macro expands to (a test framework's, a binding's) has no tokens of its own: not the project's.
        if not any(True for _ in child.get_tokens()):
            continue
        for shape, code in check(child):
            found.append(Finding(shape, file, child.location.line, inner, code))
        walk(child, root, inner, found)


def findings_of(job: tuple[dict[str, str], str, str]) -> tuple[list[Finding], list[str]]:
    """The findings of one compile command, and its parse errors."""
    entry, root, resource = job
    os.chdir(entry["directory"])
    try:
        unit = ci.Index.create().parse(entry["file"], args=[*flags_of(entry), "-resource-dir", resource, "-x", "c++"])
    except ci.TranslationUnitLoadError as error:
        # Reported with the parse errors: its findings are missing.
        return [], [f"{entry['file']}: libclang could not parse it ({error})"]
    errors = [f"{entry['file']}: {each}" for each in unit.diagnostics if each.severity >= ci.Diagnostic.Error]
    found: list[Finding] = []
    walk(unit.cursor, Path(root), "", found)
    return found, errors[:ERRORS_WRITTEN]


def main() -> int:
    """Reports the silent fallbacks of the project; 0 always (report only)."""
    parser = argparse.ArgumentParser(prog="python -m pybrokkr.fallbacks", description="Silent fallbacks in C++ code.")
    parser.add_argument("--compile-commands", required=True, help="the build's compile_commands.json")
    parser.add_argument("--root", default=".", help="the project, whose own files are checked (default: .)")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="sources parsed at once")
    arguments = parser.parse_args()

    root = Path(arguments.root).resolve()
    entries: list[dict[str, str]] = json.loads(Path(arguments.compile_commands).read_text())
    sources = [each for each in entries if own(str(Path(each["directory"]) / each["file"]), root) is not None]
    resource = resource_dir()
    found: set[Finding] = set()
    errors: list[str] = []
    with ProcessPoolExecutor(max_workers=arguments.jobs) as pool:
        for each, failed in pool.map(findings_of, [(entry, str(root), resource) for entry in sources]):
            found.update(each)
            errors += failed
    for line in errors:
        sys.stderr.write(f"pybrokkr.fallbacks: parse error: {line}\n")
    say(f"{len(sources)} sources parsed, {len(errors)} with parse errors")
    say(f"fallbacks: {len(found)}")
    for shape, spelled in SHAPES.items():
        of_shape = sorted(each for each in found if each.shape == shape)
        say(f"{shape} ({spelled}): {len(of_shape)}")
        for each in of_shape:
            say(f"  {each.file}:{each.line}  {each.function or '-'}")
            say(f"      {each.code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
