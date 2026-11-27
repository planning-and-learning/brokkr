Include
=======

What a header includes, every file that includes it compiles. These rules keep headers light, so that a translation
unit (TU) compiles only what it uses; they serve the goal of the :doc:`template_rules`, minimal compiler memory and time
per TU, and the measurements and examples there apply to them as well. They apply to yggdrasil, loki, tyr and runir and
are maintained only here.

Headers
-------

- .. rule:: include-declaration-headers
  .. rule:: I1

  :ruleid:`I1` :decidable:`decidable`
  **Declaration headers declare.**

  :Name: ``include-declaration-headers``

  ``declarations.hpp`` contains forward declarations, aliases, enums and tags. It
  includes only other ``declarations.hpp`` or ``*_concepts.hpp`` headers and light standard or yggdrasil core headers
  (``yggdrasil/core/*``, ``yggdrasil/formalism/builder.hpp``).

- .. rule:: include-concept-headers
  .. rule:: I2

  :ruleid:`I2` :decidable:`decidable`
  **Concepts used as constraints live in** ``<name>_concepts.hpp``, next to the header that implements them, with no
  implementation includes.

  :Name: ``include-concept-headers``

  Forward declarations that own default template arguments (``Node<Kind, State = ...>``) live
  there too; the definition then omits the defaults.

- .. rule:: include-data-headers
  .. rule:: I3

  :ruleid:`I3` :decidable:`decidable`
  **Data headers hold data.**

  :Name: ``include-data-headers``

  ``*_data.hpp`` defines ``urd::data<T>`` with indices and values only. Helpers that take
  views are templates over the view context, or live in the view header.

- .. rule:: include-no-cycles
  .. rule:: I4

  :ruleid:`I4` :decidable:`decidable`
  **No header include cycles.**

  :Name: ``include-no-cycles``
  :Check: ``python -m pybrokkr.rules I4``

  No header includes itself, directly or through other headers. In a cycle, the header
  that is included second sees the first one only partly, so what compiles depends on which header a file includes
  first. The check reads the ``#include`` lines of every tracked file, in every ``#if`` branch, so it also reports a
  cycle that only a configuration not built would close.

- .. rule:: include-hold-by-pointer
  .. rule:: I5

  :ruleid:`I5` :judgment:`judgment`
  **Hold heavy types by pointer or reference with declaration-only includes.**

  :Name: ``include-hold-by-pointer``

  Where the header otherwise keeps the
  pointee incomplete, dereference a smart pointer with ``*ptr.get()``, not ``*ptr``, in inline code: the overloaded
  ``operator*`` makes argument-dependent lookup complete every template argument of the ``shared_ptr``, which
  instantiates the pointee. Raw pointers and pointees that are complete anyway are not affected. A header that uses a
  view by value (``std::optional<ClassifierView>``) includes the repository of that view: a view specialization
  constrained on an incomplete repository silently falls back to the primary template, and GCC keeps that choice for
  the rest of the TU. Code in a template that uses a held type in a non-dependent expression
  (``m_builder.get_workspace()`` with ``Builder& m_builder``) is checked at the definition and needs the type complete:
  move such uses into small non-template functions defined in the library, or include the definition. Treat GCC's
  "invalid use of incomplete type" warnings as errors. The same holds for calls: a call to a function template with
  non-dependent arguments inside a template, or any template call in a non-template inline function, instantiates the
  callee in every includer even if the enclosing function is never used. Route heavy ones (a query compiler,
  canonicalization) through a declared library function. ``assert`` bodies count too: they compile only in Debug
  builds, so build Debug once after such changes. A class may also hold a ``std::vector`` of an incomplete type:
  declare the members that need the element complete (size, element access, move assignment, destructor) and define
  them out of class with the other hidden definitions (:rule:`T2`).

- .. rule:: include-include-what-you-use
  .. rule:: I6

  :ruleid:`I6` :judgment:`judgment`
  **Include what you use.**

  :Name: ``include-include-what-you-use``

  A header compiles on its own. Library code, tests and executables include the components they use, never umbrella
  headers such as ``tyr/planning/planning.hpp``. A type's own formatter is declared beside the type, so its header
  brings it; a generic formatter's header is included where it is used
  (``yggdrasil/formatting/cista_formatters.hpp``). Measure third-party headers on their own before including them from
  a widely used header; a small utility can carry a large include tree.

- .. rule:: include-pimpl
  .. rule:: I7

  :ruleid:`I7` :judgment:`judgment`
  **Pimpl at high-level entities** (heuristics, state repositories, executors) **and at a repository whose stores its
  includers do not need.**

  :Name: ``include-pimpl``

  A formalism repository (yggdrasil's ``Repository``) declares its members in its header and
  keeps its stores behind a pointer to its implementation, which one source per library instantiates
  (``yggdrasil/formalism/repository_instantiations.hpp``): a file that reads records through it completes none of its
  stores. Each read becomes a call; in tyr that costs 1-3% of search time, with the same results, and saves 16% of the
  summed peak memory and 23% of the CPU time of a full build (runir, which reads tyr's repositories: 11% and 11%).
  Its interface forwards what its users ask (a count, a membership, a row) and never hands out a store: a user that
  reaches into one completes it. Never in views,
  interning or evaluation, whose code is the hot loop itself.

