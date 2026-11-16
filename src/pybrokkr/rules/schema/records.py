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
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from itertools import repeat
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
    # Its template header (parameters and requires clause), which tells apart the specializations of one tag
    header: str = ""
    # Its tag with its namespaces, by which it is paired with its mixins
    qualified: str = ""


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


def qualified_of(spelling: str, template: str) -> str:
    """The first template argument of `template`<...> in `spelling` as written, with its namespaces.

    No namespace leads and no spaces are kept: ``runir::kr::ps::icp::Program``. Records and mixins are paired by it, so
    that tags of one name in two namespaces are not.
    """
    inner = spelling[spelling.index(f"{template}<") + len(template) + 1 :]
    depth, end = 0, len(inner)
    for position, char in enumerate(inner):
        depth += {"<": 1, ">": -1}.get(char, 0)
        if depth < 0 or (depth == 0 and char == ","):
            end = position
            break
    return re.sub(r"(^|[<,])::", r"\1", inner[:end].replace(" ", ""))


def header_of(cursor: ci.Cursor, without: str = "") -> str:
    """The template header of the specialization `cursor`, its tokens before ``struct``.

    Its parameters and requires clause tell apart the specializations of one tag (data<Concept<F, Tag>> for each shape
    of Tag). The parameter named `without` (a view mixin's view, V) is left out, so that a record and its mixins have
    the same header.
    """
    words: list[str] = []
    for token in cursor.get_tokens():
        if token.spelling in {"struct", "class"}:
            break
        words.append(token.spelling)
    if not words or words[:2] != ["template", "<"]:
        return " ".join(words)
    # The parameter list: from its "<" to its matching ">", split at its top-level commas.
    depth, end = 0, len(words)
    parameters: list[list[str]] = []
    current: list[str] = []
    for position in range(1, len(words)):
        word = words[position]
        depth += {"<": 1, ">": -1}.get(word, 0)
        if depth == 0:
            end = position
            break
        if position == 1:
            continue
        if depth == 1 and word == ",":
            parameters.append(current)
            current = []
        else:
            current.append(word)
    if current:
        parameters.append(current)
    kept = [each for each in parameters if not (without and each and each[-1] == without)]
    return " ".join(["template", "<", " , ".join(" ".join(each) for each in kept), ">", *words[end + 1 :]]).replace(
        "<  >", "< >"
    )


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


def own_nodes(unit: ci.TranslationUnit, path: Path) -> Iterator[ci.Cursor]:
    """The nodes of the source `path` (parsed: `unit`) in preorder.

    These are the subtrees of its own top-level declarations, not those of the headers it includes, which are never
    walked.
    """
    for child in unit.cursor.get_children():
        if declared_in(child, path):
            yield from child.walk_preorder()


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
        # Which members identify the record is its semantics (its index, where a registered record is its index); that
        # they are its members is its schema.
        named = members_named(bodies["identifying_members"])
        members = ["index", *names] if indexed else names
        if not named or not set(named) <= set(members):
            found.append(f"identifying_members() names {named}, not some of the members {members}")
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
    # Without fields, data() = default is the one from the fields.
    if shapes != sorted({0, len(names)}) or not defaulted:
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
    qualified = qualified_of(cursor.displayname or cursor.type.spelling, "data")
    return Record(
        tag, names, cursor.location.line, parameters=parameters, header=header_of(cursor), qualified=qualified
    ), say


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
    header: str = ""
    qualified: str = ""
    # Its own template parameters but the view's (a generic mixin's, e.g. T and F of view_mixin<Atom<T, F>, V>)
    parameters: tuple[str, ...] = ()
    # The tokens of each member function, by name (overloads joined): what a getter reads
    bodies: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    # The view parameter's name (V)
    view: str = "V"
    # A held form's mixin (of data<T> or builder<T>) that inherits the tag's own (view_mixin<T, V>): its field getters
    # are its base's
    inherits: bool = False
    # What S2 does not allow of its members that only forward (forwarding)
    forwarders: tuple[str, ...] = ()


def view_parameter(spelling: str) -> str:
    """The view parameter of a view_mixin<K, V> spelling, V: its last template argument."""
    inner = spelling[spelling.index("view_mixin<") + len("view_mixin<") : spelling.rindex(">")]
    depth, last = 0, 0
    for position, char in enumerate(inner):
        depth += {"<": 1, ">": -1}.get(char, 0)
        if depth == 0 and char == ",":
            last = position + 1
    return inner[last:].strip()


CHAIN = re.compile(r"\*?(?:(\w+)\(\)\.)*(\w+)\(\)")


def forwarding(name: str, words: list[str]) -> str:
    """What S2 does not allow of the function `name` with the tokens `words`: that it only forwards; or empty.

    It forwards where its body is a single ``return`` of a chain of calls without arguments
    (``get_symbol().get_name()``, ``self().context()``) whose last call has its own name, or that is one call on the
    view itself (an alias of a member it has).
    """
    if "{" not in words or words[-1] != "}":
        return ""
    body = words[words.index("{") + 1 : -1]
    if len(body) < 2 or body[0] != "return" or body[-1] != ";":  # noqa: PLR2004 (return, ;)
        return ""
    chain = "".join(body[1:-1])
    if not CHAIN.fullmatch(chain):
        return ""
    calls = re.findall(r"(\w+)\(\)", chain)
    if calls and calls[0] == "self":
        calls = calls[1:]
    if calls and calls[-1] == name:
        return f"{name}() forwards to {chain}, which has its name: its callers read that path"
    if len(calls) == 1:
        return f"{name}() is an alias of {calls[0]}() of the view: its callers call that"
    return ""


def mixin_of(cursor: ci.Cursor, file: str) -> Mixin:
    """The mixin `cursor` defines."""
    key = tag_of(cursor.displayname, "view_mixin")
    held = False
    for wrapper in ("data<", "builder<"):
        if key.startswith(wrapper) and key.endswith(">"):
            key = key[len(wrapper) : -1]
            held = True
    methods = [
        each.spelling
        for each in cursor.get_children()
        if each.kind in {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE, ci.CursorKind.FIELD_DECL}
    ]
    words = [token.spelling for token in cursor.get_tokens()]
    # The view's data(): self().data() (a mixin reaches its view through self() alone); a field's own data(), such as
    # a vector's (member<...>().data()), is not the view's.
    reads = sum(
        1
        for i in range(4, len(words) - 2)
        if words[i - 4 : i] == ["self", "(", ")", "."] and words[i : i + 3] == ["data", "(", ")"]
    )
    view = view_parameter(cursor.displayname)
    qualified = qualified_of(cursor.displayname, "view_mixin")
    for wrapper in ("urd::data<", "data<", "urd::builder<", "builder<"):
        if qualified.startswith(wrapper) and qualified.endswith(">"):
            qualified = qualified[len(wrapper) : -1]
            break
    parameters = tuple(
        each.spelling
        for each in cursor.get_children()
        if each.kind in {ci.CursorKind.TEMPLATE_TYPE_PARAMETER, ci.CursorKind.TEMPLATE_NON_TYPE_PARAMETER}
        and each.spelling != view
    )
    bodies: dict[str, list[str]] = {}
    for each in cursor.get_children():
        if each.kind in {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE}:
            bodies.setdefault(each.spelling, []).extend(token.spelling for token in each.get_tokens())
    forwarders = tuple(
        what
        for each in cursor.get_children()
        if each.kind in {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE} and each.spelling != "self"
        if (what := forwarding(each.spelling, [token.spelling for token in each.get_tokens()]))
    )
    inherits = held and any(
        each.kind == ci.CursorKind.CXX_BASE_SPECIFIER and "view_mixin<" in each.type.spelling
        for each in cursor.get_children()
    )
    return Mixin(
        key,
        file,
        cursor.location.line,
        methods,
        reads,
        header_of(cursor, view),
        qualified,
        parameters,
        bodies,
        view,
        inherits,
        forwarders,
    )


def split_template(spelling: str) -> tuple[str, list[str]]:
    """A template-id as its name and its arguments, split at their top-level commas: ``A<B<C>,D>`` is A, [B<C>, D]."""
    if "<" not in spelling or not spelling.endswith(">"):
        return spelling, []
    name, inner = spelling[: spelling.index("<")], spelling[spelling.index("<") + 1 : -1]
    arguments: list[str] = []
    depth, start = 0, 0
    for position, char in enumerate(inner):
        depth += {"<": 1, ">": -1}.get(char, 0)
        if depth == 0 and char == ",":
            arguments.append(inner[start:position])
            start = position + 1
    arguments.append(inner[start:])
    return name, [each for each in arguments if each]


def matches(pattern: str, value: str, parameters: tuple[str, ...], bound: dict[str, str]) -> bool:
    """Whether the tag `pattern` of a mixin, over its `parameters`, matches the tag `value` of a record.

    A parameter matches any argument (the same one each time it occurs, recorded in `bound`), anything else its own
    spelling, with its arguments matched in turn.
    """
    if pattern in parameters:
        return bound.setdefault(pattern, value) == value
    pattern_name, pattern_arguments = split_template(pattern)
    value_name, value_arguments = split_template(value)
    # Arguments left out are the template's defaults (Query<> is Query<void>), which a parameter of the pattern matches.
    defaulted = pattern_arguments[len(value_arguments) :]
    if pattern_name != value_name or len(value_arguments) > len(pattern_arguments):
        return False
    if any(each not in parameters or bound.setdefault(each, "<default>") != "<default>" for each in defaulted):
        return False
    pattern_arguments = pattern_arguments[: len(value_arguments)]
    if not pattern_arguments and not defaulted:
        return pattern == value
    return all(matches(p, v, parameters, bound) for p, v in zip(pattern_arguments, value_arguments, strict=True))


def covers(mixin: Mixin, record: Record) -> bool:
    """Whether `mixin` serves `record`: its tag, as a pattern over its own parameters, matches the record's.

    A mixin over a bare parameter (view_mixin<T, V> requires is_x<T>) names no tag: which records it serves its
    requires-clause says, which S2 does not evaluate, so it serves none here.
    """
    if mixin.qualified in mixin.parameters:
        return False
    return matches(mixin.qualified, record.qualified, mixin.parameters, {})


def reads_field(mixin: Mixin, getter: str, name: str) -> bool:
    """Whether the getter `getter` of `mixin` reads the field `name`: ``record_of<V>::<name>`` in its body."""
    words = mixin.bodies.get(getter, [])
    target = ["record_of", "<", mixin.view, ">", "::", name]
    return any(words[i : i + len(target)] == target for i in range(len(words) - len(target) + 1))


def mixin_findings(mixin: Mixin, record: Record) -> list[str]:
    """What S2 does not allow of `mixin`, one of the view mixins of `record` (its own or a generic one).

    It has ``self()`` first, a getter per field of the record, in field order, each reading its field. That the field
    getters of every record a mixin serves stand before its other members is order_findings'.
    """
    getters = [f"get_{name}" for name in record.fields]
    found: list[str] = []
    if mixin.methods[:1] != ["self"]:
        found.append(f"{record.tag}: view_mixin {mixin.qualified} starts with {mixin.methods[:1]}, not ['self']")
    missing = [each for each in getters if each not in mixin.methods]
    if missing:
        found.append(f"{record.tag}: view_mixin {mixin.qualified} has no {missing}")
    present = [each for each in dict.fromkeys(mixin.methods) if each in getters]
    if not missing and present != getters:
        found.append(
            f"{record.tag}: view_mixin {mixin.qualified} has its field getters {present}, not in field order {getters}"
        )
    unread = [
        f"get_{name}"
        for name in record.fields
        if f"get_{name}" in mixin.methods and not reads_field(mixin, f"get_{name}", name)
    ]
    if unread:
        found.append(
            f"{record.tag}: view_mixin getters {unread} do not read their field through record_of<{mixin.view}>"
        )
    if mixin.data_reads:
        found.append(f"{record.tag}: view_mixin reads data() {mixin.data_reads} times, not through member<>")
    return found


def order_findings(mixin: Mixin, records: list[Record]) -> list[str]:
    """What S2 does not allow of the order of `mixin`, which serves `records`.

    After ``self()`` come the field getters of all of them, before every other member: one strict order, of a mixin of
    one record or a generic one.
    """
    getters = {f"get_{name}" for record in records for name in record.fields}
    members = [each for each in mixin.methods if each != "self"]
    others = [position for position, each in enumerate(members) if each not in getters]
    last_getter = max((position for position, each in enumerate(members) if each in getters), default=-1)
    if others and others[0] < last_getter:
        return [f"{mixin.qualified}: view_mixin has {members[others[0]]!r} before its field getters end"]
    return []


@dataclass(frozen=True)
class Database:
    """The flags to parse with: each compiled source's own, and those of the first source for a header."""

    flags: dict[Path, list[str]]
    default: list[str]
    resource: str
    # A binding header's: those of the first binding source (python/src), which has the bindings' include paths
    binding: list[str] = field(default_factory=list[str])

    def unit(self, path: Path) -> tuple[ci.TranslationUnit | None, str]:
        """`path` parsed: a header with the first source's flags, a source with its own.

        A source that has none is not parsed (no other source's flags stand in for its own), and what is wrong is the
        error.
        """
        if path.suffix != ".cpp":
            under_bindings = "python/src" in path.as_posix() and self.binding
            return parse(path, self.binding if under_bindings else self.default, self.resource)
        if path not in self.flags:
            return None, "not in the compile database, nor included by a source that is"
        return parse(path, self.flags[path], self.resource)


UNITY_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+\.(?:cpp|cxx|cc))"', re.MULTILINE)


def database(repository: Path, compile_commands: Path) -> Database:
    """The compile database's flags of the sources under `repository`, made absolute; clang's resource directory."""
    root = repository.resolve()
    relative = re.compile(r"^(-I|-isystem|-iquote)(?=[^/])")
    flags: dict[Path, list[str]] = {}
    included: dict[Path, list[str]] = {}
    for entry in json.loads(compile_commands.read_text()):
        directory = Path(entry["directory"])
        source = (directory / entry["file"]).resolve()
        own = [relative.sub(lambda m, d=directory: f"{m[1]}{d}/", each) for each in flags_of(entry)]
        if source.is_relative_to(root):
            flags[source] = own
        # A unity build compiles its sources by including them (#include "<absolute path>.cpp"): each is parsed with the
        # flags of the source that includes it.
        if source.is_file():
            for name in UNITY_INCLUDE.findall(source.read_text(errors="replace")):
                if (member := (directory / name).resolve()).is_relative_to(root):
                    included.setdefault(member, own)
    for member, own in included.items():
        flags.setdefault(member, own)
    if not flags:
        message = f"{compile_commands} has no compile command of a source under {repository}"
        raise ValueError(message)
    no_flags: list[str] = []
    binding = next((each for source, each in flags.items() if "python/src" in source.as_posix()), no_flags)
    return Database(flags, next(iter(flags.values())), resource_dir(), binding)


def binds(record: Record, tag: str) -> bool:
    """Whether a bind_data of `tag` binds `record`: equal, or a member of its family.

    A member of its family is one the record's tag, as a pattern over its parameters (nested ones too,
    Query<AtomicStateTag<T>>), matches.
    """
    return record.tag == tag or matches(record.tag, tag, record.parameters, {})


RECORD_CLASSES = {"urd::data", "urd::index_view", "urd::borrowed_view", "urd::owning_view", "urd::shared_view"}
REFERENCES = {ci.CursorKind.TYPE_REF, ci.CursorKind.TEMPLATE_REF}
ALIASES = {ci.CursorKind.TYPE_ALIAS_DECL, ci.CursorKind.TYPEDEF_DECL}
CONSTRUCTIONS = {ci.CursorKind.VAR_DECL, ci.CursorKind.CALL_EXPR, ci.CursorKind.UNEXPOSED_EXPR}


def written_argument(words: list[str]) -> str:
    """The first template argument of the ``bind_data<...>`` among the tokens `words`, as written, without spaces.

    A ``>>`` closes two levels, one character at a time; it is empty where there is none.
    """
    if "bind_data" not in words:
        return ""
    start = words.index("bind_data") + 1
    if start >= len(words) or words[start] != "<":
        return ""
    depth, spelled = 1, ""
    for word in words[start + 1 :]:
        if word in {">", ">>"}:
            for char in word:
                depth -= 1
                if depth == 0:
                    return spelled
                spelled += char
            continue
        depth += word.count("<")
        spelled += word
    return ""


def bound(unit: ci.TranslationUnit, path: Path) -> set[str]:
    """The tags the binding source `path` (parsed: `unit`) binds with urd::python::bind_data, without namespaces.

    Each is the call's first template argument, resolved (an alias names the record it stands for) and as written (a
    record whose tag is an alias is named by it).
    """
    tags: set[str] = set()
    for call in own_nodes(unit, path):
        if call.kind == ci.CursorKind.CALL_EXPR and call.spelling == "bind_data" and declared_in(call, path):
            function = call.referenced
            if function is None or function.get_num_template_arguments() <= 0:
                # A dependent call (in a template: bind_data<State<Kind>>) has no instantiation to read: its argument
                # as written, from its tokens.
                words = [token.spelling for token in call.get_tokens()]
                tag = written_argument(words)
                if tag:
                    tags.add(re.sub(r"(?:\b\w+)?::", "", tag))
                continue
            if function.get_num_template_arguments() > 0:
                spelled = function.get_template_argument_type(0).get_canonical().spelling
                tags.add(re.sub(r"(?:\b\w+)?::", "", spelled).replace(" ", ""))
                # The argument as written, where it is an alias: libclang hands out the argument's type desugared.
                written = next((each for each in call.walk_preorder() if each.kind in REFERENCES), None)
                if written is not None and written.referenced is not None and written.referenced.kind in ALIASES:
                    tags.add(written.referenced.spelling)
    # In a template that is not instantiated here (bind_data<State<Kind>> in a header's function template), libclang
    # exposes no call: the argument as written, from the file's own tokens.
    text = re.sub(r"//[^\n]*|/\*.*?\*/", " ", path.read_text(errors="replace"), flags=re.DOTALL)
    words = re.findall(r">>|::|[A-Za-z_]\w*|[<>(),]", text)
    for start, word in enumerate(words):
        if word == "bind_data" and (tag := written_argument(words[start:])):
            tags.add(re.sub(r"(?:\b\w+)?::", "", tag))
    return tags


BINDS = ("bind_data", "bind_view", "class_<")
DEFINES = re.compile(r"struct\s+(?:::)?(?:urd::)?(?:data|view_mixin)<|\bauto\s+fields\(\)")
# What a value (S4: a struct of fields that is no record) declares besides fields()
VALUE_MEMBERS = ("name", "identifying_members")
VIEWS = ("urd::index_view<", "urd::borrowed_view<", "urd::owning_view<", "urd::shared_view<")


def qualified(declaration: ci.Cursor) -> str:
    """The name of `declaration` with its enclosing scopes: ``urd::data``."""
    names: list[str] = []
    current: ci.Cursor | None = declaration
    while current is not None and current.kind != ci.CursorKind.TRANSLATION_UNIT:
        if current.spelling:
            names.append(current.spelling)
        current = current.semantic_parent
    return "::".join(reversed(names))


def aliased(declaration: ci.Cursor) -> ci.Cursor | None:
    """What the alias or alias template `declaration` names: an alias template's alias, an alias's written type."""
    if declaration.kind == ci.CursorKind.TYPE_ALIAS_TEMPLATE_DECL:
        return next((each for each in declaration.get_children() if each.kind == ci.CursorKind.TYPE_ALIAS_DECL), None)
    written = next((each for each in declaration.walk_preorder() if each.kind in REFERENCES), None)
    return None if written is None else written.referenced


def named(reference: ci.Cursor) -> str:
    """The class or class template a type reference names, through aliases and alias templates.

    It is ``urd::data`` for V of ``using V = urd::data<Tag>``; "" where it names none (a template parameter).
    """
    declaration = reference.referenced
    while declaration is not None and (
        declaration.kind in ALIASES or declaration.kind == ci.CursorKind.TYPE_ALIAS_TEMPLATE_DECL
    ):
        declaration = aliased(declaration)
    if declaration is not None and declaration.kind in {
        ci.CursorKind.CLASS_TEMPLATE,
        ci.CursorKind.CLASS_DECL,
        ci.CursorKind.STRUCT_DECL,
    }:
        return qualified(declaration)
    return ""


def constructed(cursor: ci.Cursor) -> str:
    """The class or class template the nanobind::class_ that `cursor` constructs binds (``named``).

    It is "" where it constructs none.
    """
    references = [each for each in cursor.walk_preorder() if each.kind in REFERENCES]
    for position, each in enumerate(references[:-1]):
        referenced = each.referenced
        if each.kind == ci.CursorKind.TEMPLATE_REF and referenced and qualified(referenced) == "nanobind::class_":
            return named(references[position + 1])
    return ""


def constructs(cursor: ci.Cursor, path: Path) -> bool:
    """Whether `cursor`, of the source `path`, may construct a class there.

    A class is bound where it is constructed (a variable, a call of its constructor, unnamed in a template); a .def on
    one is not, nor is a variable that holds the class bind_data or bind_view returned.
    """
    if cursor.kind not in CONSTRUCTIONS or not declared_in(cursor, path):
        return False
    if cursor.kind == ci.CursorKind.CALL_EXPR and cursor.spelling not in {"class_", ""}:
        return False
    return not (
        cursor.kind == ci.CursorKind.VAR_DECL
        and any(
            each.kind == ci.CursorKind.CALL_EXPR and each.spelling in {"bind_data", "bind_view"}
            for each in cursor.walk_preorder()
        )
    )


def hand_bound(unit: ci.TranslationUnit, path: Path) -> list[tuple[int, str]]:
    """The classes of a record's data or view that the binding source `path` (parsed: `unit`) defines itself.

    Each is (line, record tag).

    A class bind_data or bind_view defines is in urd's header, not in `path`, so only what the file writes by hand is
    found.
    """
    found: set[tuple[int, str]] = set()
    for cursor in own_nodes(unit, path):
        if not constructs(cursor, path):
            continue
        bound = cursor.type.get_canonical()
        dependent = "type-parameter" in bound.spelling or bound.spelling == "auto"
        # Outside a template a class is constructed by a variable or a call of class_'s constructor; an unnamed
        # expression of its type there is a class a call returned (bind_data's), not one constructed here.
        if not dependent and (cursor.kind == ci.CursorKind.UNEXPOSED_EXPR or cursor.spelling == ""):
            continue
        if dependent:
            # In a template the class depends on a parameter (or is an undeduced auto): its record is not known, but the
            # template it names is, through aliases. A record's data or view bound by hand there is the finding itself.
            if constructed(cursor) in RECORD_CLASSES:
                found.add((cursor.location.line, "*"))
            continue
        if not bound.spelling.startswith("nanobind::class_<") or bound.get_num_template_arguments() < 1:
            continue
        argument = bound.get_template_argument_type(0).get_canonical().spelling
        if argument.startswith("urd::data<"):
            found.add((cursor.location.line, tag_of(argument, "data")))
        elif argument.startswith(VIEWS):
            found.add((cursor.location.line, tag_of(argument, argument[len("urd::") : argument.index("<")])))
        else:
            # Any other class, by its class or template with its namespaces: a value's (S4) is bound by bind_value.
            found.add((cursor.location.line, "class " + argument.split("<", 1)[0]))
    return sorted(found)


def value_of(cursor: ci.Cursor) -> tuple[str, list[str]] | None:
    """The value `cursor` defines: its name with its namespaces and the members of VALUE_MEMBERS it lacks.

    A value (S4) is a struct or class template, no record, with a static fields(); None where `cursor` defines none.
    """
    if cursor.kind not in {ci.CursorKind.STRUCT_DECL, ci.CursorKind.CLASS_DECL, ci.CursorKind.CLASS_TEMPLATE}:
        return None
    if not cursor.is_definition():
        return None
    members = {each.spelling for each in cursor.get_children()}
    if "fields" not in members:
        return None
    return qualified(cursor), [each for each in VALUE_MEMBERS if each not in members]


def file_findings(
    repository: Path, file: str, data: Database
) -> tuple[list[Record], list[Mixin], list[Finding], list[tuple[str, str, int]], list[Finding]]:
    """The records, view mixins and values `file` defines, and what of them S1 and S4 do not allow.

    A value is (its name with its namespaces, file, line).
    """
    path = (repository / file).resolve()
    unit, error = data.unit(path)
    if unit is None:
        return [], [], [Finding(file, f"does not parse: {error}")], [], []
    values: list[tuple[str, str, int]] = []
    value_found: list[Finding] = []
    records: list[Record] = []
    mixins: list[Mixin] = []
    found: list[Finding] = []
    for cursor in top_level(unit.cursor, path):
        if in_urd(cursor, "data"):
            record, say = record_findings(cursor)
            records.append(
                Record(record.tag, record.fields, record.line, file, record.parameters, record.header, record.qualified)
            )
            found.extend(Finding(f"{file}:{record.line}", f"data<{record.tag}> {what}") for what in say)
        elif in_urd(cursor, "view_mixin"):
            mixins.append(mixin_of(cursor, file))
        elif in_urd(cursor, "builder"):
            continue
        elif (value := value_of(cursor)) is not None:
            name, missing = value
            values.append((name, file, cursor.location.line))
            if missing:
                value_found.append(Finding(f"{file}:{cursor.location.line}", f"value {name} has no {missing}"))
    return records, mixins, found, values, value_found


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


def derived_findings(unit: ci.TranslationUnit, path: Path, file: str) -> list[Finding]:
    """What S3 does not allow of the .def calls on the classes bind_data and bind_view return in source `file`.

    Its path is `path`, parsed: `unit`.
    """
    found: list[Finding] = []
    for call in own_nodes(unit, path):
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


def binding_read(
    repository: Path, file: str, data: Database
) -> tuple[str, str | None, set[str], list[tuple[int, str]], list[Finding]]:
    """The binding source `file` parsed, read and dropped.

    What is read: the tags it binds, its classes bound by hand, its derived findings (S3); or why it does not parse,
    with nothing read. Only these are kept, never its tree, which holds everything the source includes.
    """
    path = (repository / file).resolve()
    unit, error = data.unit(path)
    if unit is None:
        return file, error, set(), [], []
    return file, None, bound(unit, path), hand_bound(unit, path), derived_findings(unit, path, file)


def pair_findings(
    found: dict[str, list[Finding]], records: list[Record], mixins: list[Mixin], binding: set[str]
) -> None:
    """Adds to `found` what S2 and S3 do not allow of `records` paired with their `mixins`, `binding` the tags bound."""
    mixins = [each for each in mixins if not each.inherits]
    by_key: dict[tuple[str, str], list[Mixin]] = {}
    for mixin in mixins:
        by_key.setdefault((mixin.qualified, mixin.header), []).append(mixin)
    served: dict[int, tuple[Mixin, list[Record]]] = {}
    for record in records:
        where = f"{record.file}:{record.line}"
        key = (record.qualified, record.header)
        # Its own mixin (of its template header) where it has one, as C++ takes the more specialized; else the generic
        # ones whose tag covers its own (view_mixin<Atom<T, F>, V> for data<Atom<LiftedTag, F>>).
        own = by_key.get(key, [])
        generic = [] if own else [each for each in mixins if covers(each, record)]
        if not own and not generic:
            found["S2"].append(Finding(where, f"{record.tag}: has no urd::view_mixin<{record.tag}, V>"))
        for mixin in own + generic:
            found["S2"].extend(Finding(f"{mixin.file}:{mixin.line}", what) for what in mixin_findings(mixin, record))
            served.setdefault(id(mixin), (mixin, []))[1].append(record)
        # A library's records are bound; a test's own records are not.
        if record.file.startswith("include/") and not any(binds(record, tag) for tag in binding):
            found["S3"].append(Finding(where, f"{record.tag} is not bound with urd::python::bind_data"))
    for mixin, served_records in served.values():
        found["S2"].extend(
            Finding(f"{mixin.file}:{mixin.line}", what) for what in order_findings(mixin, served_records)
        )


def hand_findings(
    found: dict[str, list[Finding]], file: str, by_hand: list[tuple[int, str]], records: list[Record], values: set[str]
) -> None:
    """Adds to `found` the classes the binding source `file` binds by hand: a record's (S3), a value's (S4)."""
    for line, tag in by_hand:
        where = f"{file}:{line}"
        if tag.startswith("class "):
            if tag.removeprefix("class ") in values:
                found["S4"].append(
                    Finding(where, f"value {tag.removeprefix('class ')} is bound by hand, not by bind_value")
                )
        elif tag == "*" or any(binds(record, tag) for record in records):
            found["S3"].append(
                Finding(where, f"{tag}: its data or view is bound by hand, not by bind_data or bind_view")
            )


@functools.cache
def check(repository: Path, compile_commands: Path, jobs: int | None = None) -> dict[str, list[Finding]]:
    """The findings of the record and value schemas in `repository`, by rule (S1, S2, S3, S4).

    Every tracked header and source that defines a urd::data or urd::view_mixin specialization is parsed once (a header
    alone, a source with its own compile command); a record's view mixins are those of its tag, as T, data<T> or
    builder<T>, wherever they are defined. A file that does not parse is a finding: of S1 where it defines records, of
    S3
    where it binds them. A source is parsed with its own compile command, or with that of the unity source that includes
    it; one that has neither is not parsed with another's. `jobs` files are parsed at once, each in a process of its own
    that hands back what it read, in the files' order.
    """
    files = tracked(repository)
    data = database(repository, compile_commands)
    sources = [
        each
        for each in files
        if each.startswith("python/src/")
        and each.endswith((".cpp", ".hpp"))
        and any(word in (repository / each).read_text(errors="replace") for word in BINDS)
    ]
    defining = [
        each
        for each in files
        if each.endswith((".hpp", ".cpp")) and DEFINES.search((repository / each).read_text(errors="replace"))
    ]
    # Each file parsed once, in a worker that keeps only what it read (a binding source: what it binds, what it binds by
    # hand, its derived findings); one that does not parse is a finding, not a skip: what it binds is not known.
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        read = list(pool.map(binding_read, repeat(repository), sources, repeat(data)))
        defined = list(pool.map(file_findings, repeat(repository), defining, repeat(data)))
    binding = {tag for _, _, tags, _, _ in read for tag in tags}
    records: list[Record] = []
    mixins: list[Mixin] = []
    found: dict[str, list[Finding]] = {"S1": [], "S2": [], "S3": [], "S4": []}
    values: set[str] = set()
    for more_records, more_mixins, findings, more_values, value_findings in defined:
        records.extend(more_records)
        mixins.extend(more_mixins)
        found["S1"].extend(findings)
        values.update(name for name, _, _ in more_values)
        found["S4"].extend(value_findings)
    # A record's mixins: those of its tag (with its namespaces) and its template header (one specialization of a tag per
    # shape of its parameters, e.g. data<Concept<F, Tag>> for each concept Tag satisfies, has the mixin of the same
    # header).
    # A held form's mixin that inherits the tag's (S2: the mixins of data<T> and builder<T> inherit or specialize it)
    # has its base's getters: it is not checked again.
    # Every mixin, a held form's that inherits too, has no member that only forwards.
    for mixin in mixins:
        found["S2"].extend(
            Finding(f"{mixin.file}:{mixin.line}", f"{mixin.qualified}: {what}") for what in mixin.forwarders
        )
    pair_findings(found, records, mixins, binding)
    for each, error, _, by_hand, derived in read:
        if error is not None:
            found["S3"].append(Finding(each, f"does not parse: {error}"))
            continue
        hand_findings(found, each, by_hand, records, values)
        found["S3"].extend(derived)
    return found
