Schemas
=======

A schema fixes the exact form of a construct that recurs across the libraries, in every place it appears: its
definition, its view and its binding. Code either has that form or not, so a schema is decidable, and a new instance is
written by filling the schema in, not by copying a neighbor. They apply to every library of the chain and are
maintained only here.

Records
-------

A record is a type the libraries keep as flat byte buffers in a monotonically growing urd Store: a tag ``T``, its stored
form ``urd::data<T>``, its view ``urd::index_view<T, Context>``, and their Python classes. The three rules of records
take a record ``Atom`` of the component ``formalism`` of a library ``lib`` as their example; ``<Name>`` is the record's
name in CamelCase (``Atom``).

Kept flat, a record of any size costs no allocation of its own: a reused builder holds its fields, vectors included,
while it is built, and interning writes them into the Store's buffers, which only grow. Creating dynamically sized
objects therefore allocates nothing once those buffers have grown; an index handed out stays valid, as no record is
ever removed.

.. raw:: html

   <figure class="record-diagram" style="margin: 1.5em 0; padding: 1em 1em 0.6em; text-align: center; border: 1px solid var(--color-background-border); border-radius: 0.4em;">
   <svg viewBox="0 0 860 640" width="100%" style="max-width: 860px; font-family: var(--font-stack--monospace); font-size: 13px;" role="img" aria-label="UML class diagram of a record, its Store, its index and its view">
     <defs>
       <marker id="uml-open" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10" orient="auto">
         <path d="M0,0 L11,6 L0,12" fill="none" stroke="currentColor" stroke-width="1.5"/>
       </marker>
     </defs>
     <g fill="none" stroke="currentColor" stroke-width="1.4">
       <rect x="500" y="20" width="340" height="130"/>
       <line x1="500" y1="70" x2="840" y2="70"/>
       <line x1="500" y1="100" x2="840" y2="100"/>
       <rect x="20" y="220" width="340" height="130"/>
       <line x1="20" y1="270" x2="360" y2="270"/>
       <line x1="20" y1="300" x2="360" y2="300"/>
       <rect x="500" y="220" width="340" height="114" style="stroke: var(--color-brand-primary);" stroke-width="2.2"/>
       <line x1="500" y1="254" x2="840" y2="254" style="stroke: var(--color-brand-primary);" stroke-width="2.2"/>
       <line x1="500" y1="304" x2="840" y2="304" style="stroke: var(--color-brand-primary);" stroke-width="2.2"/>
       <rect x="20" y="430" width="340" height="190"/>
       <line x1="20" y1="480" x2="360" y2="480"/>
       <line x1="20" y1="550" x2="360" y2="550"/>
       <rect x="500" y="460" width="340" height="94"/>
       <line x1="500" y1="494" x2="840" y2="494"/>
       <line x1="500" y1="524" x2="840" y2="524"/>
       <line x1="670.0" y1="220" x2="670.0" y2="164"/>
       <path d="M670.0,150 l-9,14 l18,0 z" fill="var(--color-background-primary)"/>
       <line x1="500" y1="277" x2="362" y2="277" marker-end="url(#uml-open)"/>
       <path d="M190.0,350 l-7,10 l7,10 l7,-10 z" fill="currentColor"/>
       <line x1="190.0" y1="370" x2="190.0" y2="430"/>
       <line x1="670.0" y1="334" x2="670.0" y2="458" marker-end="url(#uml-open)"/>
       <line x1="360" y1="507.0" x2="498" y2="507.0" marker-end="url(#uml-open)"/>
     </g>
     <g fill="currentColor" stroke="none">
       <text x="670.0" y="40" text-anchor="middle" font-style="italic" font-size="12">«mixin»</text>
       <text x="670.0" y="58" text-anchor="middle" font-weight="700">view_mixin&lt;Atom, V&gt;</text>
       <text x="510" y="120">+ get_predicate()</text>
       <text x="510" y="140">+ get_terms()</text>
       <text x="190.0" y="240" text-anchor="middle" font-style="italic" font-size="12">«pool»</text>
       <text x="190.0" y="258" text-anchor="middle" font-weight="700">Store</text>
       <text x="30" y="320">+ insert(data&lt;Atom&gt;) : index&lt;Atom&gt;</text>
       <text x="30" y="340">+ operator[](index&lt;Atom&gt;) : data&lt;Atom&gt;</text>
       <text x="670.0" y="242" text-anchor="middle" font-weight="700" style="fill: var(--color-brand-primary);">index_view&lt;Atom, Store&gt;</text>
       <text x="510" y="274">- index : index&lt;Atom&gt;</text>
       <text x="510" y="294">- context : const Store*</text>
       <text x="510" y="324">+ member&lt;&amp;F&gt;()</text>
       <text x="190.0" y="450" text-anchor="middle" font-style="italic" font-size="12">«record»</text>
       <text x="190.0" y="468" text-anchor="middle" font-weight="700">data&lt;Atom&gt;</text>
       <text x="30" y="500">+ index : index&lt;Atom&gt;</text>
       <text x="30" y="520">+ predicate : index&lt;Predicate&gt;</text>
       <text x="30" y="540">+ terms : flat_vector&lt;index&lt;Term&gt;&gt;</text>
       <text x="30" y="570">+ fields()</text>
       <text x="30" y="590">+ identifying_members()</text>
       <text x="30" y="610">+ cista_members()</text>
       <text x="670.0" y="482" text-anchor="middle" font-weight="700">index&lt;Atom&gt;</text>
       <text x="510" y="514">+ value : uint32</text>
       <text x="430.0" y="269" text-anchor="middle" font-size="12">context</text>
       <text x="200.0" y="422" font-size="12">0..*</text>
       <text x="678.0" y="401.0" font-size="12">index</text>
       <text x="430.0" y="499.0" text-anchor="middle" font-size="12">index</text>
     </g>
   </svg>
   <figcaption>Running example: the record <code>Atom</code> in UML: the Store owns its records and returns their indices;
   a view holds an index and the Store (its context) and inherits the field getters of its mixin.</figcaption>
   </figure>

A value that has no Store of its own, held in records or computed where it is read (a column's label and type, a fact
of a state), is no record: it is a plain struct, copyable, with ``cista_members()`` and ``identifying_members()`` and
compared by them (``urd::compared_by_identity``), as ``ygg::ColumnLayout``. Its views read it as their record type all
the same (``urd::borrowed_view<T, C, Value>``).

- .. rule:: schema-record-data
  .. rule:: S1

  :ruleid:`S1` :decidable:`decidable`
  **A record is** ``urd::data<T>``, **with an index, its fields and nothing else.**

  :Name: ``schema-record-data``
  :Check: ``python -m pybrokkr.rules S1`` (with the compile database of a configured build)

  The tag ``T`` is an empty struct
  (``struct Atom {};``, or a template of tags, ``template<FactKind F> struct Atom {};``). Each tag has one
  specialization ``data<T>``, or a family of tags one partial specialization per member (one for each ``F`` of
  ``Atom<F>``). The rule is about the specialization only; where it is written, what its header includes and what else
  the header holds are the :doc:`include_rules` and :doc:`directory_layout`'s.

  Each specialization has, in this order:

  #. ``urd::index<T> index;``, where the record has an index: the index its Store gives it when it interns the record,
     empty until then. Whether it has one is its semantics, not its schema: a record that is interned has one, a value
     held in other records (a fact of a state) has none;
  #. the fields, data members of any type that urd can store as bytes;
  #. ``data() = default;`` and the constructor from the fields in order, which leaves ``index`` empty: with no fields,
     that constructor is ``data()`` itself;
  #. either the copy deleted, the move and the destructor defaulted, the five as in the example: a copy that would cost
     the record's size is a compile error; or, for a record that is trivially copyable (indices and numbers, no memory
     of its own), its declaration that it is copied, which the compiler checks:

     .. code-block:: cpp

        static constexpr bool copyable() noexcept
        {
            static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
            return true;
        }

     urd rejects a copyable record that does not declare it;
  #. ``fields()``, which names each field once, under its member's name: ``urd::Fields<urd::field<"<member>",
     &data::<member>>...>``;
  #. ``identifying_members()``, which returns the members that make the record what it is, as ``urd::Members`` of some
     of its fields and its index, where it has one (``urd::members_of(fields())`` for all fields): which ones is the
     record's semantics, not its schema (a query's plan is stored but does not identify it);
  #. ``cista_members()``, which returns ``urd::Members<&data::index, &data::<member>...>``, the index (where it has one)
     and the fields in their order.

  A record declares no other member: no other function, alias, variable or ``static_assert`` (a contract over the
  record is checked next to its explicit instantiation, :rule:`T9`). A value that is derived from the fields is a
  function of the view, not a member.

  A family of tags has its records as partial specializations of this form: one per shape of its members whose fields
  differ (the lifted and the ground atoms), or one for the whole family where they do not. The record of the lifted
  atoms, for each fact kind ``F``:

  .. code-block:: cpp

     // include/lib/formalism/atom_data.hpp
     #include "lib/formalism/declarations.hpp"

     #include <urd/elements/flat.hpp>

     namespace urd
     {
     template<lib::formalism::FactKind F>
     struct data<lib::formalism::Atom<lib::LiftedTag, F>>
     {
         urd::index<lib::formalism::Atom<lib::LiftedTag, F>> index;
         urd::index<lib::formalism::Predicate<F>> predicate;
         urd::flat_vector<urd::index<lib::formalism::Term>> terms;

         data() = default;
         data(urd::index<lib::formalism::Predicate<F>> predicate_, urd::flat_vector<urd::index<lib::formalism::Term>> terms_) :
             index(), predicate(predicate_), terms(std::move(terms_)) {}
         data(const data& other) = delete;
         data& operator=(const data& other) = delete;
         data(data&& other) = default;
         data& operator=(data&& other) = default;
         ~data() = default;

         static constexpr auto fields() noexcept
         {
             return urd::Fields<urd::field<"predicate", &data::predicate>, urd::field<"terms", &data::terms>> {};
         }
         static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
         static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::predicate, &data::terms> {}; }
     };
     }

  The ground atoms' record, ``data<lib::formalism::Atom<lib::GroundTag, F>>``, has the same form with its own fields
  (its row); their views share one mixin or have one each (S2).

- .. rule:: schema-record-view
  .. rule:: S2

  :ruleid:`S2` :decidable:`decidable` **A record's view has one** ``get_<field>()`` **per field and may derive more from
  them, never reading** ``record()``.

  :Name: ``schema-record-view``
  :Check: ``python -m pybrokkr.rules S2`` (with the compile database of a configured build)

  A
  record's views (``urd::index_view``, and ``borrowed_view``, ``owning_view``, ``shared_view`` of its ``data<T>`` or
  ``builder<T>``) take their accessors from the specialization ``urd::view_mixin<T, V>`` of its tag, which the
  ``view_mixin<data<T>, V>`` and ``view_mixin<builder<T>, V>`` of its held forms inherit or specialize; each of them
  has, in this order:

  #. a private ``self()``, the view: ``static_cast<const V&>(*this)``;
  #. for each field of ``fields()``, in order, ``get_<field>()``, which returns
     ``self().template member<&urd::record_of<V>::<field>>()``: the field resolved through the view's context;
  #. any further member that is derived from the fields (whether it is ground, a filtered range), built on the
     getters above or on ``member<>``;
  #. ``functions()``, which lists, each under its Python name, every member of the mixin beyond ``self()`` and the field
     getters, and the free functions over the view that are offered with it (their first parameter the view):
     ``urd::Functions<urd::function<"<name>", &F>...>``. A member template whose template arguments its callers
     write (a getter templated on a tag, ``get<FluentTag>()``) is C++'s alone and not listed: Python has the plain
     getters it chooses among; one that deduces them from its parameters is listed by its instantiations, and overloads
     each with its type (``static_cast``). A mixin has no member that its ``functions()`` does not list: a member of a
     view is its interface. A free function is listed only where Python is to see it; a free helper of the derived
     functions (in ``detail``) is not listed and not bound.

  A mixin declares member functions alone, no data member, alias, nested type or using-declaration, and has no base
  but, a held form's, its tag's mixin: what a view offers is in its mixin, where the rule sees it. ``self()`` is its one
  private member; a helper its functions share is a free function in ``detail``.

  The view reads, a function derives: whether a derived function is a member or a free function is a matter of the C++
  call alone, as both are listed and bound alike. A function derives something new: none only forwards, its body a
  single ``return`` of a chain of calls without arguments that ends in a call of its own name (``get_name()`` as
  ``get_symbol().get_name()``) or is one call on the view itself (``get_state_repository()`` as ``context()``),
  written with ``this->``, in parentheses or through one local variable alike; its callers read that path. A free
  function that ``functions()`` lists is held to the same as a member: it does not only forward, and reads no
  ``record()`` of its view (its first parameter). One under a name of its own over a path (a ground atom's ``get_predicate()`` as
  ``get_row().get_relation()``) is a function of its own.

  A held form's mixin that inherits the tag's (``view_mixin<data<T>, V> : view_mixin<T, V>``) has its getters and adds
  what the held form has (an index, its repository).

  Nothing in a mixin calls ``record()``: the record's stored form bypasses the resolution ``member<>`` does and ties
  the view to how the record is laid out. Fields chosen by a tag (the literals of each kind) have their getters
  like any other; a getter templated on the tag that reads one of them is a derived member,
  after the field getters. A context that keeps its records in a layout of its own (a stored row: its values decoded
  from its pool) hands out no record but each field by the key (``urd::ReadsFieldsByKey``); ``member<>`` then reads values
  of it, never references into it, and the getters are the same.

  A family of tags (``template<TaskKind T, FactKind F> struct Atom``) has a mixin per record specialization, or one
  generic mixin that serves several of them: a partial specialization whose tag, over its own parameters, matches each
  record's tag (``view_mixin<Atom<T, F>, V>`` serves ``data<Atom<LiftedTag, F>>`` and ``data<Atom<GroundTag, F>>``). A
  record takes the mixin of its own template header where it has one, as C++ takes the more specialized; a record more
  general than every mixin of its tag has none. A mixin names its tag: one over a bare parameter (``view_mixin<T, V>
  requires ...``) serves no record. Every mixin, of one record or generic, has the order of the list above: ``self()``,
  then the field getters of every record it serves, each record's in its field order (a generic mixin's constrained by
  ``requires`` where only some records have them), then what it derives. The mixin of the lifted atoms (S1), with a
  derived function:

  .. code-block:: cpp

     // include/lib/formalism/atom_view.hpp
     #include "lib/formalism/atom_data.hpp"

     namespace urd
     {
     template<lib::formalism::FactKind F, typename V>
     struct view_mixin<lib::formalism::Atom<lib::LiftedTag, F>, V>
     {
     private:
         const V& self() const noexcept { return static_cast<const V&>(*this); }

     public:
         auto get_predicate() const noexcept { return self().template member<&urd::record_of<V>::predicate>(); }
         auto get_terms() const noexcept { return self().template member<&urd::record_of<V>::terms>(); }

         // Derived: whether none of its terms is a variable.
         bool is_ground() const noexcept
         {
             return std::ranges::none_of(get_terms(), [](auto term) { return term.is_variable(); });
         }

         static constexpr auto functions() noexcept { return urd::Functions<urd::function<"is_ground", &view_mixin::is_ground>> {}; }
     };
     }

  ``is_ground`` may as well be a free function over the view, listed the same way; only its pointer differs, and
  Python calls it as the same method, ``atom.is_ground()``. The free function is declared before the mixin, as
  ``functions()`` names it where the mixin is defined; its body is instantiated only for a view, so it may use the
  mixin's getters:

  .. code-block:: cpp

     // include/lib/formalism/atom_view.hpp
     namespace lib::formalism
     {
     template<typename V>
     bool is_ground(const V& atom) noexcept
     {
         return std::ranges::none_of(atom.get_terms(), [](auto term) { return term.is_variable(); });
     }
     }

     namespace urd
     {
     template<lib::formalism::FactKind F, typename V>
     struct view_mixin<lib::formalism::Atom<lib::LiftedTag, F>, V>
     {
         // self() and the field getters as above
         static constexpr auto functions() noexcept { return urd::Functions<urd::function<"is_ground", &lib::formalism::is_ground<V>>> {}; }
     };
     }

- .. rule:: schema-record-binding
  .. rule:: S3

  :ruleid:`S3` :decidable:`decidable`
  **A record is bound in Python by two calls,** ``urd::python::bind_data<T>(m)`` **and, for each of its views,**
  ``urd::python::bind_view<View>(m)``, **and by nothing else.**

  :Name: ``schema-record-binding``
  :Check: ``python -m pybrokkr.rules S3`` (with the compile database of a configured build)

  Nothing else is needed: urd binds a record's fields, its index, comparison, hashing, ``str`` and ``repr``, and its
  views' field getters and ``functions()`` (S2). They define the classes below, named from the record's
  name ``<Name>``, ``urd::name<T>()``: its tag's ``static constexpr std::string_view name``, followed by the names of
  its template arguments (``Condition<AndTag>`` is ``ConditionAnd``), so that each tag declares its name and no binding
  names a record or a field by hand; each call returns the class it defines. ``bind_view`` binds a record's view and a
  builder's view alike (a view of ``builder<T>``, whose ``fields()`` name the fields of ``data<T>``, is
  ``<Name>Builder``):

  .. list-table::
     :header-rows: 1
     :widths: 22 78

     * - Class
       - Members
     * - ``<Name>Index``
       - ``bind_data``, where the record holds an ``urd::index<T> index``: ``value``, ``is_none()``, ``int()``,
         comparison and hashing; a view that gives this index converts to it wherever an index is expected
     * - ``<Name>Data``
       - ``bind_data``, ``urd::data<T>``: an ``__init__`` from the fields in order, each field read and written under
         its name (flat containers as Python lists and values), comparison by the identifying members, ``str`` and
         ``repr`` by its ``fmt::formatter``
     * - ``<Name>``
       - ``bind_view``, the view: each ``get_<field>()`` of S2 (of its record's fields), comparison and hashing by its
         identity, ``str`` and ``repr`` by its ``fmt::formatter``, ``context()`` (its context, referred to, not
         copied), ``index()`` where it names its index, and the entries of ``functions()``

  urd writes every value that declares its fields (``fields()``), and a view of a record, with fmt as ``<Name>(``,
  then each field on a line of its own, ``<field>=<value>``, then ``)`` (``urd/format.hpp``): a record and a builder
  under the name of their tag, any other value under its own. A library that writes one otherwise, as PDDL for
  instance, specializes ``fmt::formatter`` for it.

  Each entry of a mixin's ``functions()``, a member or a free function over the view, becomes a method of the view's
  class under its listed name: what a view offers in Python is decided where the view is, by ``fields()`` and
  ``functions()``, never by a ``.def`` in a binding, on a class these calls return however it is reached (chained, held
  in a variable, returned by a helper). A function whose sole parameter is a view is a function of that view: it is
  listed in the view's ``functions()``, not bound with ``m.def``. One that takes more (options, a context, limits) is
  an algorithm over the view, bound with ``m.def`` with its keywords and defaults. A free function that is no function of a view (a parser, a search)
  is bound with ``m.def``; a binding may use helpers of its own made of these calls. Binding code is every tracked
  file that binds with nanobind: ``python/src``, a library's ``include/<lib>/python``, a test's module. A test's own
  records (outside ``include/``) are not bound, nor those of a library without bindings of its own (``python/src``).

  .. code-block:: cpp

     // python/src/pylib/formalism/atom.cpp
     urd::python::bind_data<lib::formalism::Atom>(m);
     urd::python::bind_view<lib::formalism::AtomView>(m);  // get_predicate, get_terms and functions(): is_ground

Values
------

A value is a plain struct of fields that no Store holds as a record: a key, a layout, a handle. It has no tag, no index
and no view, and is copied like any C++ value.

- .. rule:: schema-value
  .. rule:: S4

  :ruleid:`S4` :decidable:`decidable`
  **A value declares** ``name``, ``fields()`` **and** ``identifying_members()``, **and is bound in Python by**
  ``urd::python::bind_value<T>(m)`` **alone.**

  :Name: ``schema-value``
  :Check: ``python -m pybrokkr.rules S4`` (with the compile database of a configured build)

  Every struct or class template with a static ``fields()`` that is no record is a value, nested in a class or not.
  ``fields()`` lists its data members as a record's does, each once under its name and in order,
  ``identifying_members()`` those it is compared and hashed by, and ``static constexpr std::string_view name`` the name
  it is written and bound under. A value a record stores also declares ``cista_members()``, which cista requires there, so the
  build checks it. ``bind_value`` binds its constructor from its fields, each field read and written under its name,
  comparison by its identifying members, and ``str`` and ``repr`` by urd's formatter; a library's value (under
  ``include/``) is bound where the library has bindings (``python/src``), and a class of it bound by hand (``nb::class_<T>``), or a ``.def`` on the class
  ``bind_value`` returns, is a finding.

  .. code-block:: cpp

     // include/lib/formalism/row_index.hpp
     template<typename F>
     struct RowIndex
     {
         static constexpr std::string_view name = "RowIndex";

         urd::index<F> relation;
         urd::index<Row<F>> row;

         static constexpr auto fields() noexcept { return urd::Fields<urd::field<"relation", &RowIndex::relation>, urd::field<"row", &RowIndex::row>> {}; }
         static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
     };

     // python/src/pylib/formalism/row_index.cpp
     urd::python::bind_value<lib::formalism::RowIndex<lib::formalism::Predicate>>(m);

Status
------

``python -m pybrokkr.rules S`` checks the four rules on every tracked file, tests included; what it reports is where a
library does not follow them yet. A file it cannot parse is a finding, not a skip.
