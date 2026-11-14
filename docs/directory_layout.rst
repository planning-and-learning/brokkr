Directory layout
================

Every library of the chain (urd, yggdrasil, loki, tyr, vefr, runir) has the same layout, so that a reader, a build
script and a check find the same thing in the same place in each. ``<lib>`` is the library's name (``tyr``), ``py<lib>``
its Python package (``pytyr``; loki's is ``pypddl``).

Everything a library may have, each entry described in the sections below. A ``<component>/`` directory may hold
further ``<component>/`` directories, to any depth; ``...`` stands for the same contents again.

.. code-block:: text

   <lib>/
   ├── pyproject.toml              version, Python package, build backend, upstream pins, tool settings
   ├── CMakeLists.txt              the C++ build
   ├── Config.cmake.in             the CMake package it installs
   ├── README.md
   ├── AGENTS.md
   ├── LICENSE
   ├── Apptainer                   container definition
   ├── peachycheck.yml             linter settings
   ├── ruff.toml
   ├── pyrightconfig.json
   ├── include/
   │   └── <lib>/                  public headers
   │       ├── <name>.hpp
   │       └── <component>/        components nest to any depth
   │           ├── declarations.hpp
   │           ├── <name>.hpp
   │           ├── <name>_decl.hpp
   │           ├── <name>_concepts.hpp
   │           ├── detail/
   │           │   └── <name>_impl.hpp
   │           └── <component>/
   │               └── ...
   ├── src/                        library sources, mirroring include/<lib>/
   │   ├── <name>.cpp
   │   └── <component>/            components nest to any depth
   │       ├── <name>.cpp
   │       ├── <name>.hpp          used by the sources only
   │       └── <component>/
   │           └── ...
   ├── exe/                        executables
   │   └── <program>/
   ├── examples/                   C++ examples, built by the build
   ├── python/
   │   ├── py<lib>_build_backend.py
   │   ├── pyproject.toml          only with native/: the native dependencies' package
   │   ├── native/                 only in urd: the native dependencies, built as their own wheel
   │   │   └── <dependency>/       CMakeLists.txt, patches, licenses/, package/
   │   ├── src/
   │   │   ├── module.cpp
   │   │   └── py<lib>/            bindings and Python files, mirroring include/<lib>/
   │   │       ├── __init__.py     the package: what it imports from the module
   │   │       ├── __init__.pyi    the root's stubs, written by hand: the only tracked stub (the
   │   │       │                   module's are generated at install, brokkr_install_python_stubs)
   │   │       ├── py.typed        the package is typed (PEP 561)
   │   │       ├── <name>.py
   │   │       └── <component>/    components nest to any depth
   │   │           ├── __init__.py
   │   │           ├── <name>.cpp  bindings of the component
   │   │           ├── <name>.hpp
   │   │           └── <component>/
   │   │               └── ...
   │   ├── examples/               Python examples
   │   └── tests/                  pytest
   │       ├── <component>/
   │       └── downstream/         a module built against the installed package
   ├── tests/                      C++ tests
   │   ├── rules/                  checks of a rule over the source tree
   │   ├── laws/                   suites run for every registered subject
   │   ├── tables/                 generated output against a checked-in file
   │   ├── cost/                   compile time and memory under limits
   │   ├── unit/                   one component, mirroring include/<lib>/ and src/
   │   │   └── <component>/        components nest to any depth
   │   │       ├── <name>.cpp
   │   │       └── <component>/
   │   │           └── ...
   │   ├── integration/            a consumer of the installed package
   │   │   └── python/             a nanobind test module and the Python script that drives it
   │   └── support/                shared headers and fixtures
   │       ├── data/               test inputs and expected outputs (PDDL, JSON, the library's own formats)
   │       │   └── <component>/
   │       └── generators/         the scripts that write expected outputs, mirroring data/
   │           └── <component>/
   │               └── generate_<name>.py
   ├── docs/                       Sphinx documentation
   │   ├── <TABLE>.md              generated and checked tables
   │   └── <document>/             a LaTeX document's sources
   ├── share/
   │   └── <lib>/                  data files the package installs
   ├── benchmarks/                 programs that measure a workload, and what they read and write
   │   ├── CMakeLists.txt
   │   ├── <component>/            one program per workload, mirroring include/<lib>/, nesting to any depth
   │   │   └── <name>.cpp
   │   ├── support/                what the programs share
   │   │   ├── <name>.hpp
   │   │   ├── <name>.cpp
   │   │   └── <name>.<ext>.in     a template CMake configures
   │   ├── suites/                 the workloads: which inputs a program runs on
   │   │   └── <suite>.json
   │   ├── results/                results a test or the code reads, one file per machine
   │   │   └── <machine>.json
   │   └── tools/                  scripts that run, record, compare and report
   │       ├── <name>.py
   │       └── test_<name>.py      the scripts' own tests (pytest)
   ├── experiments/                experiments run on a cluster (Lab): their steps and configurations
   │   ├── README.md
   │   ├── <step>.py               run, parse, report, merge
   │   ├── <step>.sh
   │   └── configs/
   │       └── <axis>/             one directory per axis of the experiment (resources, planners), nesting
   │           └── <config>.json
   ├── cmake/                      CMake modules of the library's own, no subdirectories
   │   ├── <lib>_<name>.cmake
   │   └── <name>.py               a script a module runs
   └── typings/                    type stubs for packages that ship none
       └── <package>/              named as the package is imported
           ├── __init__.pyi
           ├── <module>.pyi
           └── <subpackage>/       the same, to any depth

Repository root
---------------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Path
     - What it holds
   * - ``pyproject.toml``
     - The version (the only place it is set, :doc:`release_cycle`), the Python package and its build backend, the pins
       of the upstream libraries, and the tools' settings.
   * - ``CMakeLists.txt``, ``Config.cmake.in``
     - The C++ build, and the CMake package it installs.
   * - ``README.md``, ``AGENTS.md``, ``LICENSE``
     - What the library is and how to use it; the rules for agents, which point to these documents; the license.
   * - ``peachycheck.yml``, ``ruff.toml``, ``pyrightconfig.json``
     - The linters' settings.
   * - ``include/<lib>/``
     - The public headers, one directory per component (``include/tyr/planning/``). Headers follow the
       :doc:`template_rules`: declarations in ``declarations.hpp`` and ``<name>_decl.hpp``, constraints in
       ``<name>_concepts.hpp``, definitions instantiated by the library in ``detail/<name>_impl.hpp``.
   * - ``src/``
     - The library's sources, mirroring ``include/<lib>/`` (``src/planning/`` for ``include/tyr/planning/``); headers used
       by the sources only stay here.
   * - ``exe/``
     - Executables: one directory or source per program, built against the library.
   * - ``python/``
     - The Python package (below).
   * - ``tests/``
     - The C++ tests (below).
   * - ``docs/``
     - The library's documentation, built by Sphinx.
   * - ``benchmarks/``
     - Programs that measure a workload (below).
   * - ``experiments/``
     - Experiments run on a cluster, their steps and configurations (below).
   * - ``cmake/``, ``typings/``
     - CMake modules of the library's own; type stubs for packages that ship none (below).

Every repository has ``pyproject.toml``, ``README.md``, ``AGENTS.md``, ``LICENSE``, ``peachycheck.yml``, ``.gitignore``,
``ruff.toml``, ``pyrightconfig.json`` and the lint workflow ``.github/workflows/peachycheck.yml``; a library has
``CMakeLists.txt``, ``Config.cmake.in``, ``.clang-format`` and ``.clang-tidy`` besides. The other files are optional.

A repository is a library where ``include/`` holds one directory, the library's. Without ``include/`` it is a Python
package under ``src/py<name>/`` (brokkr): it has the files of every repository, its modules and the CMake modules it
installs under ``src/py<name>/``, and ``tests/``, ``docs/`` and ``typings/`` as a library has them.

Results of experiments and evaluations (report directories, plan files, logs) are never tracked: they go to a
directory outside the repository. The only results a repository holds are a benchmark's under
``benchmarks/results/``, which a test or the code reads.

Benchmarks
----------

A benchmark is a program that runs a defined workload and measures it: how long, how much memory. Profiling (perf,
``-ftime-trace``) is done by running a benchmark under a profiler, and needs no directory of its own: there is no
``profiling/``.

#. **One program per workload, by component.** ``benchmarks/<component>/<name>.cpp`` measures what
   ``include/<lib>/<component>/`` provides (``benchmarks/planning/search/gbfs.cpp``), as ``tests/unit/`` does; the
   ``CMakeLists.txt`` of each directory builds its programs.
#. **What programs share is in** ``support/``: headers, sources, and the templates CMake configures
   (``<name>.<ext>.in``). A program includes nothing from another program.
#. **Workloads are data, in** ``suites/``: a suite (``<suite>.json``) names the inputs a program runs on, so a program
   runs any suite and a suite changes without a rebuild.
#. **Results are checked in only where something reads them**, in ``results/<machine>.json``: a test that checks a
   claim the code makes, or a choice the code bases on them (urd's container choices). Any other run's results stay
   outside the repository.
#. **Scripts are in** ``tools/``: the runner, and what records, compares and reports results.

Experiments
-----------

An experiment runs the library on a cluster over many inputs and configurations (with Lab), and reports on the
results. ``experiments/`` holds what is needed to run it again, never its results.

#. ``README.md`` says which experiments there are, how to run each, and where their results go.
#. **Its steps are scripts at the top**: ``<step>.py`` or ``<step>.sh`` (run, parse, report, merge), each a step of
   the experiment.
#. **Configurations are data, in** ``configs/<axis>/``, one directory per axis the experiment varies (the resources,
   the planners and their settings), nesting where an axis has parts (``configs/planners/gbfs_lazy/``). A
   configuration's file name says what it sets (``arrhenius-build-65536m-1800s-16cpu.json``).

CMake modules and type stubs
----------------------------

#. ``cmake/`` **has no subdirectories.** A module is ``<lib>_<name>.cmake`` (``urd_objects.cmake``), prefixed so that
   it never shadows another project's module on ``CMAKE_MODULE_PATH``; a script a module runs is ``<name>.py``. The
   package configuration template is ``Config.cmake.in`` in the root, never in ``cmake/``.
#. ``typings/<package>/`` **mirrors the stubbed package's import path**: ``typings/lab/reports/__init__.pyi`` stubs
   ``lab.reports``. Every directory has an ``__init__.pyi``, and a package is stubbed only as far as the library uses
   it.

Python package
--------------

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Path
     - What it holds
   * - ``python/py<lib>_build_backend.py``
     - The PEP 517 backend (``pybrokkr.build_backend.ProviderBackend``).
   * - ``python/src/module.cpp``
     - The extension module's entry point.
   * - ``python/src/py<lib>/``
     - The bindings, mirroring ``include/<lib>/`` (``python/src/pytyr/planning/algorithms/astar_eager/`` binds
       ``include/tyr/planning/algorithms/astar_eager.hpp``; a variant the C++ code takes as a template argument, as the
       task kind, is a submodule: ``astar_eager/ground/``), and the package's Python files. A directory of Python code
       only, with no C++ counterpart, may sit anywhere in the package.
   * - ``python/native/``, ``python/pyproject.toml``
     - urd only, at the head of the chain: the third-party native libraries the chain uses, built as the
       ``pyurd-native`` wheel (:doc:`release_cycle`), one directory per dependency (its ``CMakeLists.txt``, patches,
       ``licenses/`` and a ``package/`` configuration where upstream ships none).
   * - ``python/tests/``
     - The Python tests (pytest), by component; ``python/tests/downstream/`` builds a module against the installed
       package, as a downstream library does.

Tests
-----

Each test answers one question: when a component (a container, a function, a record type) is added, does the test have
to change? A test that does not is **generic**; it lives in one of the first five directories below, which differ in
where it takes its subjects from. A test that does is a **unit** test.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Directory
     - What it holds
   * - ``tests/rules/``
     - Checks of a rule over the whole source tree: they read the sources themselves (libclang, compile commands, the
       file tree) and name no component (urd's ``exposure.py``, ``generic.py``, ``compile_fail_*.cpp``).
   * - ``tests/laws/``
     - Suites written against a concept and run for every registered subject: a new subject gets the whole suite
       without a test written for it (urd's container properties, the facet surface over the request grid).
   * - ``tests/tables/``
     - Generated output compared with a checked-in file (urd's ``RESOLUTION.md``, ``requests.json``,
       ``vocabulary.json``).
   * - ``tests/cost/``
     - What compiling costs, held under a limit per compiler: peak memory is limited, time only reported, as it depends
       on the machine (urd's ``budget``, ``overhead``, ``scaling``). Run alone, not beside other tests, so that they
       measure what they say.
   * - ``tests/unit/``
     - One component, by example, mirroring ``include/<lib>/`` and ``src/``: the test of
       ``include/tyr/planning/state_view.hpp`` is ``tests/unit/planning/state_view.cpp``.
   * - ``tests/integration/``
     - A consumer of the installed package, built as a downstream project would; under ``python/``, a nanobind test
       module (``<name>_module.cpp``) and the Python script that drives it, which test the library's casters through
       Python.
   * - ``tests/support/``
     - Headers and fixtures the tests share; included by tests only, never by ``include/`` or ``src/``.

The conventions that keep generic tests generic:

#. **A generic test names no list of subjects by hand.** Its subjects come from the registry the code itself uses (urd's
   request grid, ``declaration_of``), or from a list that is checked against the source tree (urd's
   ``all_containers.hpp`` against the headers under ``include/urd/repr/``).
#. **A law checks what a user observes, not how it is built.** The facet surface checks which calls a Store accepts,
   not which bases it has, so it holds across a change of the facets' design, and makes that change safe.
#. **A law has failed once.** When it is added, one deliberate break of the code it guards (a constraint removed, a
   condition inverted) must make it fail; the break is named in the commit that adds it.
#. **Compile-only tests run per group.** A test that instantiates every subject is one compiler run per group of
   subjects (``-fsyntax-only``, ``-DURD_GROUP=<n>``), so that the groups run in parallel and no translation unit walks
   every subject.
#. **CTest labels are the directory names** (``ctest -L rules``, ``-L laws``, ``-L unit``): the generic checks run in
   seconds and can gate every push; ``-L cost`` runs on its own.

#. **An expected output says where it comes from.** It is either a snapshot of the library's own output (a regression
   test: it guards against a change, not for correctness) or the output of a reference (another planner: it checks
   correctness). Each generated file records its generator and its source (``"generated_by"``, ``"source": "tyr
   <version>"`` or ``"source": "fast-downward <version>"``); its generator is in ``tests/support/generators/``, beside
   the data it writes, never in ``data/``.
#. **Regenerating a snapshot is a change of behavior.** It always makes its test pass, so it is a commit of its own
   that says why the output changed. Snapshots are regenerated by hand; output that is regenerated and compared on
   every run is a table (``tests/tables/``).

A unit test copied for a second component is a law not yet written: make it one, with the components as its subjects.

Allowed files
-------------

A library's repository holds exactly the files that match one of the patterns below: each tracked path (``git
ls-files``, relative to the repository root) must match a pattern whole (Python's ``re.fullmatch``). A path that matches
none is not allowed. Files that are generated (build directories, ``__pycache__``, a LaTeX document's ``.aux``, ``.log``
and ``.pdf``, compiled documentation) are not tracked and so never need a pattern.

The patterns use two abbreviations: ``NAME`` is ``[a-z0-9_]+``, a lowercase snake_case name, and ``DIRS`` is
``(?:NAME/)*``, any depth of component directories. ``<lib>`` is the library's name.

.. list-table::
   :header-rows: 1
   :widths: 14 56 30

   * - Kind
     - Pattern
     - Holds
   * - root
     - ``(pyproject\.toml|CMakeLists\.txt|Config\.cmake\.in|README\.md|AGENTS\.md|LICENSE|Apptainer|peachycheck\.yml|ruff\.toml|pyrightconfig\.json|\.gitignore|\.gitattributes|\.clang-format|\.clang-tidy)``
     - the root files
   * - ci
     - ``\.github/workflows/[a-z0-9_-]+\.yml``
     - CI workflows
   * - directory files
     - ``(?:NAME/)+(?:README\.md|\.clang-tidy)``
     - a directory's description, its clang-tidy settings
   * - include
     - ``include/<lib>/DIRS NAME\.hpp``
     - public headers, and only headers
   * - src
     - ``src/DIRS (?:NAME\.(?:cpp|hpp)|CMakeLists\.txt)``
     - library sources
   * - exe, examples
     - ``(?:exe|examples|python/examples)/DIRS (?:NAME\.(?:cpp|hpp|py)|CMakeLists\.txt)``
     - programs and examples
   * - python
     - ``python/NAME_build_backend\.py``, ``python/(?:src/)?CMakeLists\.txt``, ``python/src/module\.cpp``
     - the backend and the module's build and entry point
   * - python package
     - ``python/src/pyNAME/DIRS (?:NAME\.(?:cpp|hpp|py)|CMakeLists\.txt)``,
       ``python/src/pyNAME/(?:__init__\.pyi|py\.typed)``
     - bindings and Python files; at the package's root only, its hand-written stubs and its typed marker
   * - python tests
     - ``python/tests/DIRS (?:NAME\.(?:py|cpp)|CMakeLists\.txt|pyproject\.toml)``
     - pytest, and the downstream module and package
   * - native dependencies
     - ``python/pyproject\.toml``,
       ``python/native/(?:CMakeLists\.txt|README\.md|LICENSE|CORRESPONDING_SOURCE\.md|SOURCES\.json|source_manifest\.cmake)``,
       ``python/native/DEP/(?:CMakeLists\.txt|NAME\.cmake|[a-z0-9_-]+\.patch)``,
       ``python/native/DEP/package/(?:CMakeLists\.txt|[A-Za-z0-9_]+Config\.cmake\.in)``,
       ``python/native/DEP/licenses/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+``
     - urd's native dependencies; ``DEP`` is ``[A-Za-z0-9_]+``, a dependency by its upstream name (``oneTBB``)
   * - tests
     - ``tests/(?:CMakeLists\.txt|__init__\.py|(?:rules|laws|tables|cost|unit|integration|support)/DIRS (?:NAME\.(?:cpp|hpp|py)|CMakeLists\.txt))``
     - the C++ tests, in their directories; ``__init__.py`` so that the generators import as
       ``tests.support.generators``
   * - test data
     - ``tests/support/data/DIRS [a-z0-9_.-]+``
     - test inputs and expected outputs, in any format the library reads
   * - test generators
     - ``tests/support/generators/DIRS NAME\.py``
     - the scripts that write expected outputs
   * - docs
     - ``docs/DIRS (?:[a-z0-9_-]+\.rst|conf\.py|requirements\.txt|[a-z0-9_-]+\.(?:svg|png))``, ``docs/_ext/NAME\.py``,
       ``docs/[A-Z][A-Z0-9_]*\.md``
     - Sphinx sources, its extensions, generated tables
   * - LaTeX
     - ``docs/[a-z0-9_-]+/[a-z0-9_-]+\.(?:tex|bib|svg|png)``
     - a document's sources, one directory each
   * - benchmarks
     - ``benchmarks/(?:DIRS)?CMakeLists\.txt``, ``benchmarks/(?!support/|suites/|results/|tools/)DIRS NAME\.cpp``,
       ``benchmarks/support/(?:NAME\.(?:hpp|cpp)|NAME\.[a-z]+\.in)``, ``benchmarks/suites/NAME\.json``,
       ``benchmarks/results/[A-Za-z0-9_.-]+\.json``, ``benchmarks/tools/NAME\.py``
     - programs by component; what they share; workloads; results something reads, named by the machine; scripts
   * - experiments
     - ``experiments/(?:README\.md|NAME\.(?:py|sh))``, ``experiments/configs/NAME/DIRS [a-z0-9_.-]+\.json``
     - the steps; configurations by axis, named by what they set
   * - share
     - ``share/<lib>/DIRS NAME\.json``
     - data files the package installs
   * - cmake
     - ``cmake/<lib>_NAME\.cmake``, ``cmake/NAME\.py``
     - the library's CMake modules, the scripts they run
   * - typings
     - ``typings/NAME/DIRS (?:__init__|NAME)\.pyi``
     - type stubs, by import path
   * - python-only package
     - ``src/pyNAME/DIRS NAME\.py``, ``src/pyNAME/py\.typed``, ``src/pyNAME/cmake/[A-Za-z0-9_]+\.cmake``
     - a repository without ``include/``: its modules, and the CMake modules it installs

(``DIRS NAME`` is written with a space for reading; the pattern has none.) The kinds *include*, *src*, *python*,
*python package*, *python tests*, *native dependencies*, *share* and *cmake* are a library's; a repository without
``include/`` has *python-only package* in their place.

These rules are about structure, which a pattern cannot state, and are checked beside the patterns:

- **Required files**: the files every repository has, and those a library has besides (*Repository root*), are
  tracked.
- **Mirroring**: a directory under ``tests/unit/`` or ``benchmarks/`` (other than ``support/``, ``suites/``,
  ``results/`` and ``tools/``), and a directory of ``python/src/py<lib>/`` that holds binding sources (``.cpp``,
  ``.hpp``) or is a parent of one that does, names a component that exists under ``include/<lib>/`` or ``src/``.
- **Stub packages**: every directory under ``typings/`` has an ``__init__.pyi``.
- **A unit test refers to its component**: a C++ test under ``tests/unit/<component>/`` includes a header of that
  component (``<lib>/<component>/...``, ``<lib>/<component>.hpp``, or one the sources keep under
  ``src/<component>/``). A Python test (``test_*.py``) under ``tests/unit/<component>/`` or
  ``python/tests/<component>/`` imports the component's module or a package that holds it, as Python reaches a
  submodule through its package; ``python/tests/downstream/`` is of no component. A test that includes nothing of the
  directory it is in is in the wrong directory, or is no unit test (a ``main.cpp``, shared fixtures:
  ``tests/support/``).
- **A header is included**: a header under ``include/<lib>/<component>/`` is included by another tracked file. A
  header at the top of ``include/<lib>/`` is an entry a user includes.

One rule needs the configured build, as only CMake knows what a target builds:

- **Every source is built, every test script is run**: a tracked ``.cpp`` under ``src/``, ``tests/``,
  ``benchmarks/``, ``exe/``, ``examples/`` or ``python/`` is a source of a target, is included by a source or a
  tracked file, or is named in a ``CMakeLists.txt`` of its directory or of one above it. A tracked Python script
  under ``tests/`` (other than ``tests/support/``) is a test pytest finds by its name (``test_*.py``), is named in
  such a ``CMakeLists.txt``, or is imported by a tracked Python file. A test in the right directory that nothing
  registers is never compiled, and its absence fails nothing.

Not allowed, among others: a source file under ``include/``; a ``profiling/`` directory (it is ``benchmarks/``);
results of a run that nothing reads; a third party's paper (link to it from the docs);
the results of an experiment or evaluation (keep them outside the repository); editor settings (``.vscode/``); a
directory or file name that is not lowercase snake_case where ``NAME`` is asked (``python/example/``, a test fixture
named ``action-costs-implicit-function``); scripts in the root (``install.sh``).

Status
------

Checked against each library's tracked files (November 2026), every library follows the rules.

``python -m pybrokkr.layout <repository>...`` checks a repository against this page: the patterns and the rules
about structure. ``python -m pybrokkr.registered --sources <build>/brokkr/sources.txt <repository>`` checks the rule
that needs the build. Each reports its findings and exits 1 where any is found.

A library runs both as tests: ``brokkr_add_rule_tests()`` in its ``tests/CMakeLists.txt`` registers ``layout`` and
``registered`` (``ctest -L rules``) and writes the sources of every target to ``<build>/brokkr/sources.txt`` when the
build is configured. A rule added to brokkr is added to that function, so a library gets it with the brokkr it builds
with. brokkr, which has no build, checks its own tree in ``tests/unit/pybrokkr/test_layout.py``.
