Template and include rules
==========================

Compile cost in yggdrasil, loki, tyr and runir is dominated by the C++ front end: template instantiation and the headers
that trigger it, not optimization or LTO. These rules keep translation units (TUs) small. They apply to all four
repositories and are maintained only here; the other repositories link to this page.

Goal: minimal compiler memory (max RSS of ``cc1plus``) and time per TU in a Release + LTO build with GCC, with a
coherent structure that every repository follows.

Headers
-------

1. **Declaration headers declare.** ``declarations.hpp`` contains forward declarations, aliases, enums and tags. It
   includes only other ``declarations.hpp`` or ``*_concepts.hpp`` headers and light standard or yggdrasil core headers
   (``yggdrasil/core/*``, ``yggdrasil/formalism/builder.hpp``).
2. **Concepts used as constraints live in** ``<name>_concepts.hpp``, next to the header that implements them, with no
   implementation includes. Forward declarations that own default template arguments (``Node<Kind, State = ...>``) live
   there too; the definition then omits the defaults.
3. **Data headers hold data.** ``*_data.hpp`` defines ``urd::data<T>`` with indices and values only. Helpers that take
   views are templates over the view context, or live in the view header.
4. **Hold heavy types by pointer or reference with declaration-only includes.** Where the header otherwise keeps the
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
   them out of class with the other hidden definitions (rule 8).
5. **Include what you use.** A header compiles on its own. Library code, tests and executables include the components
   they use, never umbrella headers such as ``tyr/planning/planning.hpp``. This includes the formatter headers of every
   type that is formatted (``tyr/planning/formatter.hpp``, ``yggdrasil/formatting/cista_formatters.hpp``). Measure
   third-party headers on their own before including them from a widely used header; a small utility can carry a large
   include tree.
6. **Pimpl only at high-level entities** (heuristics, state repositories, executors), never in views, repositories,
   interning or evaluation.

Instantiation
-------------

7.  **Explicitly instantiate when the same instantiation is repeated in many TUs and the declaration is cheap.** Define
    the members out of class: members defined in the class body are implicitly inline and GCC still instantiates them in
    every TU that uses them, despite ``extern template``. This includes the constructors and the destructor: declare
    them in the class and define them out of class (``~T();`` and ``template<...> T<...>::~T() = default;``), or every
    TU that creates or destroys an object instantiates the destructors of all its members. Instantiate the whole class
    (``template class T<...>;``), not only its out-of-class members: under ``extern template``, GCC also calls inline
    members it does not inline, so the library must provide them too.

8.  **Prefer hiding definitions over** ``extern template``. Put the definitions in ``detail/<name>_impl.hpp``, include
    it only from the instantiating sources (and under ``<PROJECT>_HEADER_INSTANTIATION``), and instantiate in the
    library. Users then only link. Headers that the definitions need include the declarations as ``<name>_decl.hpp``,
    and only the public ``<name>.hpp`` adds the definitions under ``<PROJECT>_HEADER_INSTANTIATION``, so that build mode
    has no include cycle. Build it once after moving definitions. An ``extern template`` declaration of a class
    instantiates the class definition in every includer, so long extern lists or externs over heavy classes cost more
    than they save. Compile a shared library with ``-fno-semantic-interposition`` (GCC): otherwise calls between its own
    exported functions go through the PLT and are not inlined, so small hot functions moved out of headers become calls.

9.  **Make extern lists opt-in when the definitions must stay visible.** Put ``extern template`` declarations for widely
    shared instantiations (such as the symbol storage of every symbol type) in a separate
    ``detail/<name>_instantiations.hpp`` that only the TUs doing that work include, e.g. parsers and translators that
    intern every type. Including such a list everywhere costs every light TU the class instantiations.
    ``yggdrasil/formalism/intern_instantiations.hpp`` spells the list of ``intern`` instantiations from a repository's
    type list (``YGG_FORMALISM_INTERNS``): the opt-in header declares them ``extern``, one library source defines them.
    Keep the list in the main header instead when nearly every includer does the work: in tyr, removing it from the
    repository headers made 60 TUs heavier and one lighter. Decide by measuring both, in the full build: a standalone
    probe of the same command can show a gain the build does not. Extern lists pay off for classes whose member bodies
    are heavy and used by many TUs (interning: hashing, lookup, insertion). They lose for classes whose cost is the
    class definition itself (object pools, builder storage, relation storage): the declaration instantiates the
    definition in every includer and saves little. The instantiating sources of a list also lengthen the library's LTO
    link, a serial step of the build; peak build memory decides: drop a list only if that does not raise the peak at the
    build's parallelism. Opt-in lists rely on the library exporting every instantiated member; ld64's LTO drops weak
    explicit instantiations that nothing inside the dylib calls, so a library whose includers call members it never
    calls itself builds without LTO on macOS.

10. **No deduced return types on functions that are declared** ``extern`` **or used only through declarations**:
    deducing the type instantiates the body.

11. **Split instantiating sources only along the dimension that drives their cost** (family, task kind, context or
    constructor category) so no single TU dominates, even if the summed memory grows by the repeated includes. Test a
    dimension by compiling the parts merged: if the merged source costs about as much as one part, the parts share their
    instantiations and the split only compiles them twice, so merge them as long as the merged source stays below the
    heaviest TU of the build. Tests split the same way: shared fixtures go to a ``<test>_fixtures.hpp`` header, and the
    parts stay in one test executable. A split lowers the heaviest TU, but the peak build memory only if the heavy TUs
    no longer overlap: the parts fill the parallel slots. Keep a split only if the peak drops (identical builds vary by
    about 1 GB at -j12, so compare two runs each).
    Merge with ``brokkr_unity_directories(<target> ENABLED ${<PROJECT>_UNITY_BUILD} DIRECTORIES ...)``: the sources of
    each directory listed compile as one TU, and ``<PROJECT>_UNITY_BUILD=OFF`` compiles them apart again (for
    clang-tidy, and for rebuilds after editing one source). Light sources that include the same headers merge to about
    their largest part (type tests, bindings of one family). Merged heavy sources keep the summed memory down but can
    raise the peak at high parallelism, as more slots hold heavy TUs at once (the heaviest TU, and so the peak at low
    parallelism, stays): keep such a merge only where it buys wall time, and say so. A batch puts the file-local names
    of its sources into one TU: a name declared twice fails to compile (give each file a namespace of its own), but
    internal functions of one name and different parameters become overloads, and a call may resolve to another file's;
    look for them before listing a directory (``python -m pybrokkr.unity_check --compile-commands <db> <directory>...``,
    with the batches off), and rename them or give them their own namespace. Where a target's heavy TUs still overlap,
    cap how many of them compile at once (``brokkr_limit_compile_jobs(<target> JOBS <n>)``, a Ninja job pool): the
    other targets fill the free slots, so the peak drops at about the same wall time. The cap depends on the machine,
    so ``<n>`` is a cache variable set at configuration time, empty (no cap) by default.

12. **One container for many record types.** Memo tables, visited sets and caches keyed by records of every type in a
    type list use one container keyed by (type position, index) instead of a tuple with one container per type: each
    container type instantiates its whole hash table. The key carries no dispatch; views are rebuilt from the index.

15. **No all-types invocability constraints on internal visitors over long type lists.** ``InvocableWithEach<F, List>``
    (or ``std::invocable<F, T>`` for each ``T``) on a generic lambda instantiates the lambda body for every type in the
    list, at every instantiation of the constrained function: a recursive visitor over N record types costs N x N body
    instantiations although each node visits only its few children. Constrain the public entry point if a diagnostic is
    wanted; leave internal helpers that only forward the visitor unconstrained.

16. **Dispatch your own types before a generic library's trait-based dispatch.** ``boost::json::value_from`` computes
    every conversion category (user, native, generic: sequence, map, tuple, optional, described class) of every nested
    type it converts, even when a ``tag_invoke`` overload matches. For types the library describes itself (yggdrasil's
    ``describe_fields``), and ranges and optionals of them, convert directly and hand only leaf types to the generic
    library. Types serialized as another object declare ``serialize_as(Dictionaries&, const T&)`` instead of a competing
    ``tag_invoke``.

17. **Check compile-time contracts where the instantiation already exists.** A ``static_assert`` over overload
    resolution against a heavy class (``InternsData``, ``rejects_symbol`` on a repository) instantiates that class. In a
    test that checks many repositories it re-instantiates all of them; in the library source that explicitly
    instantiates the repository it costs almost nothing. Put such contracts next to the explicit instantiation, with the
    shared contract concepts in a ``detail`` header; tests keep the contracts on light types.

18. **Template on what the code depends on, not on what it passes along.** A parameter that only forwards to other
    templates multiplies every instantiation by its values and keeps the code out of the library. When the data is
    uniform (encoded bytes, indices) and only typed access needs the type, give the type its own identity (a constant of
    its codec or traits, not its position in a list) and keep the type list at the edges that turn a runtime type back
    into a value type. Once the parameter is gone, the code is no longer a template: move its definitions into the
    library (rule 8), or every includer compiles them (rule 4). The parameter also deferred checking: expressions that
    no longer depend on a template parameter are checked where they are written, so they need complete types there (an
    include, a deduced parameter such as the repository type, or a library definition), and a recursive structure must
    define a type before the members that hold it by value.

19. **Split storage templates into a read header and a write impl.** When the write path of a widely included storage
    template (insertion, serialization) needs a dependency its read path does not, keep the class and the read API
    (``at``, ``operator[]``, ``size``, iteration, views) in ``<name>.hpp`` and define the whole write API (``insert*``,
    ``create*``, ``complete_miss*``, ``append*``, ``serialize``) in ``detail/<name>_impl.hpp``. Split along this
    boundary, not along the individual functions that need the dependency, and only when the measured difference is
    large. The class comment names the impl header. Sources with the explicit instantiation lists include the impl,
    ``<PROJECT>_HEADER_INSTANTIATION`` builds include it in the ``#else`` branch of the extern list, and code that
    interns types nobody else instantiates adds explicit instantiations in one source. When a member only serves the
    write side (the value-to-index hash table of an interning set), declare its class in the header, define it in the
    impl and hold it by an owning raw pointer that the impl creates and deletes: the read header then never instantiates
    it. Not by ``std::unique_ptr`` in a template instantiated per record type: it instantiates ``unique_ptr``,
    ``__uniq_ptr_impl`` and a ``std::tuple`` for every element type. Value lookup (``find*``), construction,
    destruction, ``clear`` and memory accounting go to the impl with it. A container keeps its element storage behind
    the same pointer, so reads and writes share one indirection; it holds by value only what inline reads need, a view
    of the storage (``detail::SegmentedRows``: the segment table's and the size's addresses), whose type does not depend
    on the storage template. Apply this in the containers only: their holders (repositories, tree sets) keep them by
    value. Define these members out of class: functions defined in the class body are implicitly inline, and an extern
    template declaration does not stop their instantiation in the includer.

20. **Keep** ``std::tuple`` **and** ``std::unique_ptr`` **out of per-type code.** A ``std::tuple`` of N types
    instantiates N levels of ``_Tuple_impl`` and the constraint traits of its constructors, and ``std::unique_ptr``
    stores its pointer
    in a ``std::tuple``. In code instantiated for every record type or over long type lists, hold an owned object by raw
    pointer and keep the ownership in the out-of-class special members (rule 19), keep one object per type in flat bases
    (``struct Slots : Slot<Ts>... {}``, listed in reverse to keep ``std::tuple``'s destruction order: pooled objects may
    own handles into the pools of later types), and list record fields as member pointers
    (``static constexpr auto cista_members() noexcept { return ygg::Members<&Data::index, &Data::a> {}; }``; our cista
    fork folds over a static ``cista_members()`` that returns such a pack) so that serialization, hashing, child visits
    and ``clear()`` fold over the pointers (``ygg::for_each_member``, ``ygg::clear_members``) instead of ``std::tie``
    and ``std::apply``. A ``cista_members()`` that returns ``std::tie`` in a non-template record compiles in every
    includer. Find such costs with clang's ``-ftime-trace`` over the heaviest TUs, summed by template name.

21. **Compute once per value what depends on a value only.** A constant computed per template (a variable template, a
    static data member) is computed again for every template argument list, even where it depends on part of it only.
    Key it by that part, passed as a value: urd's choice of a container depends on the request's shape (what it
    requires, what its data is, what it holds), not on its element types, so ``serving_for<Kind, Shape>`` scans the
    kind's table once per shape, and every Store of that shape reuses the scan (74 shapes among 832 Stores in two
    pyrunir TUs). The value must be structural, as urd's ``property_set`` is.

22. **Expand a pack instead of recursing over it.** A recursion over a list is one class instantiation per step, each
    carrying every argument of the recursion; where one is a large value (a ``property_set`` of 64 tags), naming and
    comparing it costs more than the step's work. urd's spec of a request takes the answer of each category of its
    kind's format in one expansion (``answers_of<Meant>(format)``: an ``mp_append`` of each category's answer, or of
    nothing), not in a recursion of one step per category for every Store.

23. **Build a** ``std::variant`` **by its index.** Its converting constructor resolves an overload set over all
    alternatives (``_Build_FUNs``) for every type it is called with, so building each alternative of an N-way variant
    from a value resolves N sets of N. ``std::in_place_index<I>`` names the alternative instead. libstdc++ still builds
    alternative I through I nested unions (``_Variadic_union``), about N²/2 instantiations for a variant whose every
    alternative is built; a variant of many alternatives that is built often (a record's variant of child views) is a
    cost of its own, which only a type of fewer alternatives, or none, removes.

24. **Define a recursion over every record kind once, at the records of any kind.** A visitor that recurses through a
    record's children (an optimizer, a measure, a statistics collector) instantiates, from any one record, the closure
    of every kind below it; defined in a header, it makes every includer that calls it on one record compile all of
    them. Declare it in the header for the records of any kind, the variants that children are held as (a constructor
    of each category, a query of any kind): plain overloads, or explicit specializations of a member template, defined
    in the library. An includer then compiles the record it calls the visitor on and stops at its children. Move the
    non-template members that call the recursion out of the class too: their bodies instantiate it where the class
    ends, before the specializations are declared (ill-formed; clang rejects it, GCC does not). An inline non-template
    function in a header costs the same: every includer instantiates what it calls, whether or not it calls it.

Process
-------

13. **Measure before and after.** Use the standalone cost of a header (``-fsyntax-only`` of a TU that only includes it),
    the cost of a single API call (the TU's includes plus that call, at ``-fsyntax-only`` and at ``-O3``), and a full
    instrumented build logging the max RSS per TU. GCC's peak RSS also depends on when its garbage collector runs, which
    moves single TUs by up to about 200 MB without any change in live memory; check a surprising rise with
    ``--param ggc-min-expand=10 --param ggc-min-heapsize=32768`` before and after. Build each repository against a
    prefix that holds only the third-party dependencies and the freshly installed upstream repositories: the yggdrasil
    install bundles the prefix into ``pyyggdrasil/``, whose include directory comes first, so a stale loki or tyr
    install there silently replaces the headers being measured.
    ``python -m pybrokkr.compile_cost`` records a build through CMake's compiler launcher
    (``-DCMAKE_CXX_COMPILER_LAUNCHER="python;-m;pybrokkr.compile_cost;record;<log>"``: every object's time and the
    compiler's max RSS), summarizes a log and compares two by object. Sample the memory in use on the machine
    (``MemAvailable`` in ``/proc/meminfo``) during the build for its peak. ``compile_cost weak <build dir>`` sums the
    weak definitions of all objects by template: what the build compiles in more than one TU. A template that a
    library instantiates explicitly, found weak in another object, marks a TU that does that work without the opt-in
    list that declares it (rule 9); an extern list declared before its use keeps it out (an undefined symbol instead).
14. **Keep only what wins in the full build.** A smaller standalone header often does not shrink its includers, which
    may instantiate the same code anyway. Revert changes that do not lower the max or summed memory of the affected TUs.

Examples
--------

.. list-table::
   :header-rows: 1

   * - Rule
     - Change
     - Effect
   * - 1
     - ``tyr/analysis/declarations.hpp`` stopped including the formalism repositories
     - 1.0 GB to 0.3 GB per includer (113 TUs)
   * - 2
     - ``tyr/planning/state_view_concepts.hpp``
     - ``StateViewConcept`` costs 0.2 GB instead of 1.1 GB
   * - 3
     - ``runir/kr/dl/semantics/register_values_data.hpp``
     - 0.75 GB to 0.26 GB
   * - 4
     - runir constructor and denotation repositories hold the tyr repository by pointer
     - ``runir/kr/dl/repository.hpp`` 0.75 GB to 0.47 GB
   * - 5
     - tyr statistics and heuristic tests include only the tested component
     - 2.5 GB to 2.0 GB per test TU
   * - 5
     - pyrunir serialization bindings include their component's type list and serializers instead of
       ``runir/serialization/{types,serialization}.hpp`` (1.65 GB each); the type lists split into
       ``runir/serialization/types/*.hpp``
     - 20 DL, denotation and Uns bindings -0.9 to -1.0 GB, ps bindings -0.25 to -0.62 GB, identical symbols; pyrunir
       summed memory -20 GB, peak at -j12 29.6/31.0 GB to 27.8/26.8 GB, same wall time
   * - 15
     - runir DL ``QueryOptimizer::for_each_child`` without the ``InvocableWithEach`` constraint over all record types
     - pyrunir DL semantics and feature bindings -0.5 to -0.67 GB each (4.6 GB to 4.1 GB), optimization test -0.12 GB;
       pyrunir summed memory -5 GB, peak at -j12 26.4/28.2 GB to 26.3/25.6 GB
   * - 16
     - yggdrasil ``Dictionaries::convert`` serializes described types and their ranges and optionals directly; runir's
       bidirectional graph uses ``serialize_as``
     - pyrunir ``graphs`` binding 4.65 GB to 3.88 GB and 40 s to 36 s, execution and ps bindings -0.18 to -0.28 GB, DL
       bindings about -0.12 GB; same JSON (new nested test passes with the old and new header)
   * - 17
     - runir constructor repository interning contracts moved from the DL family traits test into the nine
       ``repository_*.cpp`` sources
     - test 4.69 GB to 2.72 GB and 31 s to 17 s (the heaviest runir TU); repository sources +0 to +9 MB
   * - 17
     - runir DL type tests' view and data contracts (one per constructor type) probed in the repository source
     - ``repository_ext.cpp`` +0.95 GB for the Ext third: the library does not instantiate the views, so the cost only
       moves; not applied
   * - 6
     - tyr planning ``Parser`` keeps its loki state behind a pointer
     - tyr summed memory -24.5 GB (38 TUs up to -0.74 GB), runir -12 GB
   * - 7
     - yggdrasil ``BasicSymbolRepository`` members out of class, symbol storage instantiated in loki and tyr
     - loki max TU 2.2 GB to 1.8 GB, tyr summed memory -4.6%
   * - 7
     - yggdrasil ``BasicSymbolRepository`` constructor and destructor out of class
     - loki max TU 1.80 GB to 1.70 GB; summed memory tyr -7.5 GB, runir -9.6 GB (query evaluation test 5.8 GB to 4.6 GB)
   * - 7
     - runir ``EvaluationGraph`` and ``IncrementalEvaluation`` destructors out of class
     - 8 TUs -57 to -113 MB
   * - 8
     - runir DL evaluator compiled in eight library sources
     - evaluating TUs -0.2 to -1.0 GB
   * - 8
     - runir Ext evaluator with borrowed register values instantiated in the library instead of five tests
     - test TUs -0.4 to -2.3 GB (max 7.5 GB to 5.3 GB), two new 2.8 GB sources
   * - 8
     - runir Ext query evaluator over builder states instantiated in the library instead of a test
     - successor expander test 4.5 GB to 4.0 GB, library source +44 MB; tests that pass their own callbacks to member
       templates (``for_each_successor``) keep including the definitions
   * - 4
     - runir incremental ``EvaluationGraph`` holds its nodes as a vector of incomplete types; the accessors that read
       nodes are defined in ``detail/evaluation_impl.hpp`` and instantiated in the library, ``SetOperationWorkspace``
       has its own header, and the delta policy reaches the database workspace through a library function
     - ``incremental/evaluation.hpp`` 1.93 GB to 0.82 GB on its own; executors -0.27 and -0.35 GB, executor and
       evaluation tests -0.15 to -1.4 GB; peak at -j12 25.7/25.1 GB to 23.5/24.9 GB, same wall time
   * - 4
     - runir projection heuristic calls ``ygg::database::compile`` through a library function instead of a non-dependent
       call in ``abstract_edges``
     - ``heuristics/projection.hpp`` 0.81 GB to 0.59 GB, ``task_context.hpp`` 1.38 GB to 1.04 GB on their own
   * - 4
     - runir Ext execution storage reads the entry module's register counts from its data instead of a non-dependent
       ``get_registers<...>()`` call
     - ``ps/ext/execution_storage.hpp`` 2.13 GB to 1.79 GB on its own; executors unchanged (they use the views anyway)
   * - 4
     - loki ``detail::copy`` declared with explicit types and defined in ``src/semantic/translator.cpp`` instead of two
       inline non-template functions
     - ``semantic/translator/copy_translator.hpp`` 1.27 GB to 1.00 GB on its own (6 sources and 2 tests)
   * - 5
     - a standalone scan of all 1192 public headers (clang, one TU each)
     - three headers did not compile on their own: tyr ``datalog/ground/workspaces/rule.hpp`` and
       ``datalog/statistics/program.hpp`` (missing includes), runir ``dl/family_traits.hpp`` (include cycle with
       ``declarations.hpp``)
   * - 5
     - yggdrasil ``SpinSharedMutex`` and ``SpinMutex`` (``core/spin_mutex.hpp``) implement oneTBB's ``spin_rw_mutex``
       and ``spin_mutex`` algorithms with ``<atomic>`` and compiler builtins instead of including the oneTBB headers,
       whose backoff pulls in ``<immintrin.h>`` (116 MB) and ``<thread>`` (74 MB); same state words, sizes and
       alignments
     - ``formalism/symbol_repository.hpp`` 396 MB to 293 MB on its own; summed memory yggdrasil 64.2 GB to 57.9 GB, loki
       105.9 GB to 92.2 GB (no TU heavier)
   * - 1, 8
     - tyr headers that only take ``ygg::ExecutionContext&`` include ``yggdrasil/execution/declarations.hpp`` instead of
       ``execution/onetbb.hpp`` (``task_arena``, 215 MB on its own); ``execute_model`` is defined in
       ``src/datalog/solver_impl.hpp`` and instantiated next to ``compute_model``; with the row above
     - summed memory tyr 236.1 GB to 214.1 GB (TUs above 1 GiB 136 to 94), runir 256.4 GB to 237.5 GB (median 1.23 GB to
       1.10 GB); 24 tyr TUs that create an ``ExecutionContext`` grew 21-36 MB because ``onetbb.hpp`` now comes after the
       tyr headers (first include: back to the old cost); ``ground/solver.cpp`` +54 MB for the ``execute_model``
       instantiations
   * - 19, 5
     - cista fork: ``hashing.h`` without the ``std::chrono`` specializations (moved to ``hashing_chrono.h``, included by
       ``serialization.h``), so ``cista/containers/variant.h`` no longer pulls in ``<chrono>`` (``<format>``,
       ``<locale>``, ``<sstream>``); yggdrasil ``buffer/declarations.hpp`` includes ``cista/targets/buf.h`` instead of
       ``cista/serialization.h``, and the write APIs of ``buffer::IndexedHashSet`` and ``BasicSymbolRepository`` are
       defined in ``detail/*_impl.hpp``, included by the instantiating sources (moving the whole write API instead of
       only the functions that serialize: no change in loki, tyr or runir)
     - ``formalism/symbol_repository.hpp`` 293 MB to 197 MB, ``database/semantics/relation_repository.hpp`` 341 MB to
       268 MB on their own; summed memory yggdrasil 57.9 GB to 55.6 GB, loki 92.2 GB to 82.8 GB, tyr 214.1 GB to 206.4
       GB, runir 237.5 GB to 228.8 GB; CPU time -3 to -14%
   * - 13
     - the TUs that grew with the row above (tyr search and heuristics +35 to +72 MB, runir
       ``ps/ext/program_executor.cpp`` +196 MB)
     - with frequent collections the same TUs are unchanged or lighter (gbfs_lazy 1206 MB to 1169 MB, program_executor
       3276 MB to 3288 MB including its new explicit instantiations); the rise is GC timing
   * - 5
     - gtl patch (``src/gtl/settings-struct.patch``): ``raw_hash_set`` keeps growth_left, hasher, key_equal and
       allocator in a struct with ``[[no_unique_address]]`` members instead of a ``std::tuple``, which every record
       type's hash set instantiated anew (std::tuple and its traits were 31% of the instantiation time of the 18
       heaviest downstream TUs); same layout
     - summed memory loki 82.8 GB to 77.5 GB (TUs above 1 GiB 11 to 5), tyr 206.4 GB to 188.4 GB (median 885 MB to 784
       MB, above 1 GiB 90 to 70), runir 228.8 GB to 203.1 GB (max 3.89 GB to 3.40 GB, above 1 GiB 109 to 83); CPU -6 to
       -8%; no TU heavier
   * - 18
     - records list their identifying members as member pointers,
       ``static constexpr auto identifying_members() noexcept { return ygg::Members<&Data::a, &Data::b> {}; }``, instead
       of returning ``std::tie(a, b)``; ``Hash``, ``EqualTo`` and ``Less`` fold over the pointers, so no tuple,
       ``std::tie`` or ``std::apply`` is instantiated per record type (a static function, not a type alias: a class
       template is still incomplete while its own aliases are instantiated)
     - tyr's 107 records converted: summed memory 188.4 GB to 176.7 GB, median 784 MB to 701 MB, CPU -5%; one TU +36 MB
   * - 19
     - yggdrasil ``IndexedHashSet`` (both) holds its element vector by value and its value-to-index table (``Lookup``:
       the gtl set and its functors) behind a ``std::unique_ptr`` to a class defined in
       ``detail/indexed_hash_set_impl.hpp``; ``BasicSymbolRepository`` construction, ``clear``, ``memory_usage`` and
       ``find_local*`` moved to its impl; with inline segment pointers in ``SegmentedVector`` and a segmented
       ``ObjectPoolStorage``
     - summed memory loki 74.9 GB to 70.1 GB, tyr 180.3 GB to 156.5 GB (above 1 GiB 67 to 50, max 1.95 GB to 1.70 GB,
       median 565 MB to 483 MB), runir 198.1 GB to 169.2 GB (above 1 GiB 76 to 59, max 3.19 GB to 2.79 GB), yggdrasil
       58.8 GB to 57.7 GB; CPU -4 to -16%; changes the container layout, so prebuilt downstream packages must be rebuilt
   * - 19
     - yggdrasil ``IndexedHashSet`` (both) holds its ``Lookup`` by an owning raw pointer instead of ``std::unique_ptr``
       (clang time traces of the heaviest TUs: ``unique_ptr``, ``__uniq_ptr_*`` and their ``std::tuple`` were about 12%
       of runir's front end, nearly all from ``IndexedHashSet``)
     - summed memory loki 69.0 GB to 65.8 GB (above 1 GiB 3 to 1), tyr 152.5 GB to 141.1 GB (median 579 MB to 525 MB,
       above 1 GiB 46 to 30, max 1.66 GB to 1.54 GB), runir 164.5 GB to 143.8 GB (median 672 MB to 545 MB, above 1 GiB
       60 to 48), yggdrasil 53.2 GB to 52.8 GB; peak at -j32 tyr 41.6 GB to 37.5 GB; CPU -4 to -9%; no TU more than 20
       MB heavier
   * - 7
     - runir ``ConstructorRepositoryFactory::create`` defined in ``detail/constructor_repository_impl.hpp`` (the class
       is extern but ``create`` was in the class body)
     - a TU that creates a repository 2.27 GB to 0.78 GB; with the projection change: 49 runir TUs -50 MB to -0.6 GB,
       summed -13.3 GB, none heavier than +6 MB
   * - 7
     - runir ``DenotationRepository`` constructor, destructor and factory, and the ps
       ``BasicRepositoryFactory::create``, defined in the library
     - callers no longer construct or destroy the symbol pools; needed for the macOS link of the incremental query test
   * - 4
     - runir CNF translation asserted ``==`` on two ``shared_ptr``\ s to the planning repository
     - completed the repository type in Debug builds only (GCC 13 CI error); compares ``.get()`` now
   * - 9
     - runir on macOS: ld64 LTO dropped the denotation and query pool members that only tests call through the opt-in
       extern lists
     - runir skips LTO on Apple; Linux keeps it
   * - 9
     - runir Uns parser includes extern declarations of the Uns symbol storage
     - 3.95 GB to 2.89 GB
   * - 9
     - runir optimization, query evaluation and successor expander tests include the lists of the families they intern
     - -0.3 to -0.5 GB per TU; the same lists cost +0.1 to +0.7 GB in TUs that only evaluate
   * - 9
     - pyrunir bindings that intern or evaluate include their family's lists and the denotation list
     - 24 binding TUs -0.2 to -1.5 GB, summed pyrunir memory -22 GB; the lists cost up to +0.4 GB in bindings that only
       wrap views
   * - 9
     - runir grammar and CNF grammar lists dropped, then restored
     - link -56 s and wall 379 s to 342 s, but peak at -j12 26.1 GB to 28.5 GB; restored because peak memory limits the
       build
   * - 9
     - second runir sweep over all TUs above 1.4 GB without lists
     - ten more TUs -65 to -534 MB (domain_context, parser, structural termination, classifier and executor tests); none
       between 1.4 and 2 GB gained more than 100 MB
   * - 11
     - tyr applicability, serialization and datalog solver tests split along task kind and test groups
     - 3.05-3.3 GB to at most 2.95 GB
   * - 11
     - the runir optimization test split by task kind
     - no change (7.1 GB per half); the cost depends on the family
   * - 11
     - runir DL evaluator and incremental engine merged from 16 sources (family x kind x context) into one per family
     - 2.8-3.6 GB per part, 3.5-4.0 GB per family; summed build memory 334 GB to 299 GB, wall 403 s to 370 s
   * - 14
     - runir program executor data headers without the proof graph and plan definitions
     - 1.4 GB to 0.5 GB on their own, no change in the build: every includer uses the graph; reverted
   * - 12
     - runir DL and ps optimizers memoize in one map instead of one per record type
     - optimization test 6.4 GB to 4.2 GB; pyrunir bindings that optimize -1.1 to -3.0 GB each (max 8.8 GB to 5.8 GB)
   * - 14
     - runir ``DenotationCaches`` with one map for the four category caches (rule 12)
     - evaluating library sources -38 to -54 MB (1.5%): the query and join-index caches dominate the class; tests check
       per-category entries, which one map can answer only with extra counters on the hot path; reverted
   * - 14
     - yggdrasil ``BasicRelationRepository`` members out of class with extern declarations in loki and tyr
     - summed memory +0.1 GB loki, +1.2 GB tyr, +0.8 GB runir: few TUs use the relation storage; reverted
   * - 14
     - runir ``EvaluationPolicyConcept`` in its own concepts header
     - ``ps/rule_evaluator_concepts.hpp`` 2.1 GB to 0.8 GB on its own, no change in the build: every includer needs the
       policies; reverted
   * - 14
     - yggdrasil ``BuilderStorage`` constructor and destructor out of class, builders declared extern in loki and tyr
       (global) and runir (opt-in)
     - tyr summed memory +7.9 GB (123 TUs heavier, max 2.80 GB to 2.64 GB), runir +4.4 GB, opt-in sweep +0.2 to +1.3 GB
       in every heavy runir TU: the extern class instantiates every pool; reverted
   * - 11
     - runir DL grammar parser instantiations split by family
     - 4.2 GB, 64 s to 2.5-2.8 GB, 25-28 s per family; summed memory +3.7 GB
   * - 14
     - runir symbol storage instantiated member by member (only out-of-class members) to shorten the library LTO link
     - link 240 s to 225 s, but tests failed to link: inline members such as ``at_local`` are called out of line;
       reverted
   * - 14
     - runir ``datasets/declarations.hpp`` so the task context does not include the task search context
     - ``task_context.hpp`` 1.7 GB to 1.4 GB on its own, +175 MB in the build: its includers need the search context;
       reverted
   * - 14
     - runir DL optimizer behind a pointer and compiled once per family in the library (rules 6 and 8)
     - pyrunir summed memory -18 GB and TUs above 3 GiB 37 to 20, but peak at -j12 runir 26.4 GB to 28.9 GB, pyrunir
       28.6 GB to 29.4 GB; reverted
   * - 14
     - the same with each family's source split into optimizer and statistics halves (rule 11)
     - runir peak 26.6 GB to 26.9 GB and wall 333 s to 359 s, pyrunir peak 28.6 GB to 30.0 GB; reverted: new library
       sources raise the peak while other heavy TUs compile
   * - 11
     - runir family traits, query evaluation and query allocation tests split along their test groups
     - heaviest TU 4.7 GB to 4.2 GB, but peak at -j12 24.6/26.0 GB before and 25.7/26.4 GB after, same wall time;
       reverted
   * - 11
     - runir symbol storage sources kept per repository and family
     - merging three costs as much as the parts (44-57 s, 4-5 GB)
   * - 18
     - yggdrasil database engine without the ``ColumnTypes Values`` parameter (360 templates); column layouts store
       ``ColumnCodec<T>::id``, the list remains only in ``visit_column_type`` and ``validate_row``; definitions still in
       headers
     - query test 2.41 GB to 1.55 GB and 34 s to 18 s (it instantiated the engine for three lists), other database TUs
       -8% to +44%: median 622 MB to 879 MB, headers on their own 0.45-0.65 GB to 0.57-0.95 GB, since the now
       non-template inline code compiles in every includer (rule 4); the definitions belong in the library
   * - 18, 8, 7, 9
     - the same engine compiled once in ``yggdrasil::database`` (133 definitions in ``src/database``),
       ``QueryRepository`` and ``RelationRepository`` constructors and destructors out of class, their symbol storage
       instantiated in the library with extern lists in the main headers, ``Builder<Relation>`` moves and destructor out
       of class
     - 36 database TUs: max 2.41 GB to 1.23 GB, above 1 GiB 8 to 3, summed 29.8 GB to 25.1 GB, wall 371 s to 246 s; the
       library adds 26 sources (12.7 GB, max 0.88 GB), and test builds a second, instrumented copy for the two
       work-counting tests (another 12.7 GB)
   * - 7
     - 28 non-template member functions of 8 lines or more (search, generic join, plans, cost model) defined out of
       class in the library; codecs and row accessors stay inline for the hot paths
     - database TUs summed 25.1 GB to 24.6 GB, max 1.23 GB to 1.15 GB, but 7 more library sources at about 0.5 GB each:
       library 12.7 GB to 16.3 GB
   * - 11
     - the 33 ``yggdrasil::database`` sources compiled as 5 unity batches of 8
     - library 16.3 GB to 3.8 GB, 140 s to 39 s, heaviest 1.0 GB; with the previous rows the whole yggdrasil build goes
       from 61.8 GB summed, max 2.41 GB, 9 TUs above 1 GiB, 67 s at -j16 to 59.7 GB, 1.15 GB, 2, 45 s
   * - 8
     - the shared ``yggdrasil::database`` library compiled with ``-fno-semantic-interposition``
     - incremental distance with dense ties 5.5 µs (header-only) to 12.1 µs (library) back to 4.7 µs: without it,
       ``successor_distance``, ``contains_edge`` and the work counters were PLT calls inside the library
   * - 20
     - yggdrasil ``BuilderStorage`` keeps one pool per type in flat bases (reversed) instead of
       ``std::tuple<UniqueObjectPool<Data<Ts>>...>``; the first version listed the bases in type order and crashed a
       loki test with ``free(): invalid pointer`` at destruction
     - summed memory tyr 141.1 GB to 138.7 GB (above 1 GiB 30 to 28), runir 143.8 GB to 142.3 GB, loki and yggdrasil
       -0.3%; peak at -j32 tyr 37.5 GB to 35.6 GB, runir 67.3 GB to 64.0 GB; CPU +2 to +3% in tyr and runir in two runs
   * - 20
     - records return their fields from a static ``cista_members()`` as ``ygg::Members<&Data::index, ...>`` instead of
       ``std::tie`` (254 classes in the four repositories; four tyr rule class templates keep ``cista_members()``); the
       cista fork folds over the pointers in ``for_each_field`` and ``for_each_ptr_field`` and builds a tuple only in
       ``to_tuple``; same type hash
     - summed memory yggdrasil 52.6 GB to 50.6 GB, loki 65.5 GB to 60.6 GB (median 346 MB to 308 MB), tyr 138.7 GB to
       128.8 GB (median 509 MB to 480 MB, above 1 GiB 28 to 21, max 1.51 GB to 1.42 GB), runir 142.3 GB to 129.1 GB
       (median 541 MB to 507 MB, above 1 GiB 47 to 41); CPU -4 to -12%; peak at -j32 loki 16.6 GB to 14.4 GB, tyr 35.6
       GB to 32.3 GB; one TU +33 MB
   * - 19
     - tyr planning and datalog ``repository.hpp`` without ``prepare_for_insert`` and ``insert``: both move to a new
       ``interning.hpp`` with the canonicalization they need (71 MB of ``repository.hpp``'s 351 MB on its own), included
       by the 36 tyr sources, headers and tests and the one runir test that intern; ``ygg::formalism::insert`` requires
       the hook, so a missing include fails to compile
     - summed memory tyr 128.8 GB to 123.5 GB (median 479 MB to 438 MB, above 1 GiB 21 to 18), runir 129.1 GB to 127.1
       GB (median 507 MB to 490 MB); one TU +27 MB
   * - 14
     - cista ``type_at_index`` in constant depth (``__type_pack_element``, with a flat fallback) instead of a linear
       recursion, used once per case by ``variant::apply``
     - no change in any repository (-0.1% to +0.1%); clang traces had already put it at about 1% of runir's front end;
       reverted
   * - 11
     - runir DL grammar ``parser_def.hpp`` defined the Spirit rules of all three families and both dialects in every
       instantiation source, each of which instantiates one family; a probe without any instantiation cost 1.82 GB. Each
       source now defines its family (``RUNIR_DL_GRAMMAR_PARSER_BASE``, ``_EXT``, ``_UNS``) before the include.
       Splitting by dialect instead did not help: the two halves cost 2.62 GB and 2.51 GB against 2.69 GB merged
     - base 2.40 GB to 1.68 GB, ext 2.57 GB to 1.83 GB, uns 2.69 GB to 1.94 GB, 34-38 s to 15-18 s each; runir summed
       127.1 GB to 124.9 GB, max 2.68 GB to 2.21 GB, peak at -j32 60.9 GB to 56.2 GB
   * - 11
     - runir ``evaluation_ext.cpp``, ``evaluation_uns.cpp`` and ``ps/ext/program_executor.cpp`` split into ground and
       lifted sources (probes: the direct evaluator and the incremental engine share most of their instantiations, a
       ground or lifted half does not)
     - halves 1.62-1.80 GB against 2.00-2.21 GB, runir max 2.21 GB to 1.94 GB, but summed 124.9 GB to 128.7 GB, CPU +3%,
       peak at -j32 56.2/62.9/62.9 GB to 69.3/66.5/62.7 GB in three runs each; reverted
   * - 11
     - tyr ``lmcut.cpp`` and ``rpg_{ff,add,max}.cpp`` split into ground and lifted sources, each including only its
       kind's RPG header (probes)
     - lmcut 1.35 GB to 1.06 + 1.25 GB, rpg_ff 1.25 GB to 0.99 + 1.17 GB: the lifted half keeps 90-95%, so the max drops
       about 0.1 GB for about 1 GB more summed memory; not applied
   * - 1, 7
     - yggdrasil ``GenericJoinPlan`` and ``DistancePlan`` in their own headers (``generic_join_plan.hpp``,
       ``distance_plan.hpp``) without the evaluators, ``GenericJoinPlan``'s constructor and ``matches`` in the library,
       ``must_pass_plan.hpp`` without the unused ``relation_view.hpp``; runir's query and numerical data headers include
       only the plans
     - ``generic_join.hpp`` alone 238 MB, ``plans.hpp`` 155 MB; runir summed 124.9 GB to 123.8 GB, CPU -2%; other
       repositories unchanged
   * - 18
     - runir: sketches and classifiers moved to the Ext DL constructor set (made the union of all three), a capability
       check per language in the shared AST translation, then the Base and Uns DL instantiations (evaluation, symbol
       storage, Spirit rules, AST parsers) and the Ext and Uns grammar and CNF storage deleted
     - runir summed 123.8 GB to 107.6 GB, CPU 22.1 to 18.6 min, wall 94 s to 69 s, peak at -j32 58.4 GB to 35.9 GB,
       largest link 2.31 GB to 1.18 GB
   * - 18, 4, 8
     - runir DL ``Family`` template parameter removed (scripted, 296 files)
     - first version 107.6 GB to 109.6 GB: generation grammar and CNF types took the union constructor set (their symbol
       storage sources +0.32 GB each), and the query translator, query construction and others became non-template code
       in headers; generation grammars back on the Base set 108.2 GB; translator and query construction defined in the
       library 108.1 GB, max 2.13 GB, peak at -j32 33.3 GB, wall 69 s; with the renames 108.1 GB, peak 30.0 GB
   * - 19, 20
     - yggdrasil ``IndexedHashSet`` and ``buffer::IndexedHashSet`` hold their ``SegmentedVector`` behind the lookup's
       pointer and read through ``detail::SegmentedRows``; ``SegmentedVector``'s segment table holds untyped pointers,
       so it is one type per segment layout instead of one ``std::array`` per element type
     - summed memory tyr 123.5 GB to 119.2 GB (median 437 MB to 409 MB, above 1 GiB 16 to 15), runir 107.9 GB to 105.0
       GB (median 426 MB to 403 MB), loki 60.5 GB to 60.0 GB; largest drops 0.07 GB (tyr) and 0.10 GB (runir); tyr A\*
       blind and FF on 27 HTG tasks, lifted and ground: identical expansions and costs, stable cases within 5%, peak RSS
       geomean 0.98 to 1.005
   * - 13
     - the runir build with its tests and pyrunir (255 TUs; GCC 13, Release, -j12) measured again after urd took over
       the containers, records and graphs, against the rows above
     - summed memory 381.4 GB, median 1236 MB, max 4.08 GB, CPU 79.5 min, wall 427 s, peak 38.4 GB; clang traces of the
       heaviest TUs put urd's own templates at 26% of their instantiation time and constant evaluation at 6%, most of it
       choosing containers (the rows below)
   * - 21, 22
     - urd ``spec``'s answers in one expansion instead of a recursion of about 20 steps per Store, each carrying the
       request's ``property_set``; the container scan (``serving_v``) keyed by the request's shape
       (``serving_for<Kind, Shape>``), so Stores over different element types share it
     - front end (-fsyntax-only, frequent collections): DL repository 9.6 s to 8.4 s and 1.86 GB to 1.62 GB, DL
       evaluation 25.2 s to 20.9 s, successor expander test 29.9 s to 25.9 s; with the next row, the runir build
       CPU 79.5 min to 70.8 min, summed memory 381.4 GB to 358.4 GB, max 4.08 GB to 3.92 GB, wall 427 s to 380 s
   * - 23
     - urd's ``resolution`` of a variant member builds each alternative of the ``std::variant`` of views by
       ``std::in_place_index`` instead of the converting constructor
     - 20 to 30 MB per TU; the variants' ``_Variadic_union`` constructors remain the largest standard library cost
       under urd (about 0.5 s of clang front end per heavy TU)
   * - 18, 20
     - urd ``Hash``, ``EqualTo`` and ``Less`` of a record fold over its identifying members (``members_hashable``,
       ``hash_members``, ``equal_members``, ``less_members``) instead of building the tuple ``identity()`` gives;
       ``identity_t`` names that tuple from the members' types, so naming it instantiates no function; same hashes and
       orders (urd's tests); the transparent overloads keep the tuple
     - front end -66 to -177 MB and -0.4 to -1.6 s per TU (DL repository 1.62 GB to 1.56 GB, successor expander test
       3.13 GB to 2.95 GB)
   * - 4, 8
     - runir ``is_complement_leaf`` (an inline non-template function visiting every query tag and constructor) and its
       visitor moved from ``translations/ygg_query.hpp`` into its only user, ``ygg_query.cpp``; the text of a DL
       constructor or query (``semantics::text``) compiled once in ``src/kr/dl/semantics/formatter.cpp``: formatting
       one formats its operands of every kind, which every TU that formatted a feature compiled
     - with the previous row, runir CPU 70.8 min to 65.6 min, summed memory 358.4 GB to 329.8 GB, max 3.92 GB to
       3.65 GB, median 1120 MB to 1020 MB, slowest TU 95 s to 63 s, wall 380 s to 356 s, peak 37.8 GB to 36.9 GB; tyr
       (only the urd rows) CPU 36.8 min to 32.2 min, summed 222.7 GB to 200.3 GB, median 874 MB to 780 MB, above
       1 GiB 97 to 66, wall 205 s to 181 s, peak 26.1 GB to 25.4 GB
   * - 9, 13
     - TUs that intern without the opt-in list of what they intern, found as weak ``intern`` definitions
       (``compile_cost weak``): runir CNF generation, query evaluation and successor expander tests, must-pass
       profile and the ps rule binding include their lists; tyr's RPG, static rule filter, literal decomposition, rule
       splitting and program sources and five tests include ``tyr/formalism/detail/repository_instantiations.hpp``
     - at -O3: CNF generation 61.8 s to 44.6 s and 3.06 GB to 2.57 GB, query evaluation test 64.4 s to 55.2 s, tyr
       static rule filter 21.2 s to 15.0 s and 1.22 GB to 0.97 GB, rule splitting 23.3 s to 16.6 s; the ps Ext program
       executor binding was unchanged and keeps no list
   * - 11
     - pyrunir's sources of one directory compiled as one TU (``brokkr_unity_directories``, ``RUNIR_UNITY_BUILD``) for
       the twelve directories whose merged source stays below the heaviest TU (merged probes: ``kr/ps/base/dl`` nine
       sources 15.5 GB summed, 3.62 GB merged; ``datasets`` 4.55 GB, 1.97 GB); runir's and tyr's type tests the same,
       each test file in a namespace of its own (``runir::tests::<path>``, ``tyr::tests::<path>``)
     - runir 256 TUs to 190, CPU 64.8 min to 56.1 min, summed memory 328.7 GB to 271.6 GB, wall 350 s to 305 s, max
       3.58 GB to 3.62 GB, peak 36.5/36.6 GB to 37.7/38.0 GB (two runs each); tyr 262 TUs to 224, CPU 31.4 min to
       28.2 min, summed 197.7 GB to 174.3 GB, wall 176 s to 161 s, peak 25.8 GB to 23.6 GB
   * - 11
     - tyr's library (``core``) batched in the 22 directories whose merged source stays below its heaviest TU
       (``planning/heuristics``: five sources 8.17 GB summed, 1.90 GB merged), none of them declaring a file-local
       function twice; ``formalism/planning`` and ``planning/lifted`` exceed the heaviest TU merged, ``analysis`` and
       ``planning/lifted/programs`` repeat file-local names
     - tyr 224 TUs to 160, CPU 28.2 min to 21.8 min, summed memory 174.3 GB to 128.0 GB, wall 161 s to 130 s, max
       2.12 GB, peak 23.6 GB to 23.9 GB; with the rows above, tyr CPU 36.8 min to 21.8 min, summed 222.7 GB to
       128.0 GB, wall 205 s to 130 s, peak 26.1 GB to 23.9 GB
   * - 11
     - pytyr batched: ``database/query`` and ``formalism/datalog`` whole, ``formalism`` and ``formalism/planning`` by at
       most 11 sources (``BATCH_SIZE``: 18 and 21 sources merge to 3.13 GB and 3.74 GB whole, above the 2.99 GB of the
       serialization binding); with the library batches above
     - tyr with pytyr: library 121 TUs to 57 (106.5 GB to 60.1 GB summed), pytyr 86 TUs to 29 (73.6 GB to 42.0 GB),
       CPU 27.8 min to 17.4 min, wall 158 s to 104 s, max 2.99 GB, but peak at -j12 25.3/25.5 GB to 27.6/27.6 GB;
       the job pool below brings the peak back down
   * - 11
     - tyr's ``analysis`` and ``planning/lifted/programs`` freed of repeated file-local names, then batched: the domain
       helpers both analyses copied moved to ``analysis/domain_sets.hpp``, each analysis's own steps into a namespace of
       its own; the applicability helpers of ``action.cpp`` and ``ground.cpp`` moved to ``planning/programs/common``,
       the per-program builders named after their program (``create_rpg_program``, ``create_ground_program``, ...);
       ``formalism/planning`` by at most 3 sources (``BATCH_SIZE``)
     - ``analysis`` 4.21 GB to 1.58 GB merged, ``planning/lifted/programs`` 5.86 GB to 1.72 GB; tyr 161 TUs to 148, CPU
       22.0 min to 20.2 min, summed 129.7 GB to 117.2 GB, max 2.12 GB, wall 127 s to 122 s, peak 23.8 GB to 24.5 GB;
       with the rows above, tyr CPU 36.8 min to 20.2 min, summed 222.7 GB to 117.2 GB, wall 205 s to 122 s, peak
       26.1 GB to 24.5 GB
   * - 11
     - the Python modules' TUs compiled at most 6 at once (``brokkr_limit_compile_jobs``,
       ``-DRUNIR_PYTHON_COMPILE_JOBS=6``, ``-DTYR_PYTHON_COMPILE_JOBS=6``; no cap by default): they are the heaviest
       batches, and the library's and tests' TUs take the free slots
     - runir peak at -j12 38.0/38.4 GB to 34.1/34.2 GB, wall 310 s to 312/308 s (4 at once: 385 s, 35.9 GB); tyr with
       pytyr 27.6/27.6 GB to 24.6/23.8 GB, wall 104 s to 114/115 s; with all rows above, tyr with pytyr CPU 27.7 min
       to 14.2 min, summed 180.0 GB to 91.3 GB, wall 158 s to 114 s, peak 25.4 GB to 24.2 GB; runir CPU 79.5 min to
       55.5 min, summed 381.4 GB to 271.6 GB, max 4.08 GB to 3.62 GB, wall 427 s to 308-314 s, peak 38.4 GB to
       34.1/34.2/37.0 GB in three runs (the third after reinstalling tyr)
   * - 11, 14
     - runir's library (``kr``) batched the same way: sixteen directories, then only the eleven light ones (merged
       below 2 GB)
     - sixteen: summed 271.6 GB to 254.0 GB, CPU -2.2 min, but peak 37.0/38.0 GB to 38.9/40.2 GB; eleven: summed
       -7.6 GB, wall unchanged, peak 38.9/38.3 GB; not applied: batches of 2.5 GB and more compile at once what ran
       apart, and runir's library holds the build's heaviest sources
   * - 11
     - pyrunir sources batched in name order, two or three per directory, and whole directories whose sources share
       little (``kr/dl/semantics`` 7.56 GB merged, ``kr/ps/ext`` 5.30 GB, ``serialization/kr/dl`` 4.74 GB)
     - batches of three: max 5.09 GB, peak 41.7 GB; of two: 43.0 GB (``query`` and ``records`` share about 1.2 GB of
       6.3 GB); not applied: a batch pays off only where its sources share their instantiations
   * - 14
     - urd ``IndexedSet``'s empty storage for reads (a function-local static) in a never-destroyed holder, after the
       weak-symbol scan found its destructor compiled in 136 of 255 runir TUs; runir and tyr against compiled fmt
       instead of ``FMT_HEADER_ONLY`` (fmt's formatting core is compiled in 81 runir TUs)
     - no change (at most 0.6 s and 20 MB per TU in either): code compiled in many TUs is not the cost where the front
       end decides; reverted, and fmt kept header-only
   * - 24
     - runir's query optimizer and query statistics collector: their entry points for a constructor of each category
       and a query of any kind as explicit specializations, defined with the non-template members (the maximal-query
       optimization, the rewrites of must-pass, distance and nonempty records) in ``src/kr/dl/optimization.cpp``; the
       syntactic complexity of a constructor or query of any kind the same, as plain overloads; the projection
       heuristic's ``abstract_edges`` (inline, non-template) moved to its source; clang traces of the 45 heaviest TUs
       found the optimizer's recursion in 14 of them (13.5 s of 35 s in the query binding)
     - runir summed memory 271.6 GB to 263.6 GB, CPU 55.5 to 53.3 min, slowest TU 76 s to 71 s, wall 314 s to 288 s,
       peak 34.1-37.0 GB to 32.5 GB; the optimizer's includers -0.3 to -1.0 GB each (its test 3.0 GB to 2.0 GB)
   * - 24
     - pyrunir's serialization: writing a constructor of each category or a query of any kind (``describe_fields``
       for yggdrasil's dictionary writer) declared beside the generic overloads and defined once in
       ``serialization/kr/dl/constructor.cpp``; before, the Boolean serializer wrote the concept, role, numerical and
       query records too
     - the eleven serialization TUs -0.2 to -0.6 GB each, summed 263.6 GB to 259.7 GB, wall 278 s, peak 33.6 GB
   * - 24, 5
     - tyr's public ``optimization.hpp`` without the planner (``details/optimization.hpp``: its normalizer's and
       planner's in-class members instantiate the operator builder in every includer); ``Evaluation`` and the
       ``detail::optimize`` declaration moved to the public header, the two tests of the planner's parts include them
     - runir's DL binding TUs -0.1 to -0.2 GB, summed 259.7 GB to 258.2 GB, peak 31.6 GB, wall 278 s; with all rows
       above, runir CPU 79.5 to 51.6 min, summed 381.4 GB to 258.2 GB, max 4.08 GB to 3.52 GB, wall 427 s to 278 s,
       peak 38.4 GB to 31.6 GB
   * - 4
     - tyr's ``FDRContext`` holds its builder by ``std::unique_ptr``, its destructor defined in the source: by value, the
       builder (a slot per record type of tyr's planning formalism) completed in every includer of the task headers;
       clang over the 88 tyr and runir headers that 30 or more runir TUs include found it (0.9 s of
       ``fdr_context.hpp``'s 2.8 s, 5.2 s to 4.3 s for ``planning/lifted/task.hpp``)
     - runir summed 258.2 GB to 247.6 GB, median 1216 MB to 1143 MB, max 3.52 GB to 3.41 GB, CPU 51.6 to 50.5 min, wall
       278 s to 270/272 s, peak 31.6 GB to 31.9/31.8 GB (two runs); tyr with pytyr summed 91.1 GB to 89.9 GB, max
       2.99 GB to 2.83 GB, wall 114 s to 112 s, peak 22.0 GB to 22.4 GB; with all rows above, runir CPU 79.5 to 50.5
       min, summed 381.4 GB to 247.6 GB, max 4.08 GB to 3.41 GB, wall 427 s to 270 s, peak 38.4 GB to 31.8 GB; tyr
       with pytyr CPU 27.7 to 13.9 min, summed 180.0 GB to 89.9 GB, wall 158 s to 112 s, peak 25.4 GB to 22.4 GB
   * - 14
     - precompiled headers (GCC, the headers 42 of 50 pyrunir TUs share); GCC's collector run more often
       (``--param ggc-min-expand``) on the query binding
     - precompiled: 33.7 s to 32.4 s, 3.42 GB to 3.44 GB (the headers parse in 5 s, the TU's instantiations dominate);
       collector at 50: -8% memory, +8% time, at 20: -14%, +34%; neither applied
   * - 21, 14
     - urd's facts of a role: the traits a kind asks of the role filtered once per kind and role
       (``asked_traits``), not checked again for every list of types that plays it
     - clang -5% on a TU that completes runir's DL repository, GCC unchanged (3.38 s to 3.37 s, same memory); reverted:
       GCC builds the libraries
   * - 14
     - runir compiled with clang 18 instead of GCC 13 (the same flags, LTO off; after rewriting one generic visitor
       lambda in ``ps/icp/dl/parser.cpp`` as a ``boost::get`` dispatch, on which clang 18 crashed), against tyr
       compiled with clang 18 too (against the GCC-built tyr the links fail); urd's resolution measured alone first:
       per Store GCC spends 0.8 MB choosing the container (most of it on the element types' traits, not on the size of
       ``property_set``: 32 categories instead of 64 change nothing, nor does ``-fconstexpr-cache-depth``), 0.4 MB
       completing it and 1.1 MB on the Store and its facets
     - runir: summed memory 247.6 GB to 193.6 GB, median 1143 MB to 894 MB, max 3.41 GB to 2.50 GB, CPU 50.6 to
       52.6 min, wall 270 s to 284 s, peak at -j12 31.8 GB to 21.8 GB; tyr: summed 113.9 GB to 90.5 GB, max 2.10 GB to
       1.60 GB, CPU 19.8 to 21.7 min, wall 117 s to 144 s, peak 23.7 GB to 17.9 GB; tests pass (27, 49) and run as fast
       (tyr's, one at a time, 196 s to 175 s; runir's 5.7 s to 6.0 s); not applied: a choice of toolchain, not of code
   * - 13, 14
     - where a Store's 2.15 MB (GCC, completing it) goes, over 120 Stores of sets, sequences and maps of distinct
       element types, each part switched off in turn in a copy of urd: the choice of the container, its completion,
       the facets' conditions and each facet
     - choosing 0.8 MB (the element types' traits), the container 0.4 MB, the facets' conditions 0.15 MB, the facets
       0.6 MB spread over about fifteen (at most 3 MB over 120 Stores for any one), the Store's own members the rest;
       constructing one adds 0.4 MB; no part to remove alone: only fewer Stores per TU, or a different design, would
       shrink it
