# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.rules.template.type_lists on a small library: named type lists pass, a specialization over one is found."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("clang.cindex")
if shutil.which("clang++") is None:
    pytest.skip("needs clang++ for clang's own headers", allow_module_level=True)

from pybrokkr.rules.template import type_lists
from pybrokkr.rules.template.type_lists import check

# Just enough of mp11 and of an upstream library (its own list, its storage, an alias of its own).
UPSTREAM = """#pragma once
namespace boost::mp11 { template<typename... Ts> struct mp_list {}; }
namespace up {
template<typename... Ts> struct Symbols { using List = Symbols; };
template<typename C, typename L> class Storage;
template<typename C, typename... Ts> class Storage<C, boost::mp11::mp_list<Ts...>> {
public:
    using Base = Storage;
    Storage();
};
template<typename C, typename... Ts> Storage<C, boost::mp11::mp_list<Ts...>>::Storage() {}
template<typename S> class Repository {};
template<typename T, typename C> struct view { const C* context; };
struct Atom {};
using UpRepository = Repository<Symbols<Atom>>;
}
"""
NAMED = """#pragma once
#include "up/up.hpp"
namespace lib {
struct Atom {};
struct Term {};
// A list named by a class deriving from it, and a storage over a named class.
struct Symbols : up::Symbols<Atom, Term> {};
using Repository = up::Repository<Symbols>;
class Context final {};
struct Types : boost::mp11::mp_list<Atom, Term> {};
using Builder = up::Storage<Context, Types>;
// A class that derives from the specialization, and its alias of that base.
class Store final : public up::Storage<Store, boost::mp11::mp_list<Atom>> {
    using Base = up::Storage<Store, boost::mp11::mp_list<Atom>>;
};
// Another library's alias: its finding, not this one's.
void read(up::view<Atom, up::UpRepository> view);
// A list itself is no specialization over one.
using Kinds = boost::mp11::mp_list<Atom, Term>;
// A template that forms its parts from the class it is given, not from a list of its parameters.
template<typename O, int P> struct Part {};
template<typename Derived, typename... Ts> struct Layer {
    using Own = Part<Derived, 0>;
};
// A partial specialization's members name the specialization itself.
template<typename C, typename L> struct Pool;
template<typename C, typename... Ts> struct Pool<C, boost::mp11::mp_list<Ts...>> {
    using Self = Pool<C, boost::mp11::mp_list<Ts...>>;
    Pool* self();
    Pool(const Pool& other) = delete;
    struct Impl { explicit Impl(const Impl* parent); };
};
}
"""
UNNAMED = """#pragma once
#include "up/up.hpp"
namespace lib {
using Direct = up::Repository<up::Symbols<struct Atom>>;
void use(const Direct& repository);
void first(const up::Repository<up::Symbols<Atom>>* repository);
void spelled(up::view<Atom, up::Storage<int, boost::mp11::mp_list<Atom>>> view);
// A template that forms a specialization over a list of its parameters: in every instantiation's names.
template<typename O, typename Keys> struct Held {};
template<typename Derived, typename... Ts> struct Context {
    using Part = Held<Derived, boost::mp11::mp_list<Ts...>>;
};
}
"""


def library(root: Path, source: str) -> tuple[Path, Path]:
    """A git repository at `root` whose source includes `source`, over the upstream library; its compile database."""
    files = {"include/lib/named.hpp": NAMED, "include/lib/unnamed.hpp": UNNAMED, "src/lib.cpp": source}
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "-q", str(root)], check=True)
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    subprocess.run([git, "-C", str(root), "add", "."], check=True)
    upstream = root.parent / f"{root.name}-up" / "include"
    (upstream / "up").mkdir(parents=True)
    (upstream / "up/up.hpp").write_text(UPSTREAM)
    database = root / "compile_commands.json"
    flags = f"clang++ -std=c++20 -I{root / 'include'} -isystem {upstream}"
    database.write_text(
        json.dumps([{"directory": str(root), "file": "src/lib.cpp", "command": f"{flags} -c src/lib.cpp"}])
    )
    return root, database


def test_named_lists_have_no_findings(tmp_path: Path) -> None:
    assert check(*library(tmp_path / "lib", '#include "lib/named.hpp"\n')) == []


def test_a_specialization_over_a_list_is_found_once_where_it_is_defined_or_first_named(tmp_path: Path) -> None:
    found = check(*library(tmp_path / "lib", '#include "lib/unnamed.hpp"\n'))
    assert [(each.path, each.rule) for each in found] == [
        ("include/lib/unnamed.hpp:4", "defines up::Repository<...> over a type list: derive a class"),
        ("include/lib/unnamed.hpp:7", "names up::Storage<...> over a type list: derive a class"),
        ("include/lib/unnamed.hpp:11", "defines lib::Held<...> over a type list: derive a class"),
    ]


def test_a_source_that_does_not_parse_is_a_finding(tmp_path: Path) -> None:
    found = check(*library(tmp_path / "lib", "int broken(\n"))
    assert [each.path for each in found] == ["src/lib.cpp"]
    assert found[0].rule.startswith("does not parse")


def test_a_source_compiled_through_a_generated_source_is_read_through_it(tmp_path: Path) -> None:
    # The tracked source needs what its generated source includes first (a container's header before its tests), and is
    # compiled only through it: parsed alone it would not parse.
    root, database = library(tmp_path / "lib", '#include "lib/named.hpp"\n')
    (root / "src/needs.cpp").write_text("lib::Atom needed();\nusing Direct = up::Repository<up::Symbols<lib::Atom>>;\n")
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "-C", str(root), "add", "src/needs.cpp"], check=True)
    generated = root / "build/generated.cpp"
    generated.parent.mkdir()
    generated.write_text(f'#include "lib/named.hpp"\n#include "{root / "src/needs.cpp"}"\n')
    entries = json.loads(database.read_text())
    flags = entries[0]["command"].rsplit(" -c ", 1)[0]
    database.write_text(
        json.dumps([{"directory": str(root), "file": str(generated), "command": f"{flags} -c {generated}"}])
    )
    found = check(root, database)
    assert [(each.path, each.rule) for each in found] == [
        ("src/needs.cpp:2", "defines up::Repository<...> over a type list: derive a class"),
    ]


def test_a_source_libclang_crashes_on_is_not_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # A crash fails the parse without a diagnostic (the binding's TranslationUnitLoadError): clang's fault, not the
    # source's.
    def crashed(*_: object) -> tuple[None, str]:
        return None, type_lists.LOAD_FAILED

    monkeypatch.setattr(type_lists, "parse", crashed)
    assert check(*library(tmp_path / "lib", '#include "lib/unnamed.hpp"\n')) == []
    assert "src/lib.cpp: T20: not checked, libclang crashed on it" in capfd.readouterr().err
