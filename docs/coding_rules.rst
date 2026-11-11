Coding rules
============

Every repository checks its code with `peachycheck <https://github.com/drexlerd/peachycheck>`__, locally, in the
agents' hooks and in CI, with the linters its ``peachycheck.yml`` enables. Two rules hold for every linter:

- **Finding-free.** Every finding fails the check; there is no baseline. On a pull request the changed files count, on
  ``main`` every file.
- **Every rule is on, except where a rule is wrong for any code, not just for today's.** Each exception stands in the
  linter's configuration file with its reason. The configuration files of a repository are authoritative; this page
  states what they share.

Python
------

``ruff.toml`` selects every ruff rule (``select = ["ALL"]``) with a line length of 120, and ``ruff format`` formats
the code. The exceptions:

.. list-table::
   :header-rows: 1

   * - Rule
     - Reason
   * - ``COM812``
     - Trailing commas are the formatter's; ruff's documentation lists the rule as conflicting with it.
   * - ``TRY003``
     - Messages say what failed where it is raised; a class per message would only move the text.
   * - ``S603``
     - Fires on every subprocess call, though they pass fixed argument lists and no shell.
   * - ``TC001``, ``TC002``, ``TC003``
     - Imports used only in annotations stay ordinary imports, so every name a module annotates is also there at
       runtime.

Beyond the rule selection:

- Docstrings follow the Google Python Style Guide.
- Imports are absolute; relative imports are banned.
- ``typing.TYPE_CHECKING`` is banned: import at module level instead; the modules have no import cycles to break.
- Tests may use ``assert``, literal values and undocumented test functions, and their folders are not packages
  (``S101``, ``PLR2004``, ``D1``, ``FBT001``, ``C901``, ``PLR0912``, ``PLR0915``, ``INP001``).
- Command-line entry points may print (``T201``).

``pyrightconfig.json`` checks the sources and the tests in ``strict`` mode for Python 3.11, with the reports that
strict mode leaves off or as warnings raised to errors (missing imports and stubs, unknown types, implicit overrides,
unused imports and variables, unnecessary ``type: ignore`` comments, unreachable code, import cycles, deprecated
names). pyright resolves imports in the repository's ``.venv``, so the package is installed there first; for a
library with bindings that install also generates the stubs.

C++
---

``.clang-format`` formats the code: Allman braces, an indent of 4 spaces, 160 columns, pointers and references
aligned left (``T* p``), no bin-packing of arguments or parameters, includes sorted and regrouped.

``.clang-tidy`` turns on every ``bugprone``, ``cppcoreguidelines`` and ``performance`` check, the static analyzer
(``clang-analyzer``) and ``concurrency``. From the other families it takes the checks that find defects rather than
enforce a style: include cycles, redundant expressions, external linkage of file-local functions, discarded results,
C-style casts, declarations whose parameter names differ from the definition, non-inline definitions in headers,
ignored C return values, dead code (unused declarations and parameters, redundant declarations and casts, member
functions that could be const) and the modern forms that rule out a defect class (``override``, ``nullptr``,
``make_unique``, deleted and defaulted members, misleading identifiers and indentation).

The exceptions, in the repositories that need them:

.. list-table::
   :header-rows: 1

   * - Check
     - Reason
   * - ``cppcoreguidelines-pro-bounds-avoid-unchecked-container-access``,
       ``cppcoreguidelines-pro-bounds-constant-array-index``
     - The only fix, ``.at()``, puts a bounds check into hot loops. Debug builds check those bounds instead: they
       define ``_GLIBCXX_ASSERTIONS``, so ``operator[]`` of ``std::vector``, ``std::array`` and ``std::span`` asserts
       its index there, at no cost in Release.
   * - ``bugprone-std-namespace-modification``
     - ``std::ranges::enable_borrowed_range`` must be specialized in ``std``.
   * - ``bugprone-easily-swappable-parameters``
     - A heuristic without a clear fix.
   * - ``cppcoreguidelines-pro-type-reinterpret-cast``
     - Byte storage views its bytes as objects (``reinterpret_cast`` plus ``std::launder``); casting through ``void*``
       instead stays forbidden (``bugprone-casting-through-void``).
   * - ``cppcoreguidelines-avoid-c-arrays``
     - ``std::unique_ptr<T[]>`` with ``make_unique_for_overwrite`` is the uninitialized buffer, which ``std::vector``
       would zero.
   * - ``cppcoreguidelines-pro-type-const-cast``
     - ``std::atomic_ref`` of a const object needs C++26; until then atomic loads of const blocks cast.
   * - ``bugprone-crtp-constructor-accessibility``
     - Private mixin constructors break inheriting constructors (``using Base::Base``) and aggregate initialization
       of derived types.
   * - ``misc-const-correctness``
     - In templates it reports variables as never modified that an overload chosen at instantiation does modify
       (``hash_combine``'s seed, fold-expression counters); following it made ``hash_combine`` recurse forever.
   * - ``google-explicit-constructor``
     - The standard library's own idioms need implicit conversions that it forbids, with no option to allow them:
       proxy references convert to their value (as ``std::vector<bool>::reference`` does, and iterator concepts
       require it), and views of mutable elements convert to views of const ones (as ``std::span`` does).
   * - ``portability-template-virtual-member-function``
     - It warns that other compilers (MSVC) instantiate unused virtual members of class templates; the libraries
       build only with GCC and Clang (Linux and macOS), which instantiate only what is used, so no build can check a
       fix.

Folders with their own ``.clang-tidy`` inherit the repository's and turn off more, each with its reason:

- **Tests**: literal values are the test data, fixed seeds keep runs reproducible, checks of moved-from objects use
  them after the move, validation tests cast invalid enum values, and values that throw in their moves test exception
  safety. Tests read optionals with ``value()``, whose ``bad_optional_access`` fails the test.
- **Benchmarks**: literal values are the benchmark sizes and data, and benchmarks register themselves during static
  initialization, which may throw.
- **Bindings**: nanobind takes ownership of objects returned as ``new T`` with ``rv_policy::take_ownership``; types
  that cannot move are created that way.

Headers and templates also follow the :doc:`template_rules`.

Documentation
-------------

Documentation pages are reStructuredText, built by Sphinx with warnings as errors. peachycheck checks them with doc8
(lines of at most 120 characters) and codespell.
