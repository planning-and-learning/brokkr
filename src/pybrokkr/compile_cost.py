# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile cost per translation unit, as the template rules measure it (docs/template_rules.rst, rule 13).

Record a build: every compile's wall time and the compiler's peak memory (max RSS), one line per object, through
CMake's compiler launcher:

    cmake -B build "-DCMAKE_CXX_COMPILER_LAUNCHER=python;-m;pybrokkr.compile_cost;record;/tmp/cost.log"
    ninja -C build clean && ninja -C build

Summarize it, or compare two (the largest drops and rises by object):

    python -m pybrokkr.compile_cost summary /tmp/before.log [/tmp/after.log]

Find what the build compiles again and again: the functions each object defines as weak symbols (implicit template
instantiations, and inline functions not inlined everywhere), summed by template over all objects. A template the
library instantiates explicitly that still shows up weak in other objects is one those objects do not see declared
(an opt-in extern list they do not include, rule 9):

    python -m pybrokkr.compile_cost weak build
"""

import argparse
import collections
import re
import resource
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

GIB = 1024 * 1024  # KiB per GiB
NM_FIELDS = 4  # address, size, type, name


def emit(line: str) -> None:
    """Print one line of a report."""
    sys.stdout.write(line + "\n")


def record(log: str, command: list[str]) -> int:
    """Run the compile command; append its object, seconds and the compiler's max RSS (KiB) to the log."""
    start = time.monotonic()
    returncode = subprocess.run(command, check=False).returncode
    seconds = time.monotonic() - start
    kib = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss  # KiB on Linux
    output = command[command.index("-o") + 1] if "-o" in command else command[-1]
    with Path(log).open("a") as out:  # one short line per write: appends from parallel compiles do not interleave
        out.write(f"{output}\t{seconds:.2f}\t{kib}\n")
    return returncode


def load(log: str) -> dict[str, tuple[float, float]]:
    """Read a log: object -> (seconds, GiB); a later line for the same object replaces an earlier one."""
    costs: dict[str, tuple[float, float]] = {}
    for line in Path(log).read_text().splitlines():
        output, seconds, kib = line.split("\t")
        costs[output] = (float(seconds), int(kib) / GIB)
    return costs


def describe(name: str, costs: dict[str, tuple[float, float]]) -> str:
    """Totals and distribution of a log, in one line."""
    seconds = [t for t, _ in costs.values()]
    memory = [m for _, m in costs.values()]
    return (
        f"{name}: {len(costs)} TUs, CPU {sum(seconds) / 60:.1f} min, summed memory {sum(memory):.1f} GiB, "
        f"max {max(memory):.2f} GiB, median {statistics.median(memory) * 1024:.0f} MiB, above 1 GiB "
        f"{sum(m > 1 for m in memory)}, slowest {max(seconds):.0f} s"
    )


def short(output: str) -> str:
    """An object's path from its target's directory on."""
    return output.rpartition("CMakeFiles/")[2]


def summary(before: str, after: str | None, rows: int) -> None:
    """Print a log's totals and heaviest objects, or two logs' totals and the largest changes between them."""
    first = load(before)
    emit(describe("before" if after else "build", first))
    if after is None:
        for output, (seconds, memory) in sorted(first.items(), key=lambda item: -item[1][1])[:rows]:
            emit(f"  {memory:5.2f} GiB {seconds:5.0f} s  {short(output)}")
        return
    second = load(after)
    emit(describe("after", second))
    changes = sorted((second[o][1] - first[o][1], second[o][0] - first[o][0], o) for o in first.keys() & second.keys())
    for title, chosen in (("largest drops", changes[:rows]), ("largest rises", changes[::-1][:rows])):
        emit(f"{title}:")
        for memory, seconds, output in chosen:
            emit(f"  {memory * 1024:+7.0f} MiB {seconds:+5.0f} s  {short(output)}")


def template_name(symbol: str) -> str:
    """A demangled name with every template argument list and parameter list emptied: one name per template."""
    out: list[str] = []
    depth = 0
    for ch in symbol:
        if ch == "<":
            if depth == 0:
                out.append("<>")
            depth += 1
        elif ch == ">":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(ch)
    return re.sub(r"\(.*\)", "()", "".join(out))


def weak(build: str, rows: int) -> None:
    """Print the weak definitions in a build's objects, summed by template: objects, copies, code bytes."""
    nm = shutil.which("nm")
    if nm is None:
        message = "weak: nm (binutils) is not on PATH"
        raise SystemExit(message)
    objects = [str(p) for p in Path(build).rglob("*.o")]
    size: collections.Counter[str] = collections.Counter()
    copies: collections.Counter[str] = collections.Counter()
    users: dict[str, set[str]] = collections.defaultdict(set)
    for obj in objects:
        command = [nm, "-C", "-S", "--defined-only", obj]
        listing = subprocess.run(command, capture_output=True, text=True, check=True).stdout
        for line in listing.splitlines():
            fields = line.split(" ", 3)
            if len(fields) == NM_FIELDS and fields[2] in ("W", "w"):
                name = template_name(fields[3])
                size[name] += int(fields[1], 16)
                copies[name] += 1
                users[name].add(obj)
    emit(f"{len(objects)} objects; by code size: objects, copies, bytes, template")
    for name, total in size.most_common(rows):
        emit(f"  {len(users[name]):5d} {copies[name]:7d} {total / 1e6:7.2f} MB  {name[:140]}")


def main() -> int:
    """Run the command line."""
    summary_line = (__doc__ or "").partition("\n\n")[0]
    parser = argparse.ArgumentParser(prog="python -m pybrokkr.compile_cost", description=summary_line)
    commands = parser.add_subparsers(dest="command", required=True)
    recording = commands.add_parser("record", help="compiler launcher: run the command, log its time and max RSS")
    recording.add_argument("log")
    recording.add_argument("compile", nargs=argparse.REMAINDER)
    summarizing = commands.add_parser("summary", help="totals of a log, or the changes between two")
    summarizing.add_argument("before")
    summarizing.add_argument("after", nargs="?")
    summarizing.add_argument("--rows", type=int, default=15)
    scanning = commands.add_parser("weak", help="weak definitions in a build's objects, summed by template")
    scanning.add_argument("build")
    scanning.add_argument("--rows", type=int, default=40)
    arguments = parser.parse_args()
    if arguments.command == "record":
        return record(arguments.log, arguments.compile)
    if arguments.command == "summary":
        summary(arguments.before, arguments.after, arguments.rows)
    else:
        weak(arguments.build, arguments.rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
