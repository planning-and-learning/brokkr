# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""The record schemas of docs/schema_rules.rst (S1, S2, S3), checked with libclang (``pybrokkr[fallbacks]``).

Each tracked ``include/<lib>/**/*_data.hpp`` and its ``*_view.hpp`` parse as a translation unit that includes the header
alone, with the include paths and the standard of one compile command of the repository's compile database. A header
that does not parse is a finding, not a skip: what it holds is not known.

    python -m pybrokkr.rules S1 S2 S3 [-C <repository>] [--compile-commands <file>]
"""

import functools
import itertools
import json
import re
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from itertools import repeat
from pathlib import Path

import clang.cindex as ci

from pybrokkr.rules.coding.fallbacks import flags_of, index, resource_dir
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


def words(cursor: ci.Cursor) -> list[str]:
    """The tokens of `cursor`, its comments left out: what a comment names is not code."""
    return [token.spelling for token in cursor.get_tokens() if token.kind != ci.TokenKind.COMMENT]


def overloads(reference: ci.Cursor) -> list[ci.Cursor]:
    """The declarations a reference may mean: an unresolved name (in a template) each of its overloads."""
    if reference.kind == ci.CursorKind.OVERLOADED_DECL_REF:
        count = ci.conf.lib.clang_getNumOverloadedDecls(reference)
        return [ci.conf.lib.clang_getOverloadedDecl(reference, i) for i in range(count)]
    referenced = reference.referenced
    return [] if referenced is None or referenced == reference else [referenced]


def signature(function_type: ci.Type) -> str:
    """The parameter list of a function type (or a pointer to one) as written, without namespaces and spaces.

    It is its last parenthesized group before a trailing return type: ``(int)`` of ``int (int) const``, of ``int
    (view_mixin<T, V>::*)(int) const`` and of ``auto (int) const -> decltype(f(x))``, how a static_cast picks an
    overload, read alike from a member and a cast whose type is dependent.
    """
    spelled = function_type.spelling.split(" -> ", 1)[0]
    end = spelled.rfind(")")
    depth = 0
    for position in range(end, -1, -1):
        depth += {")": 1, "(": -1}.get(spelled[position], 0)
        if depth == 0:
            return re.sub(r"(?:\b\w+)?::", "", spelled[position : end + 1]).replace(" ", "")
    return ""


def key_of(cursor: ci.Cursor) -> tuple[str, str, int, int]:
    """A declaration by its name and where it is: an overload's own, which its name alone is not."""
    file = cursor.location.file
    return cursor.spelling, "" if file is None else file.name, cursor.location.line, cursor.location.column


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
        unit = index(resource).parse(
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
        cursor.kind
        in {ci.CursorKind.STRUCT_DECL, ci.CursorKind.CLASS_DECL, ci.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION}
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
        text = " ".join(words(copyable[0]))
        checked = "static_assert ( std :: is_trivially_copyable_v < data >" in text and "return true ;" in text
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
    bodies = {each.spelling: words(each) for each in methods}
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


# S1's blocks, in their order: the index, the fields, the constructors, the five (or copyable()), the three lists.
BLOCKS = [
    "the index",
    "a field",
    "a constructor",
    "a special member",
    "fields()",
    "identifying_members()",
    "cista_members()",
]


def block_of(member: ci.Cursor) -> int:
    """The position in BLOCKS of the block of the record member `member`."""
    if member.kind == ci.CursorKind.FIELD_DECL:
        return 0 if member.spelling == "index" else 1
    if is_special(member) or member.spelling == "copyable":
        return 3
    if member.kind == ci.CursorKind.CONSTRUCTOR:
        return 2
    return 4 + METHODS.index(member.spelling)


def block_findings(members: list[ci.Cursor]) -> list[str]:
    """What S1 does not allow of the order of a record's `members`: a block before one that comes first.

    A member of none of the blocks is not S1's form at all, which record_findings reports.
    """
    members = [
        each
        for each in members
        if each.kind in {ci.CursorKind.FIELD_DECL, ci.CursorKind.CONSTRUCTOR}
        or is_special(each)
        or each.spelling in {*METHODS, "copyable"}
    ]
    for before, after in itertools.pairwise(members):
        if block_of(after) < block_of(before):
            return [f"declares {BLOCKS[block_of(after)]} ({after.spelling}) after {BLOCKS[block_of(before)]}"]
    return []


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
    say.extend(block_findings([each for each in members if each in known]))
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
    """A urd::view_mixin specialization: the record tag it serves, where it is, its members, its reads of record().

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
    # What S2 does not allow of it whatever records it serves: its members' kinds, access and order, its bases, its
    # members that only forward
    own: tuple[str, ...] = ()
    # The member functions functions() is to list, each by its name and key_of: every one but self() and functions()
    # and the member templates whose template arguments their callers write (get<FluentTag>(), C++'s alone)
    members: tuple[tuple[str, tuple[str, str, int, int]], ...] = ()
    # The key_of of each member function its functions() lists
    listed: frozenset[tuple[str, str, int, int]] = frozenset()


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
# The standard's customization points a range offers as members too (std::ranges::size(e), std::size(e): e.size())
MEMBER_FORMS = re.compile(r"(?:std::)?(?:ranges::)?(size|ssize|empty|begin|end|cbegin|cend|data)\((.+)\)")


def unwrapped(text: str) -> str:
    """`text` without the parentheses that enclose all of it."""
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for position, char in enumerate(text):
            depth += {"(": 1, ")": -1}.get(char, 0)
            if depth == 0 and position < len(text) - 1:
                return text
        text = text[1:-1]
    return text


def returned(body: list[str], receivers: tuple[str, ...]) -> str:
    """The chain of calls a body of tokens `body` returns, written without spaces; "" where it returns none.

    ``this->``, parentheses around it, and one local variable it is held in first (``auto s = get_symbol(); return
    s.get_name();``) are left out, as is a leading receiver of `receivers` (the view a free function takes); a standard
    customization point over it is its member (``std::ranges::size(get_values())`` is ``get_values().size()``).
    """
    text = "".join(body).replace("this->", "")
    local = re.fullmatch(r"(?:const)?auto&{0,2}(\w+)=(.+?);return\1\.(.+);", text)
    if local:
        text = f"return{local[2]}.{local[3]};"
    if not text.startswith("return") or not text.endswith(";"):
        return ""
    chain = unwrapped(text[len("return") : -1])
    # A standard customization point over a chain is the chain's own member: std::ranges::size(e) is e.size().
    member = MEMBER_FORMS.fullmatch(chain)
    if member:
        chain = f"{unwrapped(member[2])}.{member[1]}()"
    for receiver in receivers:
        if chain.startswith(f"{receiver}."):
            chain = chain[len(receiver) + 1 :]
    return chain if CHAIN.fullmatch(chain) else ""


def forwarding(name: str, words: list[str], receivers: tuple[str, ...] = ()) -> str:
    """What S2 does not allow of the function `name` with the tokens `words`: that it only forwards; or empty.

    It forwards where its body is a single ``return`` of a chain of calls without arguments
    (``get_symbol().get_name()``, ``self().context()``) whose last call has its own name, or that is one call on the
    view itself (an alias of a member it has). `receivers` names the view where a free function takes it.
    """
    if "{" not in words or words[-1] != "}":
        return ""
    chain = returned(words[words.index("{") + 1 : -1], receivers)
    if not chain:
        return ""
    calls = re.findall(r"(\w+)\(\)", chain)
    if calls and calls[0] == "self":
        calls = calls[1:]
    if calls and calls[-1] == name:
        return f"{name}() forwards to {chain}, which has its name: its callers read that path"
    if len(calls) == 1:
        return f"{name}() is an alias of {calls[0]}() of the view: its callers call that"
    return ""


EXPRESSION_WRAPPERS = {ci.CursorKind.UNEXPOSED_EXPR, ci.CursorKind.PAREN_EXPR}
CASTS = {ci.CursorKind.CXX_STATIC_CAST_EXPR, ci.CursorKind.CSTYLE_CAST_EXPR, ci.CursorKind.CXX_FUNCTIONAL_CAST_EXPR}


def is_view(expression: ci.Cursor, view: str, parameter: ci.Cursor | None, depth: int = 0) -> bool:
    """Whether `expression` is the view: ``self()``, ``*this``, ``this``, a cast to `view`, the view `parameter`.

    A local variable is the view where its initializer is.
    """
    children = list(expression.get_children())
    kind = expression.kind
    if kind in EXPRESSION_WRAPPERS:
        return bool(children) and is_view(children[0], view, parameter, depth)
    if kind == ci.CursorKind.DECL_REF_EXPR:
        return names_view(expression, view, parameter, depth)
    return (
        kind == ci.CursorKind.CXX_THIS_EXPR
        or (kind == ci.CursorKind.CALL_EXPR and len(children) == 1 and words(expression)[-3:] == ["self", "(", ")"])
        or (kind == ci.CursorKind.UNARY_OPERATOR and words(expression)[:2] == ["*", "this"])
        or (kind in CASTS and any(each.kind == ci.CursorKind.TYPE_REF and each.spelling == view for each in children))
    )


def names_view(reference: ci.Cursor, view: str, parameter: ci.Cursor | None, depth: int) -> bool:
    """Whether the name `reference` is the view: its `parameter`, or a local variable initialized with it."""
    referenced = reference.referenced
    if referenced is None or depth >= 3:  # noqa: PLR2004 (variables of variables, bounded)
        return False
    if referenced.kind == ci.CursorKind.PARM_DECL:
        return parameter is not None and referenced == parameter
    value = initializer(referenced) if referenced.kind == ci.CursorKind.VAR_DECL else None
    return value is not None and is_view(value, view, parameter, depth + 1)


def data_reads(function: ci.Cursor, view: str, parameter: ci.Cursor | None = None) -> int:
    """How often `function` calls record() of its view (is_view), whichever way it reaches it."""
    count = 0
    for node in function.walk_preorder():
        if node.kind != ci.CursorKind.MEMBER_REF_EXPR or words(node)[-1:] != ["record"]:
            continue
        objects = list(node.get_children())
        if objects and is_view(objects[0], view, parameter):
            count += 1
    return count


FUNCTION_KINDS = {ci.CursorKind.CXX_METHOD, ci.CursorKind.FUNCTION_TEMPLATE}
REFERENCE_KINDS = {ci.CursorKind.DECL_REF_EXPR, ci.CursorKind.MEMBER_REF_EXPR, ci.CursorKind.OVERLOADED_DECL_REF}
LISTS = {"urd::function", "urd::Functions"}


def pointed_to(node: ci.Cursor, cast: str | None) -> list[ci.Cursor]:
    """The functions ``&F`` (`node`) points to: the overloads of F, the one a static_cast to the types `cast` picks.

    Of a static_cast, the functions its operand points to: its type may name functions too
    (``decltype(declval<V>().f())``).
    """
    if node.kind == ci.CursorKind.CXX_STATIC_CAST_EXPR:
        node = list(node.get_children())[-1]
    reference = next((each for each in node.walk_preorder() if each.kind == ci.CursorKind.OVERLOADED_DECL_REF), None)
    if reference is None:
        reference = next((each for each in node.walk_preorder() if each.kind in REFERENCE_KINDS), None)
    if reference is None:
        return []
    candidates = [
        each
        for each in overloads(reference)
        if each.kind in FUNCTION_KINDS | {ci.CursorKind.FUNCTION_DECL, ci.CursorKind.CONVERSION_FUNCTION}
    ]
    if cast is None or len(candidates) <= 1:
        return candidates
    return [each for each in candidates if picks(cast, each)]


def picks(cast: str, function: ci.Cursor) -> bool:
    """Whether a static_cast to the parameter types `cast` picks `function`.

    A function's parameters as written are the cast's; a function template's match them as patterns over its template
    parameters, as the cast instantiates it (``(Wrap<T>)`` is picked by ``(Wrap<int>)``).
    """
    own = signature(function.type)
    if own == cast or function.kind != ci.CursorKind.FUNCTION_TEMPLATE:
        return own == cast
    parameters = tuple(each.spelling for each in function.get_children() if each.kind in TEMPLATE_PARAMETERS)
    _, own_types = split_template(f"_<{own[1:-1]}>")
    _, cast_types = split_template(f"_<{cast[1:-1]}>")
    bound: dict[str, str] = {}
    return len(own_types) == len(cast_types) and all(
        matches(each, given, parameters, bound) for each, given in zip(own_types, cast_types, strict=True)
    )


def listed_in(root: ci.Cursor) -> list[ci.Cursor]:
    """The functions the urd::function lists under `root` point to (``&F``), each overload a static_cast picks."""
    found: list[ci.Cursor] = []

    def visit(node: ci.Cursor, cast: str | None, *, inside: bool) -> None:
        children = list(node.get_children())
        inside = inside or any(
            each.kind == ci.CursorKind.TEMPLATE_REF
            and each.referenced is not None
            and qualified(each.referenced) in LISTS
            for each in children
        )
        if node.kind == ci.CursorKind.CXX_STATIC_CAST_EXPR:
            cast = signature(node.type)
        if inside and node.kind == ci.CursorKind.UNARY_OPERATOR and words(node)[:1] == ["&"]:
            found.extend(pointed_to(node, cast))
            return
        for child in children:
            visit(child, cast, inside=inside)

    visit(root, None, inside=False)
    return found


Entry = tuple[str, list[ci.Cursor], list[str]]


def entries_in(root: ci.Cursor) -> list[Entry]:
    """The entries of the urd::function lists under `root`, in order.

    Each is its name, the functions its pointer may mean (the overload a static_cast picks), and the names its
    urd::arg give its parameters.
    """
    entries: list[Entry] = []
    for node in root.walk_preorder():
        children = list(node.get_children())
        if any(each.kind == ci.CursorKind.TEMPLATE_REF and each.spelling == "function" for each in children):
            entries.extend(list_entries(children))
    return entries


def list_entries(children: list[ci.Cursor]) -> list[Entry]:
    """The entries of one urd::Functions list, whose arguments are `children` in order (urd::function starts one)."""
    entries: list[Entry] = []
    naming = False
    for child in children:
        if child.kind == ci.CursorKind.TEMPLATE_REF and child.referenced is not None:
            template = qualified(child.referenced)
            if template == "urd::function":
                started: Entry = ("", [], [])
                entries.append(started)
                naming = False
            naming = naming or template == "urd::arg"
        elif entries:
            entries[-1] = with_part(entries[-1], child, naming=naming)
    return entries


def with_part(entry: Entry, child: ci.Cursor, *, naming: bool) -> Entry:
    """`entry` with the part `child` of its urd::function: its name, its pointer, or one urd::arg's name."""
    name, functions, given = entry
    literal = next((each for each in child.walk_preorder() if each.kind == ci.CursorKind.STRING_LITERAL), None)
    if literal is not None and naming:
        given.append(literal.spelling.strip('"'))
    elif literal is not None and not name:
        name = literal.spelling.strip('"')
    elif child.kind == ci.CursorKind.CXX_STATIC_CAST_EXPR:
        functions.extend(pointed_to(child, signature(child.type)))
    elif child.kind == ci.CursorKind.UNARY_OPERATOR and words(child)[:1] == ["&"]:
        functions.extend(pointed_to(child, None))
    return name, functions, given


def argument_findings(entries: list[Entry]) -> list[str]:
    """What S2 does not allow of the parameter names a functions() gives (urd::arg): any but the function's own.

    A member's parameters are named beside its this, a free function's beside its view, its first parameter. An entry
    points to one function: where its pointer may mean several (overloads a cast does not tell apart), one of them
    has the names given.
    """
    found: list[str] = []
    for name, functions, given in entries:
        names = [parameter_names(each) for each in functions]
        if names and given not in names:
            found.append(f"functions() lists {name} with the parameter names {given}, not its own {names[0]}")
    return found


def parameter_names(function: ci.Cursor) -> list[str]:
    """The names of the parameters of `function` beside its view: a member's all, a free function's but its first."""
    parameters = [each.spelling for each in function.get_children() if each.kind == ci.CursorKind.PARM_DECL]
    parent = function.semantic_parent
    return parameters if parent is not None and parent.kind in VALUE_KINDS else parameters[1:]


def deduces(template: ci.Cursor) -> bool:
    """Whether the member template `template` deduces a template argument from its parameters (``f(auto)``)."""
    parameters = [each.spelling for each in template.get_children() if each.kind in TEMPLATE_PARAMETERS]
    types = [each.type.spelling for each in template.get_children() if each.kind == ci.CursorKind.PARM_DECL]
    return any(re.search(rf"\b(?:auto|{'|'.join(map(re.escape, parameters)) or 'auto'})\b", each) for each in types)


def shape_findings(cursor: ci.Cursor, *, held: bool) -> list[str]:
    """What S2 does not allow of the members of the mixin `cursor` whatever it serves: their kinds, access and order.

    A mixin declares member functions alone: ``self()`` first and private, every other one public, ``functions()``
    last; it has no base but, a held form's, its tag's mixin.
    """
    found: list[str] = []
    members: list[ci.Cursor] = []
    for each in cursor.get_children():
        if each.kind in ARGUMENTS or each.kind.is_expression() or each.kind.is_attribute():
            continue
        if each.kind == ci.CursorKind.CXX_BASE_SPECIFIER:
            if not (held and "view_mixin<" in each.type.spelling):
                found.append(f"has the base {each.type.spelling}: a mixin has none but a held form's its tag's mixin")
        elif each.kind not in FUNCTION_KINDS:
            found.append(f"declares {each.kind.name.lower()} {each.spelling}: a mixin declares member functions alone")
        else:
            members.append(each)
    names = [each.spelling for each in members]
    if names and names[0] != "self" and not held:
        found.append(f"starts with {names[0]}(), not self()")
    for each in members:
        private = each.access_specifier != ci.AccessSpecifier.PUBLIC
        if (each.spelling == "self") != private:
            found.append(f"has {each.spelling}() {each.access_specifier.name.lower()}: self() alone is private")
    if "functions" in names and names[-1] != "functions":
        found.append(f"declares {names[-1]}() after functions(), which is its last member")
    return found


def first_argument(arguments: str) -> str:
    """The first of comma-separated template arguments (``T, C`` of builder<T, C>: T)."""
    depth = 0
    for position, character in enumerate(arguments):
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
        elif character == "," and depth == 0:
            return arguments[:position].strip()
    return arguments


def mixin_of(cursor: ci.Cursor, file: str) -> Mixin:
    """The mixin `cursor` defines."""
    key = tag_of(cursor.displayname, "view_mixin")
    held = False
    for wrapper in ("data<", "builder<"):
        if key.startswith(wrapper) and key.endswith(">"):
            key = first_argument(key[len(wrapper) : -1])
            held = True
    children = list(cursor.get_children())
    methods = [each.spelling for each in children if each.kind in FUNCTION_KINDS | {ci.CursorKind.FIELD_DECL}]
    view = view_parameter(cursor.displayname)
    functions = [each for each in children if each.kind in FUNCTION_KINDS]
    reads = sum(data_reads(each, view) for each in functions)
    qualified_tag = qualified_of(cursor.displayname, "view_mixin")
    for wrapper in ("urd::data<", "data<", "urd::builder<", "builder<"):
        if qualified_tag.startswith(wrapper) and qualified_tag.endswith(">"):
            qualified_tag = first_argument(qualified_tag[len(wrapper) : -1])
            break
    parameters = tuple(
        each.spelling
        for each in children
        if each.kind in {ci.CursorKind.TEMPLATE_TYPE_PARAMETER, ci.CursorKind.TEMPLATE_NON_TYPE_PARAMETER}
        and each.spelling != view
    )
    bodies: dict[str, list[str]] = {}
    for each in functions:
        bodies.setdefault(each.spelling, []).extend(words(each))
    own = shape_findings(cursor, held=held)
    if reads:
        own.append(f"reads record() of its view {reads} times, not through member<>")
    own += [what for each in functions if each.spelling != "self" if (what := forwarding(each.spelling, words(each)))]
    members = tuple(
        (each.spelling, key_of(each))
        for each in functions
        if each.spelling not in {"self", "functions"} and (each.kind == ci.CursorKind.CXX_METHOD or deduces(each))
    )
    listed = frozenset(key_of(each) for each in functions if each.spelling == "functions" for each in listed_in(each))
    own += [what for each in functions if each.spelling == "functions" for what in argument_findings(entries_in(each))]
    inherits = held and any(
        each.kind == ci.CursorKind.CXX_BASE_SPECIFIER and "view_mixin<" in each.type.spelling for each in children
    )
    return Mixin(
        key,
        file,
        cursor.location.line,
        methods,
        reads,
        header_of(cursor, view),
        qualified_tag,
        parameters,
        bodies,
        view,
        inherits,
        tuple(own),
        members,
        listed,
    )


def free_findings(function: ci.Cursor) -> list[str]:
    """What S2 does not allow of the free function `function` a functions() lists.

    That is a parameter beside the view (a function of a view takes it alone: one that takes more is an algorithm over
    it, bound with m.def), forwarding, or reading record().
    """
    definition = function.get_definition() or function
    parameters = [each for each in definition.get_children() if each.kind == ci.CursorKind.PARM_DECL]
    if not parameters:
        return []
    if len(parameters) > 1:
        return [
            f"{definition.spelling}() takes {len(parameters)} parameters: a function of a view takes the view alone"
        ]
    view = parameters[0]
    named_type = re.sub(r"\b(?:const|volatile)\b|[&*\s]", "", view.type.spelling)
    found = [what] if (what := forwarding(definition.spelling, words(definition), (view.spelling,))) else []
    if reads := data_reads(definition, named_type, view):
        found.append(f"{definition.spelling}() reads record() of its view {reads} times, not through member<>")
    return found


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
    return found


def listing_findings(mixin: Mixin, records: list[Record]) -> list[str]:
    """What S2 does not allow of the functions of `mixin`, which serves `records`.

    That is a member beyond ``self()`` and their field getters that its ``functions()`` does not list.
    """
    getters = {f"get_{name}" for record in records for name in record.fields}
    unlisted = [name for name, key in mixin.members if name not in getters and key not in mixin.listed]
    return [f"{mixin.qualified}: view_mixin members {unlisted} are not listed in functions()"] if unlisted else []


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
            # A binding header (python/src, or one that binds with nanobind elsewhere: include/<lib>/python)
            under_bindings = self.binding and (
                "python/src" in path.as_posix() or "nanobind" in path.read_text(errors="replace")
            )
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
    # A library without python/src (urd) binds in its tests' modules: the flags of one that includes nanobind
    binding = next((each for source, each in flags.items() if "python/src" in source.as_posix()), no_flags) or next(
        (
            each
            for source, each in flags.items()
            if source.is_file() and "nanobind" in source.read_text(errors="replace")
        ),
        no_flags,
    )
    return Database(flags, next(iter(flags.values())), resource_dir(), binding)


def binds(record: Record, tag: str) -> bool:
    """Whether a bind_data of `tag` binds `record`: equal, or a member of its family.

    A member of its family is one the record's tag, as a pattern over its parameters (nested ones too,
    Query<AtomicStateTag<T>>), matches.
    """
    return record.tag == tag or matches(record.tag, tag, record.parameters, {})


# A bound tag, as binding_tags reads it: without namespaces, with them ("" where only written), and the template
# parameters of the function template it is written in (a dependent call's: bind_view<index_view<Atom<T, F>, C>>)
Tag = tuple[str, str, tuple[str, ...]]


def binds_qualified(record: Record, tag: Tag) -> bool:
    """Whether a binding of the tag `tag` binds `record`: by its namespaces where known.

    A tag over the parameters of the template it is bound in binds every record it matches as a pattern over them.
    """
    unqualified_tag, with_namespaces, parameters = tag
    if unqualified_tag in parameters:
        return False  # a bare parameter names no tag (bind_view<ViewOf<T>> in a generic helper)
    if parameters and matches(unqualified_tag, record.tag, parameters, {}):
        return True
    if not binds(record, unqualified_tag):
        return False
    return not with_namespaces or matches(record.qualified, with_namespaces, record.parameters, {})


RECORD_CLASSES = {"urd::data", "urd::index_view", "urd::borrowed_view", "urd::owning_view", "urd::shared_view"}
REFERENCES = {ci.CursorKind.TYPE_REF, ci.CursorKind.TEMPLATE_REF}
TEMPLATE_PARAMETERS = {
    ci.CursorKind.TEMPLATE_TYPE_PARAMETER,
    ci.CursorKind.TEMPLATE_NON_TYPE_PARAMETER,
    ci.CursorKind.TEMPLATE_TEMPLATE_PARAMETER,
}
ALIASES = {ci.CursorKind.TYPE_ALIAS_DECL, ci.CursorKind.TYPEDEF_DECL}
CONSTRUCTIONS = {ci.CursorKind.VAR_DECL, ci.CursorKind.CALL_EXPR, ci.CursorKind.UNEXPOSED_EXPR}
BINDERS = ("bind_data", "bind_view", "bind_value")
# A tracked file that may bind: it names one of these
BINDS = (*BINDERS, "class_<")
# A record or mixin, a value's fields(), a function list
DEFINED = (
    r"(?:struct|class)\s+(?:::)?(?:urd::)?(?:data|view_mixin)\s*<",
    r"static\s+constexpr\s+[^;{=()]*\bfields\s*\(",
    r"\burd::function\s*<",
)
DEFINES = re.compile("|".join(DEFINED))
VIEWS = ("urd::index_view<", "urd::borrowed_view<", "urd::owning_view<", "urd::shared_view<")


def written_argument(words: list[str], binder: str = "bind_data") -> str:
    """The first template argument of the ``<binder><...>`` among the tokens `words`, as written, without spaces.

    A ``>>`` closes two levels, one character at a time; it is empty where there is none.
    """
    if binder not in words:
        return ""
    start = words.index(binder) + 1
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


def unqualified(spelling: str) -> str:
    """`spelling` without namespaces and spaces."""
    return re.sub(r"(?:\b\w+)?::", "", spelling).replace(" ", "")


def callee(call: ci.Cursor) -> str:
    """The name of the function `call` calls: its own, or in a template the name it looks up (``bind_data<T>(m)``).

    A member function's (``.def``) is the last word of its member expression.
    """
    if call.spelling:
        return call.spelling
    children = list(call.get_children())
    if not children:
        return ""
    head = children[0]
    while head.kind == ci.CursorKind.UNEXPOSED_EXPR and list(head.get_children()):
        head = next(iter(head.get_children()))
    if head.kind == ci.CursorKind.MEMBER_REF_EXPR:
        spelled = words(head)
        return spelled[-1] if spelled else ""
    reference = next(
        (
            each
            for each in head.walk_preorder()
            if each.kind in {ci.CursorKind.OVERLOADED_DECL_REF, ci.CursorKind.DECL_REF_EXPR} and each.spelling
        ),
        None,
    )
    return "" if reference is None else reference.spelling


def view_tag(spelling: str) -> str:
    """The record tag of a view type's spelling (``urd::index_view<T, C>``: T; of data<T> or builder<T>: T); or ""."""
    compact = spelling.replace(" ", "").removeprefix("::")
    for view in VIEWS:
        position = compact.find(view)
        if position < 0:
            continue
        tag = qualified_of(compact[position:], view[len("urd::") : -1])
        for wrapper in ("urd::data<", "urd::builder<"):
            if tag.startswith(wrapper) and tag.endswith(">"):
                return first_argument(tag[len(wrapper) : -1])
        return tag
    return ""


def alias_chain(call: ci.Cursor) -> list[tuple[str, tuple[str, ...]]]:
    """What the alias a dependent call names as its template argument stands for, written, through aliases of aliases.

    ``ConcreteQueryView<Tag>`` is ``QueryView<Tag>``, which is ``urd::index_view<Query<Tag>, Repository>``: each with
    the template parameters of the alias template it is written in.
    """
    reference = next(
        (
            each
            for each in call.walk_preorder()
            if each.kind in REFERENCES
            and each.referenced is not None
            and (each.referenced.kind in ALIASES or each.referenced.kind == ci.CursorKind.TYPE_ALIAS_TEMPLATE_DECL)
        ),
        None,
    )
    chain: list[tuple[str, tuple[str, ...]]] = []
    declaration = None if reference is None else reference.referenced
    while declaration is not None and len(chain) < 8:  # noqa: PLR2004 (aliases of aliases, bounded)
        parameters = tuple(
            each.spelling for each in declaration.get_children() if each.kind == ci.CursorKind.TEMPLATE_TYPE_PARAMETER
        )
        alias = aliased(declaration) if declaration.kind == ci.CursorKind.TYPE_ALIAS_TEMPLATE_DECL else declaration
        if alias is None:
            break
        text = "".join(words(alias))
        chain.append((text.split("=", 1)[1].removesuffix(";") if "=" in text else "", parameters))
        declaration = next(
            (
                each.referenced
                for each in alias.walk_preorder()
                if each.kind in REFERENCES
                and each.referenced is not None
                and each.referenced != declaration
                and (each.referenced.kind in ALIASES or each.referenced.kind == ci.CursorKind.TYPE_ALIAS_TEMPLATE_DECL)
            ),
            None,
        )
    return [each for each in chain if each[0]]


def desugared(argument: ci.Type) -> list[str]:
    """The spellings of `argument` from as written to canonical, without spaces.

    Each alias it names, what that stands for, and so on: ``ObjectView``, ``urd::index_view<lib::Object, int>``,
    ``urd::index_view<lib::Family<...>, int>``.
    """
    spellings: list[str] = []
    current: ci.Type | None = argument
    while current is not None and len(spellings) < 8:  # noqa: PLR2004 (aliases of aliases, bounded)
        spellings.append(current.spelling.replace(" ", "").removeprefix("::"))
        declaration = current.get_declaration()
        current = declaration.underlying_typedef_type if declaration.kind in ALIASES else None
    spellings.append(argument.get_canonical().spelling.replace(" ", ""))
    return list(dict.fromkeys(spellings))


def resolved_tags(call: ci.Cursor, function: ci.Cursor, binder: str) -> set[Tag]:
    """What the call `call` of the instantiated `binder` `function` binds (binding_tags), from its template argument.

    libclang hands out the argument's type desugared; an alias as written is the call's first type reference. Its
    namespaces are known only of the canonical spelling: one as written may leave out those it is written in.
    """
    tags: set[Tag] = set()
    written = next((each for each in call.walk_preorder() if each.kind in REFERENCES), None)
    alias = None if written is None or written.referenced is None else written.referenced
    argument = function.get_template_argument_type(0)
    spellings = desugared(argument)
    if alias is not None and alias.kind in ALIASES:
        spellings = desugared(alias.underlying_typedef_type) + spellings
        if binder == "bind_data":
            tags.add((alias.spelling, "", ()))
    canonical = argument.get_canonical().spelling.replace(" ", "")
    for spelled in spellings:
        if tag := tag_from(spelled, binder):
            tags.add((unqualified(tag), tag if spelled == canonical else "", ()))
    return tags


def binding_tags(call: ci.Cursor, binder: str, parameters: tuple[str, ...] = ()) -> set[Tag]:
    """What the call `call` of `binder` binds, each as (without namespaces, with them or "" where only written).

    bind_data and bind_view name a record's tag (a view's is its record's), bind_value a value's class.
    """
    function = call.referenced
    if function is not None and function.get_num_template_arguments() > 0:
        return resolved_tags(call, function, binder)
    tags: set[Tag] = set()
    # A dependent call (in a template: bind_data<State<Kind>>) has no instantiation to read: its argument as written,
    # and for a view what the alias it names stands for.
    for text, more in [(each, ()) for each in written_types(call, binder)] + alias_chain(call):
        if tag := tag_from(text, binder):
            tags.add((unqualified(tag), "", tuple(dict.fromkeys(parameters + more))))
    return tags


def written_types(call: ci.Cursor, binder: str) -> list[str]:
    """The template argument of the dependent call `call` of `binder` as written, and what an alias it names stands for.

    A local alias: ``using V = urd::index_view<Atom<T, F>, C>``.
    """
    texts = [written_argument(words(call), binder)] + [text for text, _ in alias_chain(call)]
    return [each for each in texts if each]


def tag_from(text: str, binder: str) -> str:
    """The tag a binder's template argument `text` binds.

    It is a view's record's for bind_view, a value's class for bind_value, the argument itself for bind_data.
    """
    if binder == "bind_view":
        return view_tag(text)
    if binder == "bind_value":
        return text.split("<", 1)[0]
    return text


def helpers(nodes: list[ci.Cursor]) -> dict[tuple[str, str, int, int], tuple[tuple[str, ...], list[tuple[str, str]]]]:
    """The function templates among `nodes` that call a binder, by key_of.

    Each is its type parameters and its binder calls, as (binder, an argument as written of written_types).
    """
    written: dict[tuple[str, str, int, int], tuple[tuple[str, ...], list[tuple[str, str]]]] = {}
    for function in nodes:
        if function.kind != ci.CursorKind.FUNCTION_TEMPLATE:
            continue
        parameters = tuple(
            each.spelling for each in function.get_children() if each.kind == ci.CursorKind.TEMPLATE_TYPE_PARAMETER
        )
        texts = [
            (binder, text)
            for call in function.walk_preorder()
            if call.kind == ci.CursorKind.CALL_EXPR and (binder := callee(call)) in BINDERS
            for text in written_types(call, binder)
        ]
        if parameters and texts:
            written[key_of(function)] = (parameters, texts)
    return written


def instantiated_tags(nodes: list[ci.Cursor]) -> dict[str, set[Tag]]:
    """What the function templates among `nodes` bind where `nodes` call them with template arguments.

    A helper (``template<typename V> void bind_fact_view(m) { bind_view<V>(m); }``) binds what its argument is: its
    binder calls' arguments as written, each parameter replaced by the argument a call passes.
    """
    written = helpers(nodes)
    tags: dict[str, set[Tag]] = {binder: set() for binder in BINDERS}
    for call in nodes:
        function = call.referenced if call.kind == ci.CursorKind.CALL_EXPR else None
        if (
            function is None
            or function.kind != ci.CursorKind.FUNCTION_DECL
            or function.get_num_template_arguments() <= 0
        ):
            continue
        template = ci.conf.lib.clang_getSpecializedCursorTemplate(function)
        if template is None or key_of(template) not in written:
            continue
        parameters, texts = written[key_of(template)]
        arguments = [
            function.get_template_argument_type(i).get_canonical().spelling.replace(" ", "")
            for i in range(function.get_num_template_arguments())
        ]
        for binder, text in texts:
            for parameter, argument in zip(parameters, arguments, strict=False):
                if argument:
                    text = re.sub(rf"\b{re.escape(parameter)}\b", argument, text)  # noqa: PLW2901
            if tag := tag_from(text, binder):
                tags[binder].add((unqualified(tag), "", ()))
    return tags


def in_urd_python(cursor: ci.Cursor) -> bool:
    """Whether `cursor` is declared in namespace urd::python: urd's own binders, which bind by hand by design."""
    return qualified(cursor).startswith("urd::python::")


def binding_nodes(unit: ci.TranslationUnit, path: Path) -> Iterator[ci.Cursor]:
    """The own nodes of the binding source `path` (own_nodes) outside urd's own binders (urd::python)."""
    for child in unit.cursor.get_children():
        if declared_in(child, path):
            yield from walk_outside_urd_python(child)


def walk_outside_urd_python(cursor: ci.Cursor) -> Iterator[ci.Cursor]:
    """The nodes under `cursor` in preorder, but those of a declaration of namespace urd::python."""
    if cursor.kind.is_declaration() and cursor.kind != ci.CursorKind.NAMESPACE and in_urd_python(cursor):
        return
    yield cursor
    for child in cursor.get_children():
        yield from walk_outside_urd_python(child)


def bound(unit: ci.TranslationUnit, path: Path) -> dict[str, set[Tag]]:
    """What the binding source `path` (parsed: `unit`) binds, by binder (BINDERS): the tags of binding_tags."""
    tags: dict[str, set[Tag]] = {binder: set() for binder in BINDERS}
    nodes = list(binding_nodes(unit, path))
    for call in nodes:
        if call.kind == ci.CursorKind.CALL_EXPR and (binder := callee(call)) in BINDERS:
            tags[binder] |= binding_tags(call, binder)
    for binder, more in instantiated_tags(nodes).items():
        tags[binder] |= more
    # A call in a function template, once more with its parameters: its tag may be a pattern over them.
    for function in nodes:
        if function.kind != ci.CursorKind.FUNCTION_TEMPLATE:
            continue
        parameters = tuple(
            each.spelling
            for each in function.get_children()
            if each.kind in {ci.CursorKind.TEMPLATE_TYPE_PARAMETER, ci.CursorKind.TEMPLATE_NON_TYPE_PARAMETER}
        )
        for call in function.walk_preorder():
            if call.kind == ci.CursorKind.CALL_EXPR and (binder := callee(call)) in BINDERS:
                tags[binder] |= binding_tags(call, binder, parameters)
    return tags


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


def initializer(variable: ci.Cursor) -> ci.Cursor | None:
    """The expression `variable` is initialized with; None where it has none."""
    expressions = [each for each in variable.get_children() if each.kind.is_expression()]
    return expressions[-1] if expressions else None


def root_of(expression: ci.Cursor) -> ci.Cursor:
    """The object a chain of member calls on it starts from (``class_<X>(m)`` of ``class_<X>(m).def(...)``)."""
    current = expression
    while True:
        children = list(current.get_children())
        if not children:
            return current
        if current.kind in EXPRESSION_WRAPPERS or current.kind == ci.CursorKind.MEMBER_REF_EXPR:
            current = children[0]
        elif current.kind == ci.CursorKind.CALL_EXPR and children[0].kind in EXPRESSION_WRAPPERS | {
            ci.CursorKind.MEMBER_REF_EXPR
        }:
            head = children[0]
            while head.kind in EXPRESSION_WRAPPERS and list(head.get_children()):
                head = next(iter(head.get_children()))
            if head.kind != ci.CursorKind.MEMBER_REF_EXPR:
                return current
            current = head
        else:
            return current


def constructs(cursor: ci.Cursor, path: Path) -> bool:
    """Whether `cursor`, of the source `path`, may construct a class there.

    A class is bound where it is constructed (a variable, a call of its constructor, unnamed in a template); a .def on
    one is not, nor is a variable that holds a class a call returned (bind_data's, a helper's).
    """
    if cursor.kind not in CONSTRUCTIONS or not declared_in(cursor, path):
        return False
    if cursor.kind == ci.CursorKind.CALL_EXPR and cursor.spelling not in {"class_", ""}:
        return False
    if cursor.kind == ci.CursorKind.VAR_DECL:
        value = initializer(cursor)
        if value is None:
            return False
        root = root_of(value)
        named_call = root.kind == ci.CursorKind.CALL_EXPR and bool(callee(root))
        return root.spelling == "class_" or (not named_call and bool(constructed(root)))
    return True


def hand_bound(unit: ci.TranslationUnit, path: Path) -> list[tuple[int, str]]:
    """The classes of a record's data or view, or any other class, that the binding source `path` defines itself.

    Each is (line, record tag), "*" for a record's in a template, or "class <name>" for another class.

    A class bind_data, bind_view or bind_value defines is in urd's header, not in `path`, so only what the file writes
    by hand is found.
    """
    found: set[tuple[int, str]] = set()
    for cursor in binding_nodes(unit, path):
        if not constructs(cursor, path):
            continue
        bound_type = cursor.type.get_canonical()
        dependent = "type-parameter" in bound_type.spelling or bound_type.spelling == "auto"
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
        if not bound_type.spelling.startswith("nanobind::class_<") or bound_type.get_num_template_arguments() < 1:
            continue
        argument = bound_type.get_template_argument_type(0).get_canonical().spelling
        if argument.startswith("urd::data<"):
            found.add((cursor.location.line, tag_of(argument, "data")))
        elif argument.startswith(VIEWS):
            found.add((cursor.location.line, tag_of(argument, argument[len("urd::") : argument.index("<")])))
        else:
            # Any other class, by its class or template with its namespaces: a value's (S4) is bound by bind_value.
            found.add((cursor.location.line, "class " + argument.split("<", 1)[0]))
    return sorted(found)


VALUE_KINDS = {
    ci.CursorKind.STRUCT_DECL,
    ci.CursorKind.CLASS_DECL,
    ci.CursorKind.CLASS_TEMPLATE,
    ci.CursorKind.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION,
}


def classes(cursor: ci.Cursor) -> Iterator[ci.Cursor]:
    """`cursor`, where it is a class, and the classes nested in it, in preorder."""
    if cursor.kind not in VALUE_KINDS:
        return
    yield cursor
    for child in cursor.get_children():
        yield from classes(child)


def value_of(cursor: ci.Cursor) -> tuple[str, list[str]] | None:
    """The value `cursor` defines: its name with its namespaces, and what of it S4 does not allow.

    A value (S4) is a struct or class template, no record, with a static fields(); None where `cursor` defines none.
    """
    if cursor.kind not in VALUE_KINDS or not cursor.is_definition():
        return None
    children = list(cursor.get_children())
    if not any(each.spelling == "fields" and each.kind == ci.CursorKind.CXX_METHOD for each in children):
        return None
    say: list[str] = []
    name = next((each for each in children if each.spelling == "name"), None)
    if name is None or name.kind != ci.CursorKind.VAR_DECL or "string_view" not in name.type.spelling:
        say.append("has no static std::string_view name")
    methods = [each for each in children if each.kind == ci.CursorKind.CXX_METHOD and each.spelling in METHODS]
    if "identifying_members" not in [each.spelling for each in methods]:
        say.append("has no identifying_members()")
    fields = [each.spelling for each in children if each.kind == ci.CursorKind.FIELD_DECL]
    say.extend(list_findings(methods, fields, indexed=False))
    return qualified(cursor), say


@dataclass(frozen=True)
class Defined:
    """What a file that defines records, mixins or values holds, and what of it S1, S2 and S4 do not allow.

    A value is (its name with its namespaces, file, line); a free function a functions() lists is (its key_of, the
    findings of free_findings).
    """

    records: list[Record] = field(default_factory=list[Record])
    mixins: list[Mixin] = field(default_factory=list[Mixin])
    record_found: list[Finding] = field(default_factory=list[Finding])
    values: list[tuple[str, str, int]] = field(default_factory=list[tuple[str, str, int]])
    value_found: list[Finding] = field(default_factory=list[Finding])
    free: list[tuple[tuple[str, str, int, int], list[str]]] = field(
        default_factory=list[tuple[tuple[str, str, int, int], list[str]]]
    )


def file_findings(repository: Path, file: str, data: Database) -> Defined:
    """The records, mixins, values and listed free functions `file` defines; what of them S1 and S4 do not allow."""
    path = (repository / file).resolve()
    unit, error = data.unit(path)
    defined = Defined()
    if unit is None:
        defined.record_found.append(Finding(file, f"does not parse: {error}"))
        return defined
    seen: set[tuple[str, str, int, int]] = set()
    for cursor in top_level(unit.cursor, path):
        for function in listed_in(cursor):
            parent = function.semantic_parent
            if (key := key_of(function)) not in seen and (parent is None or parent.kind not in VALUE_KINDS):
                seen.add(key)
                defined.free.append((key, free_findings(function)))
        if in_urd(cursor, "data"):
            record, say = record_findings(cursor)
            defined.records.append(
                Record(record.tag, record.fields, record.line, file, record.parameters, record.header, record.qualified)
            )
            defined.record_found.extend(Finding(f"{file}:{record.line}", f"data<{record.tag}> {what}") for what in say)
        elif in_urd(cursor, "view_mixin"):
            defined.mixins.append(mixin_of(cursor, file))
        elif in_urd(cursor, "builder"):
            continue
        else:
            values_in(cursor, file, defined)
    return defined


def values_in(cursor: ci.Cursor, file: str, defined: Defined) -> None:
    """Adds to `defined` the values `cursor` and the classes nested in it define, and what of them S4 does not allow."""
    for each in classes(cursor):
        if (value := value_of(each)) is None:
            continue
        name, say = value
        where = f"{file}:{each.location.line}"
        defined.values.append((name, file, each.location.line))
        defined.value_found.extend(Finding(where, f"value {name} {what}") for what in say)


def bound_by(expression: ci.Cursor, depth: int = 0) -> str:
    """The binder (BINDERS) whose class `expression` is: through calls on it, variables and helpers; "" for none.

    A helper is a function of the unit that returns such a class.
    """
    current: ci.Cursor | None = expression
    while current is not None:
        if current.kind == ci.CursorKind.CALL_EXPR:
            name = callee(current)
            if name in BINDERS:
                return name
            function = current.referenced
            if (
                depth < 3  # noqa: PLR2004 (helpers of helpers, bounded)
                and function is not None
                and function.kind
                in {
                    ci.CursorKind.FUNCTION_DECL,
                    ci.CursorKind.FUNCTION_TEMPLATE,
                }
            ):
                definition: ci.Cursor | None = function.get_definition()
                for each in [] if definition is None else list(definition.walk_preorder()):
                    if each.kind == ci.CursorKind.RETURN_STMT:
                        values = list(each.get_children())
                        if values and (binder := bound_by(values[0], depth + 1)):
                            return binder
        if (
            current.kind == ci.CursorKind.DECL_REF_EXPR
            and current.referenced is not None
            and current.referenced.kind == ci.CursorKind.VAR_DECL
            and depth < 3  # noqa: PLR2004
        ):
            value = initializer(current.referenced)
            return "" if value is None else bound_by(value, depth + 1)
        children = list(current.get_children())
        current = children[0] if children else None
    return ""


def views_first(function: ci.Cursor) -> bool:
    """Whether `function` (a function, a function template or a lambda) is one of a view: its sole parameter a urd view.

    One that takes more (options, a context, limits) is an algorithm over the view, bound with m.def.
    """
    parameters = [each for each in function.get_children() if each.kind == ci.CursorKind.PARM_DECL]
    if len(parameters) != 1:
        return False
    spelling = parameters[0].type.get_canonical().spelling.removeprefix("const ")
    return spelling.startswith(VIEWS)


def derived_findings(unit: ci.TranslationUnit, path: Path, file: str) -> list[tuple[str, Finding]]:
    """What S3 and S4 do not allow of the .def calls in source `file` (its path `path`, parsed: `unit`), by rule.

    A class bind_data or bind_view returns gets no .def (what a view offers is its functions(), S2), nor one
    bind_value returns (S4), and a module no function over a view.
    """
    found: list[tuple[str, Finding]] = []
    for call in binding_nodes(unit, path):
        if call.kind != ci.CursorKind.CALL_EXPR or not declared_in(call, path):
            continue
        name = callee(call)
        if not name.startswith("def"):
            continue
        children = list(call.get_children())
        head = children[0] if children else None
        while head is not None and head.kind in EXPRESSION_WRAPPERS and list(head.get_children()):
            head = next(iter(head.get_children()))
        if head is None or head.kind != ci.CursorKind.MEMBER_REF_EXPR or not list(head.get_children()):
            continue
        receiver = next(iter(head.get_children()))
        where = f"{file}:{call.location.line}"
        binder = bound_by(receiver)
        if binder == "bind_value":
            found.append(("S4", Finding(where, f"{name} on a value's class: bind_value binds a value alone")))
            continue
        if binder:
            found.append(("S3", Finding(where, f"{name} on a record's class: list the function in its functions()")))
            continue
        if name != "def" or "module_" not in receiver.type.get_canonical().spelling:
            continue
        functions = [
            (each.referenced or each) if each.kind == ci.CursorKind.DECL_REF_EXPR else each
            for argument in children[1:]
            for each in argument.walk_preorder()
            if each.kind == ci.CursorKind.LAMBDA_EXPR
            or (
                each.kind == ci.CursorKind.DECL_REF_EXPR
                and each.referenced is not None
                and each.referenced.kind in {ci.CursorKind.FUNCTION_DECL, ci.CursorKind.FUNCTION_TEMPLATE}
            )
        ]
        if functions and views_first(functions[0]):
            found.append(
                ("S3", Finding(where, "binds a function over a view in a module: list it in the view's functions()"))
            )
    return found


@dataclass(frozen=True)
class Bindings:
    """What a binding source binds (bound), binds by hand (hand_bound) and defines on bound classes (derived_findings).

    Its error where it does not parse, with nothing read.
    """

    file: str
    error: str | None = None
    tags: dict[str, set[Tag]] = field(default_factory=dict[str, set[Tag]])
    by_hand: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])
    derived: list[tuple[str, Finding]] = field(default_factory=list[tuple[str, Finding]])


def binding_read(repository: Path, file: str, data: Database) -> Bindings:
    """The binding source `file` parsed, read and dropped.

    Only what is read is kept, never its tree, which holds everything the source includes.
    """
    path = (repository / file).resolve()
    unit, error = data.unit(path)
    if unit is None:
        return Bindings(file, error)
    return Bindings(file, None, bound(unit, path), hand_bound(unit, path), derived_findings(unit, path, file))


def served_by(mixin: Mixin, records: list[Record]) -> list[Record]:
    """The records a held form's `mixin` serves: those of its tag and header, or its tag as a pattern covers."""
    own = [each for each in records if (each.qualified, each.header) == (mixin.qualified, mixin.header)]
    return own or [each for each in records if covers(mixin, each)]


def pair_findings(
    found: dict[str, list[Finding]],
    records: list[Record],
    mixins: list[Mixin],
    tags: dict[str, set[Tag]] | None,
) -> None:
    """Adds to `found` what S2 and S3 do not allow of `records` paired with their `mixins`.

    `tags` is what the library binds, None where it has no bindings of its own (python/src) to bind its records in.
    """
    held = [each for each in mixins if each.inherits]
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
        # A library's records are bound, where it has bindings (python/src); a test's own records are not.
        if not record.file.startswith("include/") or tags is None:
            continue
        if not any(binds_qualified(record, tag) for tag in tags.get("bind_data", set())):
            found["S3"].append(Finding(where, f"{record.tag} is not bound with urd::python::bind_data"))
        elif not any(binds_qualified(record, tag) for tag in tags.get("bind_view", set())):
            found["S3"].append(Finding(where, f"{record.tag} has no view bound with urd::python::bind_view"))
    for mixin in held:
        served[id(mixin)] = (mixin, served_by(mixin, records))
    for mixin, served_records in served.values():
        found["S2"].extend(
            Finding(f"{mixin.file}:{mixin.line}", what)
            for what in order_findings(mixin, served_records) + listing_findings(mixin, served_records)
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


def value_bound(name: str, tags: set[Tag]) -> bool:
    """Whether a bind_value of `tags` binds the value `name` (with its namespaces): by them where known."""
    return any(
        qualified_name == name if qualified_name else short == name.rsplit("::", 1)[-1]
        for short, qualified_name, _ in tags
    )


def relative_to(repository: Path, file: str) -> str | None:
    """`file` relative to `repository`, None where it lies outside."""
    path = Path(file).resolve()
    return path.relative_to(repository).as_posix() if path.is_relative_to(repository) else None


@functools.cache
def check(repository: Path, compile_commands: Path, jobs: int | None = None) -> dict[str, list[Finding]]:
    """The findings of the record and value schemas in `repository`, by rule (S1, S2, S3, S4).

    Every tracked header and source that defines a urd::data or urd::view_mixin specialization, a value or a function
    list is parsed once (a header alone, a source with its own compile command); a record's view mixins are those of
    its tag, as T, data<T> or builder<T>, wherever they are defined. A file that does not parse is a finding: of S1
    where it defines records, of S3 where it binds them. A source is parsed with its own compile command, or with that
    of the unity source that includes it; one that has neither is not parsed with another's. `jobs` files are parsed
    at once, each in a process of its own that hands back what it read, in the files' order.
    """
    files = tracked(repository)
    data = database(repository, compile_commands)
    texts = {each: (repository / each).read_text(errors="replace") for each in files if each.endswith((".cpp", ".hpp"))}
    # The bindings: those of python/src, and any other file that binds with nanobind (a test's binding module, a
    # library's binding header)
    sources = [
        each
        for each, text in texts.items()
        if (each.startswith("python/src/") or "nanobind" in text) and any(word in text for word in BINDS)
    ]
    defining = [each for each, text in texts.items() if DEFINES.search(text)]
    # Each file parsed once, in a worker that keeps only what it read; one that does not parse is a finding, not a
    # skip: what it binds is not known.
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        read = list(pool.map(binding_read, repeat(repository), sources, repeat(data)))
        defined = list(pool.map(file_findings, repeat(repository), defining, repeat(data)))
    tags: dict[str, set[Tag]] = {binder: set() for binder in BINDERS}
    for each in read:
        for binder, more in each.tags.items():
            tags[binder] |= more
    records: list[Record] = []
    mixins: list[Mixin] = []
    found: dict[str, list[Finding]] = {"S1": [], "S2": [], "S3": [], "S4": []}
    values: dict[str, tuple[str, int]] = {}
    free: dict[tuple[str, str, int, int], list[str]] = {}
    for each in defined:
        records.extend(each.records)
        mixins.extend(each.mixins)
        found["S1"].extend(each.record_found)
        values.update({name: (file, line) for name, file, line in each.values})
        found["S4"].extend(each.value_found)
        free.update(each.free)
    # A record's mixins: those of its tag (with its namespaces) and its template header (one specialization of a tag per
    # shape of its parameters, e.g. data<Concept<F, Tag>> for each concept Tag satisfies, has the mixin of the same
    # header). A held form's mixin that inherits the tag's has its base's getters and is checked for the rest.
    for mixin in mixins:
        found["S2"].extend(Finding(f"{mixin.file}:{mixin.line}", f"{mixin.qualified}: {what}") for what in mixin.own)
    # A free function a functions() lists, wherever it is listed, once: where it is written, if in this repository.
    for key, what in free.items():
        if what and (file := relative_to(repository.resolve(), key[1])) is not None:
            found["S2"].extend(Finding(f"{file}:{key[2]}", each) for each in what)
    # A library binds its records and values where it has bindings of its own (python/src)
    bindings = any(each.startswith("python/src/") for each in sources)
    pair_findings(found, records, mixins, tags if bindings else None)
    for name, (file, line) in values.items():
        if file.startswith("include/") and bindings and not value_bound(name, tags["bind_value"]):
            found["S4"].append(Finding(f"{file}:{line}", f"value {name} is not bound with urd::python::bind_value"))
    binding_findings(found, read, records, set(values))
    return found


def binding_findings(
    found: dict[str, list[Finding]], read: list[Bindings], records: list[Record], values: set[str]
) -> None:
    """Adds to `found` what S3 and S4 do not allow of the binding sources `read`: not parsing, binding by hand, .def."""
    for each in read:
        if each.error is not None:
            found["S3"].append(Finding(each.file, f"does not parse: {each.error}"))
            continue
        hand_findings(found, each.file, each.by_hand, records, values)
        for rule, finding in each.derived:
            found[rule].append(finding)
