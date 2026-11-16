# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.rules.schema.records on a small library: a record that follows S1-S3, and one that breaks each."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("clang.cindex")
if shutil.which("clang++") is None:
    pytest.skip("needs clang++ for clang's own headers", allow_module_level=True)

from pybrokkr.rules.schema.records import Record, binds, check, forwarding

# Just enough of urd for the headers below to parse.
URD = """#pragma once
#include <cstddef>
#include <cstdint>
namespace urd {
template<typename T> struct data;
template<typename T> struct index { std::uint32_t value; };
template<typename T> struct flat_vector { T* begin; };
template<auto... Ms> struct Members {};
template<std::size_t N> struct fixed_string {
    char text[N];
    constexpr fixed_string(const char (&s)[N]) { for (std::size_t i = 0; i < N; ++i) text[i] = s[i]; }
};
template<fixed_string Name, auto Member> struct field {};
template<typename... Fs> struct Fields {};
template<typename... Fs> constexpr auto members_of(Fields<Fs...>) noexcept { return 0; }
template<typename T, typename V> struct view_mixin {};
template<typename V> using record_of = typename V::record;
template<typename T, typename C> struct index_view {};
}
"""
DECLARATIONS = """#pragma once
namespace lib { struct Atom {}; struct Cost {}; struct Loose {}; struct Term {}; struct Local {}; struct Predicate {}; }
// A tag named by an alias of a family member, as tyr names its objects.
namespace lib { template<typename T> struct Family {}; struct ObjectTag {}; using Object = Family<ObjectTag>; }
"""
ATOM_DATA = """#pragma once
#include "lib/declarations.hpp"
#include <urd/elements/flat.hpp>
namespace urd {
template<> struct data<lib::Atom> {
    urd::index<lib::Atom> index;
    urd::index<lib::Predicate> predicate;
    urd::flat_vector<std::uint32_t> objects;
    data() = default;
    data(urd::index<lib::Predicate> predicate_, urd::flat_vector<std::uint32_t> objects_) :
        index(), predicate(predicate_), objects(objects_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept {
        return urd::Fields<urd::field<"predicate", &data::predicate>, urd::field<"objects", &data::objects>> {};
    }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept {
        return urd::Members<&data::index, &data::predicate, &data::objects> {};
    }
};
}
"""
ATOM_VIEW = """#pragma once
#include "lib/atom_data.hpp"
namespace urd {
template<typename V> struct view_mixin<lib::Atom, V> {
private:
    const V& self() const noexcept { return static_cast<const V&>(*this); }
public:
    auto get_predicate() const noexcept { return self().template member<&urd::record_of<V>::predicate>(); }
    auto get_objects() const noexcept { return self().template member<&urd::record_of<V>::objects>(); }
    // Derived from the getters: allowed after them.
    auto get_arity() const noexcept { return get_objects().size(); }
};
}
"""
LOOSE_DATA = """#pragma once
#include "lib/declarations.hpp"
#include "lib/atom_view.hpp"
#include <urd/elements/flat.hpp>
#include <string>
namespace urd {
template<> struct data<lib::Loose> {
    std::string name;
    data() = default;
    data(const data&) = delete;
    static constexpr auto cista_members() noexcept { return urd::Members<&data::name> {}; }
};
}
namespace lib { inline int helper() { return 0; } }
"""
WEIGHT = "#pragma once\nnamespace lib { enum class Weight : int {}; }\n"
# A copyable record: trivially copyable, it declares copyable() instead of the five.
# A record whose tag is an alias: bound by bind_data of the alias.
ALIAS_DATA = """#pragma once
#include "lib/declarations.hpp"
#include <type_traits>
#include <urd/elements/flat.hpp>
namespace urd {
template<> struct data<lib::Object> {
    urd::index<lib::Object> index;
    int count = 0;
    data() = default;
    explicit data(int count_) : index(), count(count_) {}
    static constexpr bool copyable() noexcept
    {
        static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
        return true;
    }
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &data::count>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::count> {}; }
};
}
"""
COST_DATA = """#pragma once
#include "lib/declarations.hpp"
#include "lib/weight.hpp"
#include <type_traits>
#include <urd/elements/flat.hpp>
namespace urd {
template<> struct data<lib::Cost> {
    urd::index<lib::Cost> index;
    lib::Weight weight;
    data() = default;
    explicit data(lib::Weight weight_) : index(), weight(weight_) {}
    static constexpr bool copyable() noexcept
    {
        static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
        return true;
    }
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"weight", &data::weight>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::weight> {}; }
};
}
"""
# A second record: the five special members S1 asks of every record, its identity named member by member.
TERM_DATA = """#pragma once
#include "lib/declarations.hpp"
#include <urd/elements/flat.hpp>
namespace urd {
template<> struct data<lib::Term> {
    urd::index<lib::Term> index;
    urd::flat_vector<std::uint32_t> objects;
    data() = default;
    explicit data(urd::flat_vector<std::uint32_t> objects_) : index(), objects(objects_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"objects", &data::objects>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::Members<&data::objects> {}; }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::objects> {}; }
};
}
"""
# A view that reads the record's stored form: S2 forbids data() in a mixin.
TERM_VIEW = """#pragma once
#include "lib/term_data.hpp"
namespace urd {
template<typename V> struct view_mixin<lib::Term, V> {
private:
    const V& self() const noexcept { return static_cast<const V&>(*this); }
public:
    auto get_objects() const noexcept { return self().data().objects; }
};
}
"""
# A record a test defines for itself, in a source, and a mixin override for its data<T> views: both are checked.
LOCAL_TEST = """#include "lib/declarations.hpp"
#include <urd/elements/flat.hpp>
namespace urd {
template<> struct data<lib::Local> {
    urd::index<lib::Local> index;
    int count = 0;
};
template<typename V> struct view_mixin<urd::data<lib::Local>, V> {
    auto get_count() const noexcept { return static_cast<const V&>(*this).data().count; }
};
}
"""
# A binding source: Atom's data and view bound, and Atom's data bound by hand besides, which S3 forbids.
BINDING = """#include "lib/atom_data.hpp"
#include "lib/object_data.hpp"
#include "pylib/flags.hpp"  // found only through the include path of the unity source that compiles this one
namespace nanobind {
template<typename T> struct class_ {
    explicit class_(int) {}
    ~class_() {}  // not trivial, as nanobind's: a discarded class is a temporary with cleanups
    template<typename F> class_& def(const char*, F) { return *this; }
};
}
namespace urd::python {
template<typename T> nanobind::class_<urd::data<T>> bind_data(int) {
    return nanobind::class_<urd::data<T>>(0);
}
template<typename V> nanobind::class_<V> bind_view(int) { return nanobind::class_<V>(0); }
}
struct FluentTag {};
struct AtomPy {
    int get_arity() const { return 0; }
    template<typename F> int get_literals() const { return 0; }
    bool contains(int) const { return false; }
    bool contains(double) const { return false; }
};
void bind_derived() {
    auto held = urd::python::bind_data<lib::Atom>(0);  // a variable holding the bound class: no hand binding
    urd::python::bind_data<lib::Atom>(0);  // the class bind_data returns, unnamed: no hand binding
    urd::python::bind_data<lib::Object>(0);  // a record named by an alias
    urd::python::bind_view<AtomPy>(0)
        .def("get_arity", &AtomPy::get_arity)
        .def("get_fluent_literals", &AtomPy::template get_literals<FluentTag>)
        .def("contains", static_cast<bool (AtomPy::*)(int) const>(&AtomPy::contains))
        .def("arity", &AtomPy::get_arity)
        .def("get_arity", [](const AtomPy& view) { return view.get_arity(); });
}
// urd::python::bind_data<lib::Repository>(m);
void bind() { nanobind::class_<urd::data<lib::Atom>> by_hand(0); }
template<typename T> void bind_any() { nanobind::class_<urd::data<T>> generic(0); }
template<typename T> using ViewOf = urd::index_view<T, int>;
template<typename T> void bind_aliased_data() {
    using V = urd::data<T>;
    auto aliased_data = nanobind::class_<V>(0);
}
template<typename T> void bind_aliased_view() {
    using V = ViewOf<T>;
    nanobind::class_<V>(0).def("get_count", 0);
}
template<typename T> void bind_other() { auto other = nanobind::class_<T>(0); }  // not a record's: no finding
"""


def library(root: Path) -> tuple[Path, Path]:
    """A git repository at `root` with the headers above, and its compile database."""
    files = {
        "include/urd/elements/flat.hpp": URD,
        "include/lib/declarations.hpp": DECLARATIONS,
        "include/lib/atom_data.hpp": ATOM_DATA,
        "include/lib/atom_view.hpp": ATOM_VIEW,
        "include/lib/loose_data.hpp": LOOSE_DATA,
        "include/lib/weight.hpp": WEIGHT,
        "include/lib/cost_data.hpp": COST_DATA,
        "include/lib/object_data.hpp": ALIAS_DATA,
        "include/lib/term_data.hpp": TERM_DATA,
        "include/lib/term_view.hpp": TERM_VIEW,
        "tests/unit/local.cpp": LOCAL_TEST,
        "src/lib.cpp": '#include "lib/atom_view.hpp"\n',
        "python/src/pylib/module.cpp": BINDING,
        "python/src/pylib/flags.hpp": "#pragma once\n",
    }
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(root)], check=True)
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    # The binding source is compiled by a unity source (not tracked: generated), which alone has its include path.
    unity = root / "build/unity_pylib.cxx"
    unity.parent.mkdir()
    unity.write_text(f'#include "{root / "python/src/pylib/module.cpp"}"\n')
    database = root / "compile_commands.json"
    flags = f"clang++ -std=c++20 -I{root / 'include'}"
    database.write_text(
        json.dumps(
            [
                {"directory": str(root), "file": "src/lib.cpp", "command": f"{flags} -c src/lib.cpp"},
                {"directory": str(root), "file": "tests/unit/local.cpp", "command": f"{flags} -c tests/unit/local.cpp"},
                {"directory": str(root), "file": str(unity), "command": f"{flags} -I{root / 'python/src'} -c {unity}"},
            ]
        )
    )
    return root, database


def test_a_record_that_follows_the_schemas_has_no_findings(tmp_path: Path) -> None:
    found = check(*library(tmp_path))
    assert not [each for rule in found.values() for each in rule if "atom_data" in each.path]


def test_a_record_that_breaks_each_schema(tmp_path: Path) -> None:
    found = check(*library(tmp_path))
    loose = {rule: {each.rule for each in found[rule] if "loose_data" in each.path} for rule in found}
    assert "data<Loose> has 1 constructors, not data() = default and one from the 1 fields" in loose["S1"]
    assert any(each.startswith("data<Loose> declares ['copy constructor deleted'], neither") for each in loose["S1"])
    assert any("has the functions ['cista_members']" in each for each in loose["S1"])
    assert loose["S2"] == {"Loose: has no urd::view_mixin<Loose, V>"}
    assert loose["S3"] == {"Loose is not bound with urd::python::bind_data"}


def test_a_record_with_one_field_follows_s1(tmp_path: Path) -> None:
    assert not [each for each in check(*library(tmp_path))["S1"] if "term_data" in each.path]


def test_a_record_may_be_identified_by_its_index(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    identity = "static constexpr auto identifying_members() noexcept { return urd::Members<&data::"
    by_index = TERM_DATA.replace(identity + "objects> {}; }", identity + "index> {}; }")
    assert by_index != TERM_DATA
    (root / "include/lib/term_data.hpp").write_text(by_index)
    assert not [each for each in check(root, database)["S1"] if "term_data" in each.path]


def test_a_record_without_fields_has_only_its_default_constructor(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    empty = (
        TERM_DATA.replace("    urd::flat_vector<std::uint32_t> objects;\n", "")
        .replace("    explicit data(urd::flat_vector<std::uint32_t> objects_) : index(), objects(objects_) {}\n", "")
        .replace('urd::Fields<urd::field<"objects", &data::objects>>', "urd::Fields<>")
        .replace("urd::Members<&data::objects>", "urd::Members<>")
        .replace("urd::Members<&data::index, &data::objects>", "urd::Members<&data::index>")
    )
    assert "objects" not in empty
    (root / "include/lib/term_data.hpp").write_text(empty)
    found = [each.rule for each in check(root, database)["S1"] if "term_data" in each.path]
    assert not [each for each in found if "constructors" in each]


# One tag, two shapes: records told apart only by the concept their Tag satisfies, each with the mixin of its shape.
SHAPES = """#pragma once
#include "lib/declarations.hpp"
#include <concepts>
#include <cstdint>
#include <urd/elements/flat.hpp>
namespace lib {
struct UnaryTag {};
struct BinaryTag {};
template<typename T> concept Unary = std::same_as<T, UnaryTag>;
template<typename T> concept Binary = std::same_as<T, BinaryTag>;
template<typename Tag> struct Shape {};
}
namespace urd {
template<lib::Unary Tag> struct data<lib::Shape<Tag>> {
    urd::index<lib::Shape<Tag>> index;
    std::uint32_t operand;
    data() = default;
    explicit data(std::uint32_t operand_) : index(), operand(operand_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"operand", &data::operand>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::Members<&data::operand> {}; }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::operand> {}; }
};
template<lib::Binary Tag> struct data<lib::Shape<Tag>> {
    urd::index<lib::Shape<Tag>> index;
    std::uint32_t left_operand;
    std::uint32_t right_operand;
    data() = default;
    data(std::uint32_t left_operand_, std::uint32_t right_operand_) :
        index(), left_operand(left_operand_), right_operand(right_operand_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"left_operand", &data::left_operand>,
                         urd::field<"right_operand", &data::right_operand>> {}; }
    static constexpr auto identifying_members() noexcept
    { return urd::Members<&data::left_operand, &data::right_operand> {}; }
    static constexpr auto cista_members() noexcept
    { return urd::Members<&data::index, &data::left_operand, &data::right_operand> {}; }
};
template<lib::Unary Tag, typename V> struct view_mixin<lib::Shape<Tag>, V> {
private:
    const V& self() const noexcept { return static_cast<const V&>(*this); }
public:
    auto get_operand() const noexcept { return self().template member<&urd::record_of<V>::operand>(); }
};
template<lib::Binary Tag, typename V> struct view_mixin<lib::Shape<Tag>, V> {
private:
    const V& self() const noexcept { return static_cast<const V&>(*this); }
public:
    auto get_left_operand() const noexcept { return self().template member<&urd::record_of<V>::left_operand>(); }
    auto get_right_operand() const noexcept { return self().template member<&urd::record_of<V>::right_operand>(); }
};
}
"""


def test_records_of_one_tag_are_paired_with_the_mixin_of_their_shape(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    (root / "include/lib/shape_data.hpp").write_text(SHAPES)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    found = check(root, database)
    assert not [each for rule in ("S1", "S2") for each in found[rule] if "shape_data" in each.path]


# One name in two namespaces: each record is paired with the mixin of its own namespace.
NAMESAKES = (
    """#pragma once
#include "lib/declarations.hpp"
#include <cstdint>
#include <urd/elements/flat.hpp>
namespace lib::first { struct Thing {}; }
namespace lib::second { struct Thing {}; }
namespace urd {
"""
    + """template<> struct data<lib::{ns}::Thing> {{
    urd::index<lib::{ns}::Thing> index;
    std::uint32_t {field};
    data() = default;
    explicit data(std::uint32_t {field}_) : index(), {field}({field}_) {{}}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept {{ return urd::Fields<urd::field<"{field}", &data::{field}>> {{}}; }}
    static constexpr auto identifying_members() noexcept {{ return urd::Members<&data::{field}> {{}}; }}
    static constexpr auto cista_members() noexcept {{ return urd::Members<&data::index, &data::{field}> {{}}; }}
}};
template<typename V> struct view_mixin<lib::{ns}::Thing, V> {{
private:
    const V& self() const noexcept {{ return static_cast<const V&>(*this); }}
public:
    auto get_{field}() const noexcept {{ return self().template member<&urd::record_of<V>::{field}>(); }}
}};
""".format(ns="first", field="weight")
    + """template<> struct data<lib::{ns}::Thing> {{
    urd::index<lib::{ns}::Thing> index;
    std::uint32_t {field};
    data() = default;
    explicit data(std::uint32_t {field}_) : index(), {field}({field}_) {{}}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept {{ return urd::Fields<urd::field<"{field}", &data::{field}>> {{}}; }}
    static constexpr auto identifying_members() noexcept {{ return urd::Members<&data::{field}> {{}}; }}
    static constexpr auto cista_members() noexcept {{ return urd::Members<&data::index, &data::{field}> {{}}; }}
}};
template<typename V> struct view_mixin<lib::{ns}::Thing, V> {{
private:
    const V& self() const noexcept {{ return static_cast<const V&>(*this); }}
public:
    auto get_{field}() const noexcept {{ return self().template member<&urd::record_of<V>::{field}>(); }}
}};
""".format(ns="second", field="name")
    + "}\n"
)


def test_records_of_one_name_in_two_namespaces_are_paired_with_their_own_mixins(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    (root / "include/lib/namesake_data.hpp").write_text(NAMESAKES)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    found = check(root, database)
    assert not [each for rule in ("S1", "S2") for each in found[rule] if "namesake_data" in each.path]


def test_a_view_may_derive_more_but_not_read_data(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S2"]
    assert not [each for each in found if "atom_data" in each.path]
    assert any(each.rule == "Term: view_mixin reads data() 1 times, not through member<>" for each in found)


def test_a_trivially_copyable_record_declares_copyable(tmp_path: Path) -> None:
    assert not [each for each in check(*library(tmp_path))["S1"] if "cost_data" in each.path]


def test_records_and_mixins_in_sources_are_checked(tmp_path: Path) -> None:
    found = check(*library(tmp_path))
    assert any(each.path.startswith("tests/unit/local.cpp") and "constructors" in each.rule for each in found["S1"])
    assert any(each.path.startswith("tests/unit/local.cpp") and "reads data()" in each.rule for each in found["S2"])


def test_a_record_bound_by_hand_is_reported(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S3"]
    assert any(each.path.startswith("python/src/pylib/module.cpp") and "bound by hand" in each.rule for each in found)
    assert not any("Atom is not bound" in each.rule for each in found)  # by bind_derived's bind_data call


def test_a_bound_class_held_or_unnamed_is_no_hand_binding(tmp_path: Path) -> None:
    lines = BINDING.splitlines()
    at = [number for number, line in enumerate(lines, 1) if "bind_data<lib::Atom>(0)" in line]
    assert len(at) == 2
    found = {each.path for each in check(*library(tmp_path))["S3"]}
    assert not any(f"python/src/pylib/module.cpp:{line}" in found for line in at)


def test_a_record_bound_by_hand_in_a_template_is_reported(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S3"]
    assert any(each.rule.startswith("*: its data or view is bound by hand") for each in found)
    assert not any("Local is not bound" in each.rule for each in found)  # a test's own record


def test_a_unity_built_binding_source_parses_with_its_unity_source_flags(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S3"]
    assert not any("does not parse" in each.rule for each in found)
    assert any(each.path.startswith("python/src/pylib/module.cpp:") for each in found)


def test_a_binding_source_not_in_the_compile_database_is_reported(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    (root / "python/src/pylib/loose.cpp").write_text(BINDING)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    found = check(root, database)["S3"]
    loose = [each.rule for each in found if each.path == "python/src/pylib/loose.cpp"]
    assert any("not in the compile database" in each for each in loose)


def test_a_binding_source_that_does_not_parse_is_reported(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    broken = BINDING + "void broken() { urd::python::init_from_views<int>(); }\n"
    (root / "python/src/pylib/module.cpp").write_text(broken)
    found = check(root, database)["S3"]
    assert any(each.path == "python/src/pylib/module.cpp" and each.rule.startswith("does not parse:") for each in found)


def test_a_record_bound_by_hand_through_an_alias_in_a_template_is_reported(tmp_path: Path) -> None:
    lines = BINDING.splitlines()
    marks = ("auto aliased_data", "nanobind::class_<V>(0).def", "auto other")
    at = [next(number for number, line in enumerate(lines, 1) if mark in line) for mark in marks]
    hand = "*: its data or view is bound by hand"
    found = {each.path for each in check(*library(tmp_path))["S3"] if each.rule.startswith(hand)}
    assert f"python/src/pylib/module.cpp:{at[0]}" in found  # using V = urd::data<T>
    assert f"python/src/pylib/module.cpp:{at[1]}" in found  # using V = ViewOf<T>, an alias template of urd::index_view
    assert f"python/src/pylib/module.cpp:{at[2]}" not in found  # class_<T>: no record's class


def test_derived_bindings_name_the_member_function_they_bind(tmp_path: Path) -> None:
    derived = sorted(
        each.rule
        for each in check(*library(tmp_path))["S3"]
        if each.path.startswith("python/src/pylib/module.cpp") and "bound by hand" not in each.rule
    )
    assert derived == ["binds a lambda: bind the member function itself", "binds get_arity as 'arity', not 'get_arity'"]


def test_a_record_named_by_an_alias_is_bound_by_the_alias(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S3"]
    assert not any("Object is not bound" in each.rule for each in found)


def test_a_family_is_bound_by_a_member() -> None:
    family = Record("Relation<F>", [], 0, "include/lib/relation_data.hpp", ("F",))
    assert binds(family, "Relation<Schema>")
    assert not binds(family, "Row<Schema>")
    assert binds(Record("Atom", [], 0), "Atom")


@pytest.mark.parametrize(
    ("name", "body", "forwards"),
    [
        ("get_name", "return get_symbol ( ) . get_name ( ) ;", True),
        ("get_state_repository", "return self ( ) . context ( ) ;", True),
        ("get_task", "return * self ( ) . context ( ) . get_task ( ) ;", True),
        ("get_entry_module", "return get_module ( ) ;", True),
        ("get_predicate", "return get_row ( ) . get_relation ( ) ;", False),
        ("get_arity", "return get_terms ( ) . size ( ) ;", False),
        ("get_terms", "return self ( ) . template member < & urd :: record_of < V > :: terms > ( ) ;", False),
    ],
)
def test_forwarding(name: str, body: str, forwards: bool) -> None:
    """A member that only forwards (its name at the chain's end, or one call on the view) is S2's; others are not."""
    words = ["auto", name, "(", ")", "const", "{", *body.split(), "}"]
    assert bool(forwarding(name, words)) == forwards
