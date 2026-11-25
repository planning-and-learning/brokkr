# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""T20 (template-named-type-lists) of docs/template_rules.rst, checked with libclang (``pybrokkr[fallbacks]``).

Every source of the compile database parses as it is compiled (a unity or generated source too, with what it includes
before the repository's own files); the declarations written in the repository's own files (each once, however many
sources include it) are checked: the type each declares (an alias's, a variable's, a
field's, a parameter's, a function's result and parameters), as the compiler spells it in symbol names (canonical).
Where a class template specialization in it takes a type list as an argument, the declaration is a finding: it is to
name a class deriving from the list (or from the specialization) instead. Two declarations carry such a name and are
not findings: a member of the specialization itself (its own name is its members' prefix; a library instantiates
them, :rule:`T1`; in a template, a member of the template), and an alias in a class that names one of its bases. A
template's pattern is read too: a specialization it writes over a list of its own parameters
(``HeldPart<Derived, mp_list<urd::index<Ts>...>>``) spells that list in every instantiation's names, and is a finding
where it is written.

A type list is a specialization of ``boost::mp11::mp_list``, or of a class template that names itself its ``List``
(``using List = <its name>;``: yggdrasil's Symbols, Relations, Builders). A class deriving from one names its base, not
itself, and is not a list.

    python -m pybrokkr.rules T20 [-C <repository>] [--compile-commands <file>]
"""

import functools
import json
import sys
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import repeat
from pathlib import Path

import clang.cindex as ci

from pybrokkr.rules.layout.files import Finding, tracked
from pybrokkr.rules.schema.records import database, parse

DECLARATIONS = {
    ci.CursorKind.TYPE_ALIAS_DECL,
    ci.CursorKind.TYPEDEF_DECL,
    ci.CursorKind.VAR_DECL,
    ci.CursorKind.FIELD_DECL,
    ci.CursorKind.PARM_DECL,
    ci.CursorKind.FUNCTION_DECL,
    ci.CursorKind.CXX_METHOD,
    ci.CursorKind.CONSTRUCTOR,
    ci.CursorKind.DESTRUCTOR,
    ci.CursorKind.CONVERSION_FUNCTION,
}
CLASSES = {
    ci.CursorKind.STRUCT_DECL,
    ci.CursorKind.CLASS_DECL,
    ci.CursorKind.CLASS_TEMPLATE,
    ci.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION,
}
SCOPES = {ci.CursorKind.NAMESPACE, ci.CursorKind.LINKAGE_SPEC, ci.CursorKind.UNEXPOSED_DECL}
INDIRECTIONS = {ci.TypeKind.POINTER, ci.TypeKind.LVALUEREFERENCE, ci.TypeKind.RVALUEREFERENCE}
# The error of a source libclang crashes on (its parse fails without a diagnostic, the binding's
# TranslationUnitLoadError; or its cursors cannot be read): clang's fault, not the source's, and the source is not
# checked (reported on stderr).
LOAD_FAILED = "Error parsing translation unit."
CRASHED = "libclang crashed"
# How deep a type's arguments, pointees and enclosing classes are followed: no type of the libraries nests deeper, and a
# recursive one stops here.
DEPTH = 32


def qualified(cursor: ci.Cursor) -> str:
    """The qualified name of `cursor`'s declaration: its namespaces' and classes' names and its own."""
    names: list[str] = []
    current: ci.Cursor | None = cursor
    while current is not None and current.kind != ci.CursorKind.TRANSLATION_UNIT:
        if current.spelling:
            names.append(current.spelling)
        current = current.semantic_parent
    return "::".join(reversed(names))


def template_of(declaration: ci.Cursor) -> ci.Cursor | None:
    """The class template `declaration` specializes, none where it specializes none."""
    template = ci.conf.lib.clang_getSpecializedCursorTemplate(declaration)
    return None if template is None or template.kind == ci.CursorKind.NO_DECL_FOUND else template


@functools.cache
def names_itself_list(name: str, tokens: tuple[str, ...]) -> bool:
    """Whether a class template `name` of `tokens` declares ``using List = <name>;``."""
    return any(tokens[i : i + 5] == ("using", "List", "=", name, ";") for i in range(len(tokens) - 4))


def specialized(kind: ci.Type) -> ci.Cursor | None:
    """The class template `kind` (canonical) specializes: of a class, or of a template's pattern (dependent); none."""
    if kind.kind not in {ci.TypeKind.RECORD, ci.TypeKind.UNEXPOSED}:
        return None
    declaration = kind.get_declaration()
    if declaration.kind == ci.CursorKind.CLASS_TEMPLATE:
        return declaration
    if declaration.kind == ci.CursorKind.NO_DECL_FOUND:
        return None
    return template_of(declaration)


def is_list(kind: ci.Type) -> bool:
    """Whether `kind` (canonical) is a type list: an mp_list, or a class template naming itself its List."""
    template = specialized(kind)
    if template is None:
        return False
    if qualified(template) == "boost::mp11::mp_list":
        return True
    return names_itself_list(template.spelling, tuple(token.spelling for token in template.get_tokens()))


def carriers(kind: ci.Type, depth: int = 0) -> Iterator[ci.Type]:
    """The class template specializations in `kind` (canonical) that take a type list as an argument.

    These include `kind` itself, its arguments', its pointee's, its result's and parameters' (a function), and its
    enclosing classes' (a nested class).
    """
    if depth > DEPTH:
        return
    if kind.kind in INDIRECTIONS:
        yield from carriers(kind.get_pointee().get_canonical(), depth + 1)
    elif kind.kind == ci.TypeKind.FUNCTIONPROTO:
        yield from carriers(kind.get_result().get_canonical(), depth + 1)
        for argument in kind.argument_types():
            yield from carriers(argument.get_canonical(), depth + 1)
    elif specialized(kind) is not None or kind.kind == ci.TypeKind.RECORD:
        declaration = kind.get_declaration()
        arguments = [kind.get_template_argument_type(i) for i in range(max(kind.get_num_template_arguments(), 0))]
        arguments = [each.get_canonical() for each in arguments if each.kind != ci.TypeKind.INVALID]
        if not is_list(kind) and any(is_list(each) for each in arguments):
            yield kind
        for each in arguments:
            yield from carriers(each, depth + 1)
        parent = declaration.semantic_parent
        if parent is not None and parent.kind in CLASSES:
            yield from carriers(parent.type.get_canonical(), depth + 1)


def declared_type(cursor: ci.Cursor) -> ci.Type:
    """The type `cursor` declares: an alias's underlying type, a function's type, a variable's or field's type."""
    if cursor.kind in {ci.CursorKind.TYPE_ALIAS_DECL, ci.CursorKind.TYPEDEF_DECL}:
        return cursor.underlying_typedef_type.get_canonical()
    return cursor.type.get_canonical()


def exempt(cursor: ci.Cursor, carrier: ci.Type) -> bool:
    """Whether `cursor` may name `carrier`: written in it, or an alias in a class that names one of its bases.

    Written in it is in a member, a member's parameter or a nested class of it; in a template, of the template.
    """
    template = specialized(carrier)
    parent = cursor.semantic_parent
    if (
        cursor.kind in {ci.CursorKind.TYPE_ALIAS_DECL, ci.CursorKind.TYPEDEF_DECL}
        and parent is not None
        and parent.kind in CLASSES
        and any(
            each.kind == ci.CursorKind.CXX_BASE_SPECIFIER and each.type.get_canonical().spelling == carrier.spelling
            for each in parent.get_children()
        )
    ):
        return True
    while parent is not None and parent.kind != ci.CursorKind.TRANSLATION_UNIT:
        if parent.kind in CLASSES:
            if parent.type.get_canonical().spelling == carrier.spelling:
                return True
            owning = parent if parent.kind == ci.CursorKind.CLASS_TEMPLATE else template_of(parent)
            if template is not None and owning is not None and template.get_usr() == owning.get_usr():
                return True
        parent = parent.semantic_parent
    return False


def dependent(kind: ci.Type) -> bool:
    """Whether `kind` (canonical) depends on a template parameter."""
    return "type-parameter-" in kind.spelling


def kind_of(cursor: ci.Cursor) -> ci.CursorKind | None:
    """`cursor`'s kind; none for a kind newer than the Python binding knows (an expression, as all such kinds are)."""
    try:
        return cursor.kind
    except ValueError:
        return None


def declarations(cursor: ci.Cursor, own: set[Path]) -> Iterator[ci.Cursor]:
    """The declarations written in the files `own` under `cursor`, in preorder; function bodies too."""
    for child in cursor.get_children():
        file = child.location.file
        if file is None or Path(file.name).resolve() not in own:
            if child.kind in SCOPES:
                yield from declarations(child, own)
            continue
        for node in child.walk_preorder():
            if kind_of(node) in DECLARATIONS:
                yield node


def upstream(kind: ci.Type, own: set[Path], depth: int = 0) -> Iterator[ci.Type]:
    """The carriers `kind` (as written) names through an alias declared outside the files `own`: another library's."""
    if depth > DEPTH:
        return
    if kind.kind == ci.TypeKind.ELABORATED:
        yield from upstream(kind.get_named_type(), own, depth + 1)
    elif kind.kind == ci.TypeKind.TYPEDEF:
        file = kind.get_declaration().location.file
        if file is not None and Path(file.name).resolve() not in own:
            yield from carriers(kind.get_canonical())
    elif kind.kind in INDIRECTIONS:
        yield from upstream(kind.get_pointee(), own, depth + 1)
    elif kind.kind == ci.TypeKind.FUNCTIONPROTO:
        yield from upstream(kind.get_result(), own, depth + 1)
        for argument in kind.argument_types():
            yield from upstream(argument, own, depth + 1)
    else:
        for i in range(max(kind.get_num_template_arguments(), 0)):
            argument = kind.get_template_argument_type(i)
            if argument.kind != ci.TypeKind.INVALID:
                yield from upstream(argument, own, depth + 1)


@dataclass(frozen=True)
class Named:
    """A carrier a declaration names: its identity (USR), its template, where, and whether an alias there defines it."""

    carrier: str
    template: str
    file: str
    line: int
    defines: bool


def written_type(cursor: ci.Cursor) -> ci.Type:
    """The type `cursor` declares as written: an alias's underlying type, a function's or variable's type."""
    if cursor.kind in {ci.CursorKind.TYPE_ALIAS_DECL, ci.CursorKind.TYPEDEF_DECL}:
        return cursor.underlying_typedef_type
    return cursor.type


def source_findings(
    repository: Path, source: Path, flags: list[str], resource: str, own: set[Path]
) -> tuple[list[Named], set[str], str]:
    """The carriers named by the declarations of the files `own` that `source` (parsed with `flags`) holds.

    Also those they name only through another library's alias, and the error where it does not parse (libclang's crash
    included).
    """
    unit, error = parse(source, flags, resource)
    if unit is None:
        return [], set(), CRASHED if error == LOAD_FAILED else error
    named: list[Named] = []
    others: set[str] = set()
    try:
        for cursor in declarations(unit.cursor, own):
            kind = declared_type(cursor)
            found = [each for each in carriers(kind) if not exempt(cursor, each)]
            if not found:
                continue
            others.update(each.get_declaration().get_usr() for each in upstream(written_type(cursor), own))
            file = cursor.location.file
            if file is None:
                continue
            where = Path(file.name).resolve().relative_to(repository).as_posix()
            alias = cursor.kind in {ci.CursorKind.TYPE_ALIAS_DECL, ci.CursorKind.TYPEDEF_DECL}
            for each in found:
                template = specialized(each)
                name = qualified(template) if template is not None else each.spelling
                # A class's specialization is one type wherever it is named; a pattern's, one per place it is written.
                if dependent(each):
                    identity = f"{where}:{cursor.location.line}:{each.spelling}"
                else:
                    identity = each.get_declaration().get_usr()
                defines = alias and kind.spelling == each.spelling
                named.append(Named(identity, name, where, cursor.location.line, defines))
    except ValueError:  # libclang crashed parsing: its cursors are not readable
        return [], set(), CRASHED
    return named, others, ""


def check(repository: Path, compile_commands: Path, jobs: int | None = None) -> list[Finding]:
    """The findings of T20 in `repository`: each specialization over a type list its own declarations name, once.

    It is reported where an alias of the repository defines it, else where it is first named; one named only through
    another library's alias is that library's finding. A source that does not parse is a finding; one libclang
    crashes on is not checked, and said so on stderr.
    """
    root = repository.resolve()
    data = database(root, compile_commands)
    own = {(root / each).resolve() for each in tracked(root) if each.endswith((".hpp", ".cpp", ".h"))}
    # The sources as the build compiles them: a source a unity or generated source includes is read through that one,
    # after what it includes first (a container's header before the tests over it); a dependency fetched into the build
    # (_deps) holds none of the repository's declarations.
    entries = json.loads(compile_commands.read_text())
    compiled = {(Path(entry["directory"]) / entry["file"]).resolve() for entry in entries}
    sources = sorted(each for each in compiled if each in data.flags and "_deps" not in each.parts)
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        read = list(
            pool.map(
                source_findings,
                repeat(root),
                sources,
                (data.flags[each] for each in sources),
                repeat(data.resource),
                repeat(own),
            )
        )
    findings: list[Finding] = []
    for source, (_, _, error) in zip(sources, read, strict=True):
        if error == CRASHED:
            where = source.relative_to(root).as_posix()
            sys.stderr.write(f"{repository}/{where}: T20: not checked, libclang crashed on it\n")
        elif error:
            findings.append(Finding(source.relative_to(root).as_posix(), f"does not parse: {error}"))
    others: set[str] = set()
    for _, more, _ in read:
        others |= more
    first: dict[str, Named] = {}
    for named, _, _ in read:
        for each in named:
            if each.carrier in others:
                continue
            known = first.get(each.carrier)
            rank = (not each.defines, each.file, each.line)
            if known is None or rank < (not known.defines, known.file, known.line):
                first[each.carrier] = each
    # One finding per place: an alias template instantiated over several lists defines each of them there.
    places = sorted({(each.file, each.line, each.defines, each.template) for each in first.values()})
    for file, line, defines, template in places:
        how = "defines" if defines else "names"
        findings.append(Finding(f"{file}:{line}", f"{how} {template}<...> over a type list: derive a class"))
    return findings
