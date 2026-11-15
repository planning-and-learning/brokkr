# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""The record schemas of docs/schema_rules.rst (S1, S2, S3), checked with libclang (``pybrokkr[fallbacks]``).

Each tracked ``include/<lib>/**/*_data.hpp`` and its ``*_view.hpp`` parse as a translation unit that includes the header
alone, with the include paths and the standard of one compile command of the repository's compile database. A header
that does not parse is a finding, not a skip: what it holds is not known.

    python -m pybrokkr.rules S1 S2 S3 [-C <repository>] [--compile-commands <file>]
"""

import functools
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import clang.cindex as ci

from pybrokkr.rules.coding.fallbacks import flags_of, resource_dir
from pybrokkr.rules.layout.files import Finding, tracked

METHODS = ["fields", "identifying_members", "cista_members"]
# The kinds of a specialization's children that are its template arguments and parameters, not its members.
ARGUMENTS = {
    ci.CursorKind.TEMPLATE_TYPE_PARAMETER,
    ci.CursorKind.TEMPLATE_NON_TYPE_PARAMETER,
    ci.CursorKind.TEMPLATE_TEMPLATE_PARAMETER,
    ci.CursorKind.TYPE_REF,
    ci.CursorKind.TEMPLATE_REF,
    ci.CursorKind.NAMESPACE_REF,
    ci.CursorKind.DECL_REF_EXPR,
    ci.CursorKind.CXX_ACCESS_SPEC_DECL,
}


@dataclass(frozen=True)
class Record:
    """A specialization of urd::data in a data header: its tag as written, its fields, where it is."""

    tag: str
    fields: list[str]
    line: int
    file: str = ""
    parameters: tuple[str, ...] = ()


def tag_of(spelling: str, template: str) -> str:
    """The first template argument of `template`<...> in `spelling`, without namespaces: ``Condition<AndTag>``."""
    inner = spelling[spelling.index(f"{template}<") + len(template) + 1 :]
    depth, end = 0, len(inner)
    for position, char in enumerate(inner):
        depth += {"<": 1, ">": -1}.get(char, 0)
        if depth < 0 or (depth == 0 and char == ","):
            end = position
            break
    return re.sub(r"(?:\b\w+)?::", "", inner[:end]).replace(" ", "")


def members_named(tokens: list[str]) -> list[str]:
    """The members a list names by pointer, in order: the last name of each ``&data::m`` before the next ``,``."""
    names: list[str] = []
    depth, taking, last = 0, False, ""
    # The lexer reads ">>" as one token; a list closes two templates with it.
    split = [part for word in tokens for part in ([">", ">"] if word == ">>" else [word])]
    for word in split:
        if word == "&" and depth == 0:
            taking, last = True, ""
        elif taking and depth == 0 and word in {",", ">", ")"}:
            names.append(last)
            taking = False
        if word == "<" and taking:
            depth += 1
        elif word == ">" and depth > 0:
            depth -= 1
        elif taking and re.fullmatch(r"\w+", word):
            last = word
    return names


def parse(file: Path, flags: list[str], resource: str) -> tuple[ci.TranslationUnit | None, str]:
    """`file` parsed with `flags`: a source as it is, a header as a translation unit that includes it alone.

    None and the first error where it does not parse.
    """
    source = file.suffix == ".cpp"
    probe = file if source else file.with_name("__brokkr_schema__.cpp")
    try:
        unit = ci.Index.create().parse(
            str(probe),
            args=[*flags, "-resource-dir", resource, "-x", "c++"],
            unsaved_files=[] if source else [(str(probe), f'#include "{file}"\n')],
        )
    except ci.TranslationUnitLoadError as error:
        return None, str(error)
    errors = [each for each in unit.diagnostics if each.severity >= ci.Diagnostic.Error]
    return (None, errors[0].spelling) if errors else (unit, "")


def declared_in(cursor: ci.Cursor, header: Path) -> bool:
    """Whether `cursor` is written in `header`."""
    return cursor.location.file is not None and Path(cursor.location.file.name) == header


def top_level(cursor: ci.Cursor, header: Path) -> Iterator[ci.Cursor]:
    """The declarations of `header` at namespace scope, through its namespaces."""
    for child in cursor.get_children():
        if not declared_in(child, header):
            continue
        if child.kind == ci.CursorKind.NAMESPACE:
            yield from top_level(child, header)
        else:
            yield child


def in_urd(cursor: ci.Cursor, name: str) -> bool:
    """Whether `cursor` defines a class or a specialization named `name` in namespace urd."""
    parent = cursor.semantic_parent
    return (
        cursor.kind in {ci.CursorKind.STRUCT_DECL, ci.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
        and cursor.spelling == name
        and parent is not None
        and parent.spelling == "urd"
        and cursor.is_definition()
    )


# The special members every record declares, in order (S1): it is moved, never copied.
MOVE_ONLY = [
    "copy constructor deleted",
    "copy assignment deleted",
    "move constructor defaulted",
    "move assignment defaulted",
    "destructor defaulted",
]


def copy_findings(special: list[ci.Cursor], copyable: list[ci.Cursor]) -> list[str]:
    """What S1 does not allow of how a record is copied: the five (move-only), or copyable() with its check."""
    forms = [form(each) for each in special]
    if copyable:
        words = " ".join(token.spelling for token in copyable[0].get_tokens())
        checked = "static_assert ( std :: is_trivially_copyable_v < data >" in words and "return true ;" in words
        found = [] if checked else ["declares copyable() without static_assert(std::is_trivially_copyable_v<data>, …)"]
        return found + ([f"declares copyable() and {forms}"] if special else [])
    return [] if forms == MOVE_ONLY else [f"declares {forms}, neither {MOVE_ONLY} nor copyable()"]


def is_special(cursor: ci.Cursor) -> bool:
    """Whether `cursor` is a copy or move constructor, a copy or move assignment, or the destructor."""
    return (
        cursor.kind == ci.CursorKind.DESTRUCTOR
        or (cursor.kind == ci.CursorKind.CONSTRUCTOR and (cursor.is_copy_constructor() or cursor.is_move_constructor()))
        or cursor.is_copy_assignment_operator_method()
        or cursor.is_move_assignment_operator_method()
    )


def form(cursor: ci.Cursor) -> str:
    """A special member as MOVE_ONLY names it: which one, and whether it is deleted or defaulted."""
    if cursor.kind == ci.CursorKind.DESTRUCTOR:
        which = "destructor"
    elif cursor.kind == ci.CursorKind.CONSTRUCTOR:
        which = "copy constructor" if cursor.is_copy_constructor() else "move constructor"
    else:
        which = "copy assignment" if cursor.is_copy_assignment_operator_method() else "move assignment"
    how = "deleted" if cursor.is_deleted_method() else "defaulted" if cursor.is_default_method() else "user-defined"
    return f"{which} {how}"


def list_findings(methods: list[ci.Cursor], names: list[str], *, indexed: bool) -> list[str]:
    """What S1 does not allow of the member lists: fields(), identifying_members() and cista_members() of `names`."""
    found: list[str] = []
    bodies = {each.spelling: [token.spelling for token in each.get_tokens()] for each in methods}
    if "fields" in bodies:
        listed = re.findall(r'field < "(\w+)" ,', " ".join(bodies["fields"]))
        if listed != names or members_named(bodies["fields"]) != names:
            found.append(f"fields() names {listed}, not the fields {names} under their names")
    if "identifying_members" in bodies and "members_of ( fields ( ) )" not in " ".join(bodies["identifying_members"]):
        # Which fields identify the record is its semantics; that they are fields is its schema.
        named = members_named(bodies["identifying_members"])
        if not named or not set(named) <= set(names):
            found.append(f"identifying_members() names {named}, not some of the fields {names}")
    stored = ["index", *names] if indexed else names
    if "cista_members" in bodies and members_named(bodies["cista_members"]) != stored:
        found.append(f"cista_members() names {members_named(bodies['cista_members'])}, not {stored}")
    return found


def record_findings(cursor: ci.Cursor) -> tuple[Record, list[str]]:
    """The record `cursor` defines, and what of it S1 does not allow."""
    tag = tag_of(cursor.displayname or cursor.type.spelling, "data")
    say: list[str] = []
    members = [each for each in cursor.get_children() if each.kind not in ARGUMENTS]
    kinds = [each.kind for each in members]
    if ci.CursorKind.CXX_BASE_SPECIFIER in kinds:
        say.append("has a base class")
    fields = [each for each in members if each.kind == ci.CursorKind.FIELD_DECL]
    special = [each for each in members if is_special(each)]
    constructors = [each for each in members if each.kind == ci.CursorKind.CONSTRUCTOR and each not in special]
    methods = [
        each
        for each in members
        if each.kind in {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE} and each not in special
    ]
    known = [*fields, *constructors, *methods, *special]
    others = [each for each in members if each not in known and each.kind != ci.CursorKind.CXX_BASE_SPECIFIER]
    say.extend(f"declares {each.kind.name.lower()} {each.spelling}" for each in others)
    # Whether a record has an index is its semantics (an interned one does: interning writes it); where it has one, the
    # index is its first member, of type urd::index<T>.
    indexed = any(each.spelling == "index" for each in fields)
    if indexed and (fields[0].spelling != "index" or "index<" not in fields[0].type.spelling):
        say.append("has an index that is not its first member, urd::index<T> index")
    names = [each.spelling for each in fields if each.spelling != "index"]
    order = [each.kind for each in members if each.kind != ci.CursorKind.CXX_BASE_SPECIFIER]
    first_constructor = next((i for i, kind in enumerate(order) if kind == ci.CursorKind.CONSTRUCTOR), len(order))
    if any(kind == ci.CursorKind.FIELD_DECL for kind in order[first_constructor:]):
        say.append("declares a field after a constructor")
    shapes = sorted(len(list(each.get_arguments())) for each in constructors)
    defaulted = any(each.is_default_constructor() and each.is_default_method() for each in constructors)
    if shapes != [0, len(names)] or not defaulted:
        say.append(f"has {len(constructors)} constructors, not data() = default and one from the {len(names)} fields")
    copyable = [each for each in methods if each.spelling == "copyable"]
    methods = [each for each in methods if each.spelling != "copyable"]
    say.extend(copy_findings(special, copyable))
    if [each.spelling for each in methods] != METHODS:
        say.append(f"has the functions {[each.spelling for each in methods]}, not {METHODS}")
    say.extend(list_findings(methods, names, indexed=indexed))
    parameters = tuple(
        each.spelling
        for each in cursor.get_children()
        if each.kind in {ci.CursorKind.TEMPLATE_TYPE_PARAMETER, ci.CursorKind.TEMPLATE_NON_TYPE_PARAMETER}
    )
    return Record(tag, names, cursor.location.line, parameters=parameters), say


@dataclass(frozen=True)
class Mixin:
    """A urd::view_mixin specialization: the record tag it serves, where it is, its members, its reads of data().

    The tag is the mixin's key without data<> or builder<>: a mixin of either serves the record's views too.
    """

    tag: str
    file: str
    line: int
    methods: list[str]
    data_reads: int


def mixin_of(cursor: ci.Cursor, file: str) -> Mixin:
    """The mixin `cursor` defines."""
    key = tag_of(cursor.displayname, "view_mixin")
    for wrapper in ("data<", "builder<"):
        if key.startswith(wrapper) and key.endswith(">"):
            key = key[len(wrapper) : -1]
    methods = [
        each.spelling
        for each in cursor.get_children()
        if each.kind in {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE, ci.CursorKind.FIELD_DECL}
    ]
    words = [token.spelling for token in cursor.get_tokens()]
    reads = sum(
        1 for i in range(1, len(words) - 2) if words[i - 1] in {".", "->"} and words[i : i + 3] == ["data", "(", ")"]
    )
    return Mixin(key, file, cursor.location.line, methods, reads)


def mixin_findings(mixin: Mixin, record: Record) -> list[str]:
    """What S2 does not allow of `mixin`, one of the view mixins of `record`."""
    getters = ["self", *(f"get_{name}" for name in record.fields)]
    found: list[str] = []
    # One getter per field, in field order, first; members derived from them may follow.
    if mixin.methods[: len(getters)] != getters:
        found.append(f"{record.tag}: view_mixin starts with {mixin.methods[: len(getters)]}, not {getters}")
    if mixin.data_reads:
        found.append(f"{record.tag}: view_mixin reads data() {mixin.data_reads} times, not through member<>")
    return found


@dataclass(frozen=True)
class Database:
    """The flags to parse with: each compiled source's own, and those of the first source for a header."""

    flags: dict[Path, list[str]]
    default: list[str]
    resource: str


def database(repository: Path, compile_commands: Path) -> Database:
    """The compile database's flags of the sources under `repository`, made absolute; clang's resource directory."""
    root = repository.resolve()
    relative = re.compile(r"^(-I|-isystem|-iquote)(?=[^/])")
    flags: dict[Path, list[str]] = {}
    for entry in json.loads(compile_commands.read_text()):
        directory = Path(entry["directory"])
        source = (directory / entry["file"]).resolve()
        if source.is_relative_to(root):
            flags[source] = [relative.sub(lambda m, d=directory: f"{m[1]}{d}/", each) for each in flags_of(entry)]
    if not flags:
        message = f"{compile_commands} has no compile command of a source under {repository}"
        raise ValueError(message)
    return Database(flags, next(iter(flags.values())), resource_dir())


def arguments_of(tag: str) -> tuple[str, list[str]]:
    """A tag's template and its arguments: Relation<Schema> -> (Relation, [Schema])."""
    if "<" not in tag:
        return tag, []
    name, inner = tag[: tag.index("<")], tag[tag.index("<") + 1 : -1]
    parts: list[str] = []
    depth, current = 0, ""
    for char in inner:
        depth += {"<": 1, ">": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return name, [*parts, current]


def binds(record: Record, tag: str) -> bool:
    """Whether a bind_data of `tag` binds `record`: equal, or a member of its family (its parameters are any)."""
    if record.tag == tag:
        return True
    name, arguments = arguments_of(record.tag)
    bound_name, bound_arguments = arguments_of(tag)
    return (
        name == bound_name
        and len(arguments) == len(bound_arguments)
        and all(a == b or a in record.parameters for a, b in zip(arguments, bound_arguments, strict=True))
    )


def bound(repository: Path, file: str, data: Database) -> set[str]:
    """The tags the binding source `file` binds with urd::python::bind_data, without namespaces.

    Each is the call's first template argument, resolved: an alias names the record it stands for.
    """
    path = (repository / file).resolve()
    unit, _ = parse(path, data.flags.get(path, data.default), data.resource)
    if unit is None:
        return set()
    tags: set[str] = set()
    for call in unit.cursor.walk_preorder():
        if call.kind == ci.CursorKind.CALL_EXPR and call.spelling == "bind_data" and declared_in(call, path):
            function = call.referenced
            if function is not None and function.get_num_template_arguments() > 0:
                spelled = function.get_template_argument_type(0).get_canonical().spelling
                tags.add(re.sub(r"(?:\b\w+)?::", "", spelled).replace(" ", ""))
    return tags


BINDS = ("bind_data", "bind_view", "class_<")
DEFINES = re.compile(r"struct\s+(?:::)?(?:urd::)?(?:data|view_mixin)<")
HAND_DATA = re.compile(r"class_<\s*(?:::)?(?:urd::)?data<")
VIEWS = ("urd::index_view<", "urd::borrowed_view<", "urd::owning_view<", "urd::shared_view<")


def hand_bound(repository: Path, file: str, data: Database) -> list[tuple[int, str]]:
    """The classes of a record's data or view that the binding source `file` defines itself: (line, record tag).

    A class bind_data or bind_view defines is in urd's header, not in `file`, so only what the file writes by hand is
    found.
    """
    path = (repository / file).resolve()
    unit, _ = parse(path, data.flags.get(path, data.default), data.resource)
    if unit is None:
        return []
    found: set[tuple[int, str]] = set()
    for cursor in unit.cursor.walk_preorder():
        if cursor.kind not in {ci.CursorKind.VAR_DECL, ci.CursorKind.CALL_EXPR} or not declared_in(cursor, path):
            continue
        # A class is bound where it is constructed (a variable, a call of its constructor); a .def on one is not, nor is
        # a variable that holds the class bind_data or bind_view returned.
        if cursor.kind == ci.CursorKind.CALL_EXPR and cursor.spelling != "class_":
            continue
        if cursor.kind == ci.CursorKind.VAR_DECL and any(
            each.kind == ci.CursorKind.CALL_EXPR and each.spelling in {"bind_data", "bind_view"} for each in cursor.walk_preorder()
        ):
            continue
        bound = cursor.type.get_canonical()
        if "type-parameter" in bound.spelling:
            # In a template the record is a parameter, and its type cannot be resolved: binding urd::data<...> by hand
            # there is the finding itself.
            if HAND_DATA.search(cursor.type.spelling):
                found.add((cursor.location.line, "*"))
            continue
        if not bound.spelling.startswith("nanobind::class_<") or bound.get_num_template_arguments() < 1:
            continue
        argument = bound.get_template_argument_type(0).get_canonical().spelling
        if argument.startswith("urd::data<"):
            found.add((cursor.location.line, tag_of(argument, "data")))
        elif argument.startswith(VIEWS):
            found.add((cursor.location.line, tag_of(argument, argument[len("urd::") : argument.index("<")])))
    return sorted(found)


def file_findings(repository: Path, file: str, data: Database) -> tuple[list[Record], list[Mixin], list[Finding]]:
    """The records and view mixins `file` defines, and what of its records S1 does not allow."""
    path = (repository / file).resolve()
    unit, error = parse(path, data.flags.get(path, data.default), data.resource)
    if unit is None:
        return [], [], [Finding(file, f"does not parse: {error}")]
    records: list[Record] = []
    mixins: list[Mixin] = []
    found: list[Finding] = []
    for cursor in top_level(unit.cursor, path):
        if in_urd(cursor, "data"):
            record, say = record_findings(cursor)
            records.append(Record(record.tag, record.fields, record.line, file, record.parameters))
            found.extend(Finding(f"{file}:{record.line}", f"data<{record.tag}> {what}") for what in say)
        elif in_urd(cursor, "view_mixin"):
            mixins.append(mixin_of(cursor, file))
    return records, mixins, found


def from_bound_record(expression: ci.Cursor) -> bool:
    """Whether `expression` is a class bind_data or bind_view returned, through any chain of calls on it."""
    current: ci.Cursor | None = expression
    while current is not None:
        if current.kind == ci.CursorKind.CALL_EXPR and current.spelling in {"bind_data", "bind_view"}:
            return True
        children = list(current.get_children())
        current = children[0] if children else None
    return False


def tag_name(tag: str) -> str:
    """A tag's name in a Python name: FluentTag -> fluent, PositiveTag -> positive."""
    base = tag.removesuffix("Tag")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", base).lower()


def derived_name(method: str, words: list[str]) -> str:
    """The Python name of member `method` given the tokens of the bound expression: tags after get_ for a template."""
    if method not in words or words.index(method) + 1 >= len(words) or words[words.index(method) + 1] != "<":
        return method
    tags: list[str] = []
    depth, last = 0, ""
    for word in words[words.index(method) + 1 :]:
        if word == "<":
            depth += 1
        elif word in {">", ","} and depth == 1 and last:
            tags.append(last)
            last = ""
        if word == ">":
            depth -= 1
            if depth == 0:
                break
        elif re.fullmatch(r"\w+", word):
            last = word
    return "get_" + "_".join(tag_name(tag) for tag in tags) + "_" + method.removeprefix("get_")


def derived_findings(repository: Path, file: str, data: Database) -> list[Finding]:
    """What S3 does not allow of the .def calls on the classes bind_data and bind_view return in source `file`."""
    path = (repository / file).resolve()
    unit, _ = parse(path, data.flags.get(path, data.default), data.resource)
    if unit is None:
        return []
    found: list[Finding] = []
    for call in unit.cursor.walk_preorder():
        if call.kind != ci.CursorKind.CALL_EXPR or call.spelling != "def" or not declared_in(call, path):
            continue
        children = list(call.get_children())
        if len(children) < 3 or not from_bound_record(children[0]):  # noqa: PLR2004 (callee, name, function)
            continue
        where = f"{file}:{call.location.line}"
        names = [each for each in children[1].walk_preorder() if each.kind == ci.CursorKind.STRING_LITERAL]
        function = children[2]
        nodes = list(function.walk_preorder())
        if any(each.kind == ci.CursorKind.LAMBDA_EXPR for each in nodes):
            found.append(Finding(where, "binds a lambda: bind the member function itself"))
            continue
        methods = [
            each.referenced
            for each in nodes
            if each.kind in {ci.CursorKind.DECL_REF_EXPR, ci.CursorKind.MEMBER_REF_EXPR}
            and each.referenced is not None
            and each.referenced.kind in {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE}
        ]
        if not names or not methods:
            found.append(Finding(where, "binds something other than a member function under a string name"))
            continue
        name = names[0].spelling.strip('"')
        expected = derived_name(methods[0].spelling, [token.spelling for token in function.get_tokens()])
        if name != expected:
            found.append(Finding(where, f"binds {methods[0].spelling} as {name!r}, not {expected!r}"))
    return found


@functools.cache
def check(repository: Path, compile_commands: Path) -> dict[str, list[Finding]]:
    """The findings of the record schemas in `repository`, by rule (S1, S2, S3).

    Every tracked header and source that defines a urd::data or urd::view_mixin specialization is parsed once (a header
    alone, a source with its own compile command); a record's view mixins are those of its tag, as T, data<T> or
    builder<T>, wherever they are defined. A file that does not parse is an S1 finding.
    """
    files = tracked(repository)
    data = database(repository, compile_commands)
    sources = [
        each
        for each in files
        if each.startswith("python/src/")
        and each.endswith(".cpp")
        and any(word in (repository / each).read_text(errors="replace") for word in BINDS)
    ]
    binding = {tag for each in sources for tag in bound(repository, each, data)}
    records: list[Record] = []
    mixins: list[Mixin] = []
    found: dict[str, list[Finding]] = {"S1": [], "S2": [], "S3": []}
    for each in files:
        if each.endswith((".hpp", ".cpp")) and DEFINES.search((repository / each).read_text(errors="replace")):
            more_records, more_mixins, findings = file_findings(repository, each, data)
            records.extend(more_records)
            mixins.extend(more_mixins)
            found["S1"].extend(findings)
    by_tag: dict[str, list[Mixin]] = {}
    for mixin in mixins:
        by_tag.setdefault(mixin.tag, []).append(mixin)
    for record in records:
        where = f"{record.file}:{record.line}"
        if record.tag not in by_tag:
            found["S2"].append(Finding(where, f"{record.tag}: has no urd::view_mixin<{record.tag}, V>"))
        for mixin in by_tag.get(record.tag, []):
            found["S2"].extend(Finding(f"{mixin.file}:{mixin.line}", what) for what in mixin_findings(mixin, record))
        # A library's records are bound; a test's own records are not.
        if record.file.startswith("include/") and not any(binds(record, tag) for tag in binding):
            found["S3"].append(Finding(where, f"{record.tag} is not bound with urd::python::bind_data"))
    for each in sources:
        found["S3"].extend(
            Finding(f"{each}:{line}", f"{tag}: its data or view is bound by hand, not by bind_data or bind_view")
            for line, tag in hand_bound(repository, each, data)
            if tag == "*" or any(binds(record, tag) for record in records)
        )
        found["S3"].extend(derived_findings(repository, each, data))
    return found
