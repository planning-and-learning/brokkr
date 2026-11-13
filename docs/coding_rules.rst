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
names). pyright resolves imports in the repository's ``.venv``, so the package is installed there first.

C++ core
--------

The library, its tests and its benchmarks; the bindings add the rules under `nanobind`_.

- **Data structures.** `urd <https://planning-and-learning.github.io/urd/>`__ provides the central data structures,
  chosen by the properties a request states (what the data is and how it is used). Reuse the data structures from
  there as much as possible.
- **Derived operations.** A generic interface has a small set of primitives, which every implementation provides, and
  derived operations with a default written from the primitives. An implementation overrides a derived operation only
  where it is faster by a complexity class or by word-parallelism, and the default is the reference its tests compare
  against. A derived operation is added only when an algorithm needs it and some implementation overrides it that
  way. Code that depends on the fast version states the cost it requires, so that it does not compile against the
  default.
- **No silent fallbacks.** A fallback is code that detects that something it needs does not hold (a capability, a
  successful result, a value) and proceeds without reporting it: it discards what failed or manufactures a value in its
  place. What fails, fails loudly: a compile error where a type lacks what it needs, an exception where an operation
  fails, a signal in the result type (``std::optional``, a ``bool``, an iterator to the end) where absence is part of
  the contract. Three shapes are always fallbacks, since their failure path has no code of its own, and
  ``python -m pybrokkr.fallbacks --compile-commands build/compile_commands.json`` reports them:

  - ``if constexpr (requires ...) S`` without ``else``, the ``requires`` not negated and ``S`` not leaving: where the
    type lacks it, nothing happens;
  - a ``catch`` with an empty handler: where the operation fails, execution goes on;
  - ``value_or(v)``: where the value is missing, ``v`` takes its place.

  An *alternative* is no fallback: it meets the same contract another way (a derived operation's default, a dispatch
  on the representation). Write it as an overload constrained by a named concept, or with an ``else`` of its own,
  never as a bare skip. Dispatch on what a type offers only through named concepts (``urd::bidirectional_graph``), not
  inline ``requires`` expressions, and assert the concept on every type meant to model it, so that a renamed member is
  a compile error rather than a missing feature. Say *empty*, not *absent*: where there is nothing (a graph without
  data, a storage without a parameter), use a type with one value (``std::monostate``; regular void, P0146) rather
  than ``void``, so that generic code never asks whether there is something. A value of such a type may be left out,
  since nothing is lost.

  The terms come from the literature on error hiding: J. Shore, `Fail Fast
  <https://martinfowler.com/ieeeSoftware/failFast.pdf>`__ (IEEE Software, 2004); M. Rinard et al., `Failure-Oblivious
  Computing <https://www.usenix.org/legacy/events/osdi04/tech/full_papers/rinard/rinard_html/paper.html>`__ (OSDI
  2004), which discards and manufactures on purpose; D. Yuan et al., `Simple Testing Can Prevent Most Critical
  Failures <https://www.usenix.org/conference/osdi14/technical-sessions/presentation/yuan>`__ (OSDI 2014), on empty
  and log-only handlers.

``.clang-format`` formats all C++ code: Allman braces, an indent of 4 spaces, 160 columns, pointers and references
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

Headers and templates also follow the :doc:`template_rules`.

nanobind
--------

The Python bindings (``python/src/``) are C++ and follow the core rules, with what nanobind requires:

- **Ownership.** ``python/src/.clang-tidy`` turns off ``cppcoreguidelines-owning-memory``: nanobind takes ownership
  of objects returned as ``new T`` with ``rv_policy::take_ownership``; types that cannot move are created that way.
- **The module file.** ``python/src/module.cpp`` holds nothing but nanobind's module macro and is excluded from
  clang-tidy (``CPP_CLANG_TIDY_FILTER_REGEX_EXCLUDE`` in ``peachycheck.yml``): the macro's global and its C variadic
  call are nanobind's.
- **Bindings only.** Binding code must not contain boilerplate: it contains class and function bindings and nothing
  else.
- **Handwritten files.** The package's root ``__init__.py`` and its stub, the root ``__init__.pyi``, are written by
  hand and must follow the same structure in every repository: the imports of the provider packages, the re-exported
  subpackages, ``__version__`` and the paths of the native build (``native_prefix()``, ``cmake_prefix()``,
  ``cmake_dir()``, ...). No other ``.pyi`` file may be written by hand.
- **Stubs.** Installing the package generates every other ``.pyi`` stub from the extension, and the package ships
  them with ``py.typed``. pyright checks the Python code against them, so reinstall after a change to the C++ code or
  the bindings; otherwise it reports the bindings as unresolved or untyped.
- **Import order.** A package's ``__init__.py`` imports the packages that provide its native libraries (such as
  ``pyyggdrasil``) before its own extension, so the imports that follow are not at the top of the file (``E402``).

Documentation
-------------

Documentation pages are reStructuredText, built by Sphinx with warnings as errors. peachycheck checks them with doc8
(lines of at most 120 characters) and codespell.
