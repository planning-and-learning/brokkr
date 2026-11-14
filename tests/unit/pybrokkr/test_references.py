# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""pybrokkr.references: what a source file includes or imports, read from its text."""

from pathlib import Path

from pybrokkr.references import imports_of, included_paths, includes_of, is_included


def test_includes_are_read_as_written(tmp_path: Path) -> None:
    source = tmp_path / "a.cpp"
    source.write_text('#include <lib/a.hpp>\n  #  include "detail/b.hpp"\n// #include "no.hpp"\nint x;\n')
    assert includes_of(source) == {"lib/a.hpp", "detail/b.hpp"}
    assert includes_of(tmp_path / "missing.cpp") == set()


def test_imports_name_modules_and_what_is_imported_from_them(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_text("import os.path\nfrom pkg.core import store\nfrom . import sibling\n")
    assert imports_of(source) == {"os.path", "pkg.core", "pkg.core.store"}
    source.write_text("def broken(:\n")
    assert imports_of(source) == set()


def test_an_include_is_resolved_against_its_file(tmp_path: Path) -> None:
    (tmp_path / "include/lib/core").mkdir(parents=True)
    (tmp_path / "include/lib/core/pool.hpp").write_text('#include "detail/impl.hpp"\n#include "../other.hpp"\n')
    targets = included_paths(tmp_path, ["include/lib/core/pool.hpp", "README.md"])
    assert "include/lib/core/detail/impl.hpp" in targets
    assert "include/lib/other.hpp" in targets
    assert is_included("include/lib/core/detail/impl.hpp", targets)
    assert not is_included("include/lib/core/pool.hpp", targets)
