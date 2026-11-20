# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.rules.schema.records on a small library: a record that follows S1-S5, and one that breaks each."""

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
template<fixed_string Name> struct arg {};
template<fixed_string Name, auto Function, typename... Args> struct function {};
template<typename... Fs> struct Functions {};
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
    static constexpr auto functions() noexcept
    { return urd::Functions<urd::function<"get_arity", &view_mixin::get_arity>> {}; }
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
    urd::index<lib::Loose> index;
    std::string name;
    data() = default;
    data(const data&) = delete;
    static constexpr auto cista_members() noexcept { return urd::Members<&data::name> {}; }
};
}
namespace lib { inline int helper() { return 0; } }
"""
# A value with no children (urd::PlainValue): no index, no record's index among its fields; no view of its own (S3, S4).
PLAIN_DATA = """#pragma once
#include <string_view>
#include <type_traits>
#include <urd/elements/flat.hpp>
namespace lib { struct Span { static constexpr std::string_view name = "Span"; }; }
namespace urd {
template<> struct data<lib::Span> {
    int first = 0;
    int last = 0;
    data() = default;
    data(int first_, int last_) : first(first_), last(last_) {}
    static constexpr bool copyable() noexcept
    {
        static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
        return true;
    }
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"first", &data::first>, urd::field<"last", &data::last>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::first, &data::last> {}; }
};
}
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
# A view that reads the record's stored form: S3 forbids record() in a mixin.
TERM_VIEW = """#pragma once
#include "lib/term_data.hpp"
namespace urd {
template<typename V> struct view_mixin<lib::Term, V> {
private:
    const V& self() const noexcept { return static_cast<const V&>(*this); }
public:
    auto get_objects() const noexcept { return self().record().objects; }
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
    auto get_count() const noexcept { return static_cast<const V&>(*this).record().count; }
};
}
"""
# A binding source: Atom's data and views bound, and what S4 and S5 forbid besides: classes bound by hand, .def on a
# bound class (chained, through a variable, through a helper), a module function over a view.
BINDING = """#include "lib/atom_data.hpp"
#include "lib/object_data.hpp"
#include "lib/key.hpp"
#include "lib/term_data.hpp"
#include "lib/classy_data.hpp"
#include "pylib/flags.hpp"  // found only through the include path of the unity source that compiles this one
namespace nanobind {
struct module_ { template<typename F> module_& def(const char*, F) { return *this; } };
template<typename T> struct class_ {
    explicit class_(int) {}
    ~class_() {}  // not trivial, as nanobind's: a discarded class is a temporary with cleanups
    template<typename F> class_& def(const char*, F) { return *this; }
};
}
namespace urd::python {
// urd's own binders bind by hand by design: no finding in them
template<typename T> void bind_index(int) {}
template<typename T> nanobind::class_<urd::data<T>> bind_data(int) { return nanobind::class_<urd::data<T>>(0); }
template<typename V> nanobind::class_<V> bind_view(int) { return nanobind::class_<V>(0); }
template<typename T> nanobind::class_<T> bind_value(int) { return nanobind::class_<T>(0); }
}
using AtomView = urd::index_view<lib::Atom, int>;
using ObjectView = urd::index_view<lib::Object, int>;
inline nanobind::class_<AtomView> bind_atom_view() { return urd::python::bind_view<AtomView>(0); }
void bind_derived(nanobind::module_& m) {
    urd::python::bind_index<lib::Atom>(0);
    urd::python::bind_index<lib::Object>(0);
    auto held = urd::python::bind_data<lib::Atom>(0);  // a variable holding the bound class: no hand binding
    urd::python::bind_data<lib::Atom>(0);  // the class bind_data returns, unnamed: no hand binding
    urd::python::bind_data<lib::Object>(0);  // a record named by an alias
    urd::python::bind_view<ObjectView>(0);
    auto helped = bind_atom_view();  // a helper's class, held: no hand binding
    helped.def("through_variable", 0);
    bind_atom_view().def("through_helper", 0);
    urd::python::bind_view<AtomView>(0).def("chained", 0);
    m.def("over_view", [](AtomView view) { return 0; });
    m.def("parse", [](int text) { return text; });
    m.def("search", [](AtomView view, int limit) { return limit; });  // an algorithm over a view: m.def
    auto key = urd::python::bind_value<lib::Key>(0);  // no hand binding
    key.def("on_value", 0);
}
// urd::python::bind_data<lib::Loose>(0);  a comment binds nothing
#if 0
void inactive() { urd::python::bind_data<lib::Loose>(0); }
#endif
void bind() { nanobind::class_<urd::data<lib::Atom>> by_hand(0); }
void bind_value_by_hand() { nanobind::class_<lib::Key> value_by_hand(0); }
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
// A helper over its view: it binds what its callers pass
template<typename V> void bind_view_of() { urd::python::bind_view<V>(0); }
void bind_term() {
    urd::python::bind_index<lib::Term>(0);
    urd::python::bind_index<lib::Shuffled>(0);
    urd::python::bind_data<lib::Term>(0);
    bind_view_of<urd::index_view<lib::Term, int>>();
    urd::python::bind_data<lib::Shuffled>(0);
}
// A generic helper over a bare parameter binds no record of its own
template<typename T> void bind_any_view() { urd::python::bind_view<ViewOf<T>>(0); }
"""
# Values (S5): Key follows it; Unbound is not bound; Nameless has no name; Inner, nested, declares fields() without
# auto; Printable has a name and fields() but no identifying_members(): printable, no value.
VALUES = """#pragma once
#include <string_view>
#include <urd/elements/flat.hpp>
namespace lib {
struct Key {
    static constexpr std::string_view name = "Key";
    int first;
    int second;
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"first", &Key::first>, urd::field<"second", &Key::second>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
};
struct Unbound {
    static constexpr std::string_view name = "Unbound";
    int count;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &Unbound::count>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
};
struct Nameless {
    int count;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &Nameless::count>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
};
struct RowKey {
    static constexpr std::string_view name = "RowKey";
    int relation;
    int row;
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"relation", &RowKey::relation>, urd::field<"row", &RowKey::row>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
};
struct Printable {
    static constexpr std::string_view name = "Printable";
    int m_count;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &Printable::m_count>> {}; }
};
struct Outer {
    struct Inner {
        static constexpr std::string_view name = "Inner";
        int count;
        static constexpr urd::Fields<urd::field<"count", &Inner::count>> fields() noexcept { return {}; }
        static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    };
};
}
// A key reads as what it names: a resolution of its own.
namespace urd { template<typename M> struct resolution; }
template<> struct urd::resolution<lib::RowKey> {};
"""
# A record of S1's form, and a mixin that breaks S3 in every way it can: a base, a public self(), members that are no
# functions, record() read through a variable, a deduced member template and an overload not listed, a member listed
# only in a comment, a forwarder, a member after functions(). Its held form's mixin reads record() and lists nothing.
# Free functions listed: one forwards, one reads record().
PROBE = """#pragma once
#include "lib/declarations.hpp"
#include <urd/elements/flat.hpp>
namespace lib { struct Probe {}; template<typename V> struct Reads {}; }
namespace lib { template<typename T> struct Wrap {}; template<typename T> T make(); }
namespace urd {
template<> struct data<lib::Probe> {
    urd::index<lib::Probe> index;
    int count = 0;
    data() = default;
    explicit data(int count_) : index(), count(count_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &data::count>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::count> {}; }
};
}
namespace lib {
template<typename V> int counted(const V& probe) { return probe.get_count(); }
template<typename V> int raw(const V& probe) { return probe.record().count; }
template<typename V> int scaled(const V& probe, int factor) { return probe.get_count() * factor; }
}
namespace urd {
template<typename V> struct view_mixin<lib::Probe, V> : lib::Reads<V> {
    const V& self() const noexcept { return static_cast<const V&>(*this); }
    auto get_count() const noexcept { return self().template member<&urd::record_of<V>::count>(); }
    using alias = int;
    int cache = 0;
    int peek() const { const auto& view = static_cast<const V&>(*this); return view.record().count; }
    template<typename T> int explicit_template() const { return 0; }
    int deduced(auto value) const { return 0; }
    int at(int position) const { return position; }
    int at(double position) const { return 0; }
    template<typename T> int pick() const { return 0; }
    template<typename T> int pick(lib::Wrap<T> wrapped) const { return 1; }
    auto twice() const noexcept { return 0; }
    auto twice(int times) const noexcept -> decltype(lib::make<int>()) { return times; }
    int hidden() const { return 1; }
    auto label() const { return (this->get_count()); }
    static constexpr auto functions() noexcept
    {
        /* &view_mixin::hidden */
        return urd::Functions<urd::function<"x", &view_mixin::peek>,
                              urd::function<"x", static_cast<int (view_mixin::*)(int) const>(&view_mixin::at),
                                            urd::arg<"index">>,
                              urd::function<"pick", static_cast<int (view_mixin::*)(lib::Wrap<int>) const>(
                                                        &view_mixin::template pick<int>),
                                            urd::arg<"wrapped">>,
                              urd::function<"twice",
                                            static_cast<decltype(lib::make<const view_mixin&>().twice())
                                                            (view_mixin::*)() const noexcept>(&view_mixin::twice)>,
                              urd::function<"twice",
                                            static_cast<decltype(lib::make<const view_mixin&>().twice(1))
                                                            (view_mixin::*)(int) const noexcept>(&view_mixin::twice),
                                            urd::arg<"times">>,
                              urd::function<"x", &view_mixin::label>,
                              urd::function<"x", &lib::counted<V>>,
                              urd::function<"x", &lib::raw<V>>,
                              urd::function<"x", &lib::scaled<V>>> {};
    }
    int after() const { return 0; }
};
template<typename V> struct view_mixin<urd::data<lib::Probe>, V> : view_mixin<lib::Probe, V> {
private:
    const V& self() const noexcept { return static_cast<const V&>(*this); }
public:
    int stored() const { return self().record().count; }
};
}
"""
# S1: a record written as a class with a member S1 forbids, and one whose blocks are out of order.
CLASSY = """#pragma once
#include "lib/declarations.hpp"
#include <urd/elements/flat.hpp>
namespace lib { struct Classy {}; struct Shuffled {}; }
namespace urd {
template<> class data<lib::Classy> {
public:
    urd::index<lib::Classy> index;
    int count = 0;
    data() = default;
    explicit data(int count_) : index(), count(count_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &data::count>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::count> {}; }
    int extra() const { return 1; }
};
template<> struct data<lib::Shuffled> {
    static constexpr auto fields() noexcept { return urd::Fields<urd::field<"count", &data::count>> {}; }
    urd::index<lib::Shuffled> index;
    int count = 0;
    data() = default;
    explicit data(int count_) : index(), count(count_) {}
    data(const data& other) = delete;
    data& operator=(const data& other) = delete;
    data(data&& other) = default;
    data& operator=(data&& other) = default;
    ~data() = default;
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::count> {}; }
};
}
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
        "include/lib/span_data.hpp": PLAIN_DATA,
        "include/lib/cost_data.hpp": COST_DATA,
        "include/lib/object_data.hpp": ALIAS_DATA,
        "include/lib/term_data.hpp": TERM_DATA,
        "include/lib/term_view.hpp": TERM_VIEW,
        "include/lib/key.hpp": VALUES,
        "include/lib/probe_view.hpp": PROBE,
        "include/lib/classy_data.hpp": CLASSY,
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
    assert loose["S3"] == {"Loose: has no urd::view_mixin<Loose, V>"}
    assert loose["S4"] == {
        "Loose is not bound with urd::python::bind_data",
        "Loose holds its index, not bound with urd::python::bind_index",
    }


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
    assert not [each for rule in ("S1", "S3") for each in found[rule] if "shape_data" in each.path]


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
    assert not [each for rule in ("S1", "S3") for each in found[rule] if "namesake_data" in each.path]


def test_a_view_may_derive_more_but_not_read_data(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S3"]
    assert not [each for each in found if "atom_data" in each.path]
    assert any(each.rule == "lib::Term: reads record() of its view 1 times, not through member<>" for each in found)


def probe_findings(tmp_path: Path) -> set[str]:
    """What S3 reports of the probe mixins and the free functions they list."""
    return {each.rule for each in check(*library(tmp_path))["S3"] if "probe_view" in each.path}


def test_a_mixin_declares_member_functions_alone_without_a_base(tmp_path: Path) -> None:
    found = probe_findings(tmp_path)
    assert any(each.startswith("lib::Probe: has the base lib::Reads<V>") for each in found)
    assert any("declares type_alias_decl alias" in each for each in found)
    assert any("declares field_decl cache" in each for each in found)
    assert "lib::Probe: has self() public: self() alone is private" in found
    assert "lib::Probe: declares after() after functions(), which is its last member" in found


def test_a_mixin_reads_data_in_no_way(tmp_path: Path) -> None:
    found = probe_findings(tmp_path)
    assert "lib::Probe: reads record() of its view 1 times, not through member<>" in found  # through a variable
    assert "lib::Probe: reads record() of its view 1 times, not through member<>" in found  # the held form's mixin
    assert "raw() reads record() of its view 1 times, not through member<>" in found  # a listed free function
    assert "scaled() takes 2 parameters: a function of a view takes the view alone" in found


def test_listed_parameters_carry_their_own_names(tmp_path: Path) -> None:
    found = probe_findings(tmp_path)
    assert "lib::Probe: functions() lists x with the parameter names ['index'], not its own ['position']" in found


def test_a_mixin_lists_every_member_but_explicit_templates(tmp_path: Path) -> None:
    found = probe_findings(tmp_path)
    unlisted = next(each for each in found if "are not listed" in each and "stored" not in each)
    # A deduced template, the overload a static_cast does not pick, a member named only in a comment, and after()
    assert (
        unlisted == "lib::Probe: view_mixin members ['deduced', 'at', 'hidden', 'after'] are not listed in functions()"
    )
    held = [each for each in found if "['stored']" in each]
    assert held == ["lib::Probe: view_mixin members ['stored'] are not listed in functions()"]


def test_forwarders_are_found_in_any_spelling(tmp_path: Path) -> None:
    found = probe_findings(tmp_path)
    assert "label() is an alias of get_count() of the view: its callers call that" in {
        each.removeprefix("lib::Probe: ") for each in found
    }
    assert "counted() is an alias of get_count() of the view: its callers call that" in found


def test_a_record_written_as_a_class_is_a_record(tmp_path: Path) -> None:
    found = {each.rule for each in check(*library(tmp_path))["S1"] if "classy_data" in each.path}
    assert any(each.startswith("data<Classy> has the functions") for each in found)


def test_a_record_has_its_blocks_in_order(tmp_path: Path) -> None:
    found = {each.rule for each in check(*library(tmp_path))["S1"] if "classy_data" in each.path}
    assert "data<Shuffled> declares the index (index) after fields()" in found


def test_a_value_is_a_record(tmp_path: Path) -> None:
    rules = {each.rule for each in check(*library(tmp_path))["S5"]}
    record = (
        "is no urd::data<T>: a type that declares fields() and identifying_members() is a record, or a key"
        " urd::resolution reads"
    )
    assert f"value lib::Key {record}" in rules
    assert f"value lib::Outer::Inner {record}" in rules  # nested, fields() without auto
    assert not any("Printable" in rule for rule in rules)  # printable (name, fields()), no value
    assert not any("RowKey" in rule for rule in rules)  # a key: urd::resolution reads it as what it names
    assert not any("bind_value" in rule for rule in rules)


def test_a_trivially_copyable_record_declares_copyable(tmp_path: Path) -> None:
    assert not [each for each in check(*library(tmp_path))["S1"] if "cost_data" in each.path]


def test_records_and_mixins_in_sources_are_checked(tmp_path: Path) -> None:
    found = check(*library(tmp_path))
    assert any(each.path.startswith("tests/unit/local.cpp") and "constructors" in each.rule for each in found["S1"])
    assert any(each.path.startswith("tests/unit/local.cpp") and "reads record()" in each.rule for each in found["S3"])


def test_a_record_bound_by_hand_is_reported(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S4"]
    assert any(each.path.startswith("python/src/pylib/module.cpp") and "bound by hand" in each.rule for each in found)
    assert not any("Atom is not bound" in each.rule for each in found)  # by bind_derived's bind_data call


def test_a_bound_class_held_or_unnamed_is_no_hand_binding(tmp_path: Path) -> None:
    lines = BINDING.splitlines()
    at = [number for number, line in enumerate(lines, 1) if "bind_data<lib::Atom>(0)" in line]
    assert len(at) == 2
    found = {each.path for each in check(*library(tmp_path))["S4"]}
    assert not any(f"python/src/pylib/module.cpp:{line}" in found for line in at)


def test_a_record_bound_by_hand_in_a_template_is_reported(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S4"]
    assert any(each.rule.startswith("*: its data, builder or view is bound by hand") for each in found)
    assert not any("Local is not bound" in each.rule for each in found)  # a test's own record


def test_a_unity_built_binding_source_parses_with_its_unity_source_flags(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S4"]
    assert not any("does not parse" in each.rule for each in found)
    assert any(each.path.startswith("python/src/pylib/module.cpp:") for each in found)


def test_a_binding_source_not_in_the_compile_database_is_reported(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    (root / "python/src/pylib/loose.cpp").write_text(BINDING)
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    found = check(root, database)["S4"]
    loose = [each.rule for each in found if each.path == "python/src/pylib/loose.cpp"]
    assert any("not in the compile database" in each for each in loose)


def test_a_binding_source_that_does_not_parse_is_reported(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    broken = BINDING + "void broken() { urd::python::init_from_views<int>(); }\n"
    (root / "python/src/pylib/module.cpp").write_text(broken)
    found = check(root, database)["S4"]
    assert any(each.path == "python/src/pylib/module.cpp" and each.rule.startswith("does not parse:") for each in found)


def test_a_record_bound_by_hand_through_an_alias_in_a_template_is_reported(tmp_path: Path) -> None:
    lines = BINDING.splitlines()
    marks = ("auto aliased_data", "nanobind::class_<V>(0).def", "auto other")
    at = [next(number for number, line in enumerate(lines, 1) if mark in line) for mark in marks]
    hand = "*: its data, builder or view is bound by hand"
    found = {each.path for each in check(*library(tmp_path))["S4"] if each.rule.startswith(hand)}
    assert f"python/src/pylib/module.cpp:{at[0]}" in found  # using V = urd::data<T>
    assert f"python/src/pylib/module.cpp:{at[1]}" in found  # using V = ViewOf<T>, an alias template of urd::index_view
    assert f"python/src/pylib/module.cpp:{at[2]}" not in found  # class_<T>: no record's class


def test_a_bound_class_gets_no_def_however_it_is_reached(tmp_path: Path) -> None:
    lines = BINDING.splitlines()
    marks = (
        "helped.def",
        "bind_atom_view().def",
        '.def("chained"',
        'm.def("over_view"',
        'm.def("parse"',
        'm.def("search"',
    )
    at = [next(number for number, line in enumerate(lines, 1) if mark in line) for mark in marks]
    found = {each.path: each.rule for each in check(*library(tmp_path))["S4"]}
    for line in at[:3]:
        assert (
            found[f"python/src/pylib/module.cpp:{line}"]
            == "def on a record's class: list the function in its functions()"
        )
    assert found[f"python/src/pylib/module.cpp:{at[3]}"].startswith("binds a function over a view in a module")
    assert f"python/src/pylib/module.cpp:{at[4]}" not in found
    assert f"python/src/pylib/module.cpp:{at[5]}" not in found


def test_comments_and_inactive_code_bind_nothing(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S4"]
    assert any(each.rule == "Loose is not bound with urd::python::bind_data" for each in found)


def test_urd_own_binders_are_no_hand_binding(tmp_path: Path) -> None:
    lines = BINDING.splitlines()
    at = {number for number, line in enumerate(lines, 1) if "nanobind::class_<urd::data<T>>(0); }" in line}
    found = {each.path for each in check(*library(tmp_path))["S4"]}
    assert not any(f"python/src/pylib/module.cpp:{line}" in found for line in at)


def test_a_record_needs_a_bound_view(tmp_path: Path) -> None:
    found = {each.rule for each in check(*library(tmp_path))["S4"]}
    assert "Term has no view bound with urd::python::bind_view" not in found  # through a helper over its view
    # bind_any_view<T> binds no Shuffled: a bare parameter names no tag
    assert "Shuffled has no view bound with urd::python::bind_view" in found
    assert "Cost has no view bound with urd::python::bind_view" not in found  # Cost is not bound at all
    assert "Cost is not bound with urd::python::bind_data" in found
    assert "Cost holds its index, not bound with urd::python::bind_index" in found
    assert not any(each.startswith(("Atom ", "Object ")) for each in found)


def test_a_record_named_by_an_alias_is_bound_by_the_alias(tmp_path: Path) -> None:
    found = check(*library(tmp_path))["S4"]
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
        ("size", "return std :: ranges :: size ( self ( ) . get_values ( ) ) ;", True),
        ("empty", "return std :: empty ( get_rows ( ) ) ;", True),
        ("size", "return ranges :: size ( get_rows ( ) ) ;", True),
        ("arity", "return std :: ranges :: size ( self ( ) . columns ( ) ) ;", False),
        ("get_terms", "return self ( ) . template member < & urd :: record_of < V > :: terms > ( ) ;", False),
    ],
)
def test_forwarding(name: str, body: str, forwards: bool) -> None:
    """A member that only forwards (its name at the chain's end, or one call on the view) is S3's; others are not."""
    words = ["auto", name, "(", ")", "const", "{", *body.split(), "}"]
    assert bool(forwarding(name, words)) == forwards


BUILDER_PRELUDE = """#pragma once
#include "lib/atom_data.hpp"
namespace urd {
template<typename T, typename C> struct builder;
template<typename M, typename C> using built_t = M;
"""


def with_builder(root: Path, body: str) -> None:
    """Adds the builder of the fixture's Atom record, `body` its members, to the library at `root`."""
    path = root / "include/lib/atom_builder.hpp"
    path.write_text(f"{BUILDER_PRELUDE}template<typename C> struct builder<lib::Atom, C> {{\n{body}\n}};\n}}\n")
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(root), "add", "."], check=True)


def test_a_builder_that_follows_s2_has_no_findings(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    with_builder(
        root,
        """    urd::index<lib::Atom> index;
    urd::built_t<urd::index<lib::Predicate>, C> predicate;
    urd::built_t<urd::flat_vector<std::uint32_t>, C> objects;
    void clear() {}
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"predicate", &builder::predicate>, urd::field<"objects", &builder::objects>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
    template<typename V> void add(V value) {}
    static constexpr auto functions() noexcept
    {
        return urd::Functions<urd::function<"clear", &builder::clear>,
                              urd::function<"add", &builder::template add<int>>> {};
    }
private:
    bool empty() const { return true; }
    static int helper() { return 0; }""",
    )
    assert not [each for each in check(root, database)["S2"] if "atom_builder" in each.path]


def test_a_builder_that_breaks_s2(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    with_builder(
        root,
        """    using Objects = urd::flat_vector<std::uint32_t>;
    urd::index<lib::Atom> index;
    urd::built_t<urd::index<lib::Term>, C> predicate;
    urd::flat_vector<std::uint32_t> objects;
    bool empty() const { return true; }
    static int helper() { return 0; }
    void reset() {}
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"predicate", &builder::predicate>, urd::field<"objects", &builder::objects>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }""",
    )
    found = {each.rule for each in check(root, database)["S2"] if "atom_builder" in each.path}
    builder = "builder<lib::Atom>"
    assert f"{builder} declares type_alias_decl Objects" in found
    assert any(each.startswith(f"{builder} has the field objects of type urd::flat_vector<") for each in found)
    assert f"{builder} declares the const function empty: a read is its view's (its mixin's)" in found
    assert f"{builder} declares the static function helper" in found
    assert f"{builder} does not list its mutator reset in functions(): Python offers what it lists" in found
    assert (
        f"{builder} builds predicate from urd::index<lib::Term>, not its record's urd::index<lib::Predicate>" in found
    )


def test_a_builder_not_bound_with_bind_builder_is_reported(tmp_path: Path) -> None:
    root, database = library(tmp_path)
    with_builder(
        root,
        """    urd::index<lib::Atom> index;
    urd::built_t<urd::index<lib::Predicate>, C> predicate;
    urd::built_t<urd::flat_vector<std::uint32_t>, C> objects;
    static constexpr auto fields() noexcept
    { return urd::Fields<urd::field<"predicate", &builder::predicate>, urd::field<"objects", &builder::objects>> {}; }
    static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }""",
    )
    found = [each.rule for each in check(root, database)["S4"] if "atom_builder" in each.path]
    assert any(each.endswith("is not bound with urd::python::bind_builder") for each in found), found


def test_a_value_with_no_children_has_no_view_of_its_own(tmp_path: Path) -> None:
    found = check(*library(tmp_path))
    span = {each.rule for rule in ("S3", "S4") for each in found[rule] if "span_data" in each.path}
    assert not any("view" in each for each in span), span
