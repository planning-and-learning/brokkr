Schemas
=======

A schema fixes the exact form of a construct that recurs across the libraries, in every place it appears: its
definition, its view and its binding. Code either has that form or not, so a schema is decidable, and a new instance is
written by filling the schema in, not by copying a neighbor. They apply to every library of the chain and are
maintained only here.

Records
-------

A record is a type the libraries keep in a urd Store: a tag ``T``, its stored form ``urd::data<T>``, its view
``urd::index_view<T, Context>``, and their Python classes. The three rules below take a record ``Atom`` of the
component ``formalism`` of a library ``lib`` as their example; ``<name>`` is the record's name in snake_case
(``atom``), ``<Name>`` in CamelCase (``Atom``).

A value that has no Store of its own, held in records or computed where it is read (a column's label and type, a fact
of a state), is no record: it is a plain struct, copyable, with ``cista_members()`` and ``identifying_members()`` and
compared by them (``urd::compared_by_identity``), as ``ygg::ColumnLayout``. Its views read it as their record type all
the same (``urd::borrowed_view<T, C, Value>``).

- .. rule:: schema-record-data
  .. rule:: S1

  :ruleid:`S1` :decidable:`decidable`
  **A record is** ``urd::data<T>``, **with an index, its fields and nothing else.** The tag ``T`` is an empty struct
  (``struct Atom {};``, or a template of tags, ``template<FactKind F> struct Atom {};``). Each tag has one
  specialization ``data<T>``, or a family of tags one partial specialization per member (one for each ``F`` of
  ``Atom<F>``). The rule is about the specialization only; where it is written, what its header includes and what else
  the header holds are the :doc:`include_rules` and :doc:`directory_layout`'s.

  Each specialization has, in this order:

  #. ``urd::index<T> index;``, where the record has an index: the index its Store gives it when it interns the record,
     empty until then. Whether it has one is its semantics, not its schema: a record that is interned has one (the
     compiler checks it where interning writes it), a value held in other records (a fact of a state) has none;
  #. the fields, data members of any type: whether a type can be stored as bytes, the compiler checks where urd stores
     the record (cista serializes each member);
  #. ``data() = default;`` and one constructor that takes the fields in order and leaves ``index`` empty (a record
     without fields has ``data() = default;`` alone);
  #. either the copy deleted, the move and the destructor defaulted, the five as in the example: a copy that would cost
     the record's size is a compile error; or, for a record that is trivially copyable (indices and numbers, no memory
     of its own), its declaration that it is copied, which the compiler checks:

     .. code-block:: cpp

        static constexpr bool copyable() noexcept
        {
            static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
            return true;
        }

     urd rejects a copyable record that does not declare it, and evaluates it where it stores the record. A Store
     interns a record from ``const T&`` and leaves it as it was (the arena serializes it, a Store of copyable records
     copies it), or takes it over from ``T&&``; a copy of a move-only record is built from its fields;
  #. ``fields()``, which names each field once, under its member's name: ``urd::Fields<urd::field<"<member>",
     &data::<member>>...>``;
  #. ``identifying_members()``, which returns the members that make the record what it is, as ``urd::Members`` of some
     of its fields and its index, where it has one (``urd::members_of(fields())`` for all fields): which ones is the
     record's semantics, not its schema (a query's plan is stored but does not identify it; a registered state is its
     index, as its repository has deduplicated it by its contents);
  #. ``cista_members()``, which returns ``urd::Members<&data::index, &data::<member>...>``, the index (where it has
     one) and the fields in their order.

  A record declares no other member: no other function, alias, variable or ``static_assert`` (a contract over the
  record is checked next to its explicit instantiation, :rule:`T9`). A value that is derived from the fields is a
  function of the view, not a member.

  .. code-block:: cpp

     // include/lib/formalism/atom_data.hpp
     #include "lib/formalism/declarations.hpp"

     #include <urd/elements/flat.hpp>

     namespace urd
     {
     template<>
     struct data<lib::formalism::Atom>
     {
         urd::index<lib::formalism::Atom> index;
         urd::index<lib::formalism::Predicate> predicate;
         urd::flat_vector<urd::index<lib::formalism::Object>> objects;

         data() = default;
         data(urd::index<lib::formalism::Predicate> predicate_, urd::flat_vector<urd::index<lib::formalism::Object>> objects_) :
             index(), predicate(predicate_), objects(std::move(objects_)) {}
         data(const data& other) = delete;
         data& operator=(const data& other) = delete;
         data(data&& other) = default;
         data& operator=(data&& other) = default;
         ~data() = default;

         static constexpr auto fields() noexcept
         {
             return urd::Fields<urd::field<"predicate", &data::predicate>, urd::field<"objects", &data::objects>> {};
         }
         static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
         static constexpr auto cista_members() noexcept { return urd::Members<&data::index, &data::predicate, &data::objects> {}; }
     };
     }

  :Name: ``schema-record-data``
  :Check: ``python -m pybrokkr.rules S1`` (with the compile database of a configured build)

- .. rule:: schema-record-view
  .. rule:: S2

  :ruleid:`S2` :decidable:`decidable`
  **A record's view has one** ``get_<field>()`` **per field and may expose more derived from them, all of it read
  through** ``member<>``, **its own getters or its context by its** ``index()``, **never through** ``data()``. A
  record's views (``urd::index_view``, and ``borrowed_view``, ``owning_view``, ``shared_view`` of its ``data<T>`` or
  ``builder<T>``) take their accessors from the specialization ``urd::view_mixin<T, V>`` of its tag, which the
  ``view_mixin<data<T>, V>`` and ``view_mixin<builder<T>, V>`` of its held forms inherit or specialize; each of them
  has, in this order:

  #. a private ``self()``, the view: ``static_cast<const V&>(*this)``;
  #. for each field of ``fields()``, in order, ``get_<field>()``, which returns
     ``self().template member<&urd::record_of<V>::<field>>()``: the field resolved through the view's context;
  #. any further member that is derived from the fields (an arity, whether it is empty, a filtered range), built on the
     getters above or on ``member<>``.

  Nothing in a mixin calls ``data()``: the record's stored form bypasses the resolution ``member<>`` does and ties the
  view to how the record is laid out. A field chosen by a tag (the literals of a kind) is a member pointer chosen by
  the tag, declared once next to the record, and read through ``member<>`` as well. A record held in its context under
  a handle of several parts (a row: its pool and its position, ``urd::index_view<Row<F>, C, RowIndex<F>>``) is read
  through its context by the view's ``index()``, as its context hands it out (its values decoded).

  .. code-block:: cpp

     // include/lib/formalism/atom_view.hpp
     #include "lib/formalism/atom_data.hpp"

     namespace urd
     {
     template<typename V>
     struct view_mixin<lib::formalism::Atom, V>
     {
     private:
         const V& self() const noexcept { return static_cast<const V&>(*this); }

     public:
         auto get_predicate() const noexcept { return self().template member<&urd::record_of<V>::predicate>(); }
         auto get_objects() const noexcept { return self().template member<&urd::record_of<V>::objects>(); }
     };
     }

  :Name: ``schema-record-view``
  :Check: ``python -m pybrokkr.rules S2`` (with the compile database of a configured build)

- .. rule:: schema-record-binding
  .. rule:: S3

  :ruleid:`S3` :decidable:`decidable`
  **A record is bound in Python by two calls,** ``urd::python::bind_data<T>(m)`` **and, for each of its views,**
  ``urd::python::bind_view<View>(m)``, **and by nothing else.** They define the classes below, named from the record's
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
         identity, ``str`` and ``repr`` by its ``fmt::formatter``, and ``index()`` where it names its index

  urd writes a record and a view of it with fmt as ``<Name>(``, then each field on a line of its own,
  ``<field>=<value>``, then ``)`` (``urd/format.hpp``); a library that writes a record otherwise, as PDDL for
  instance, specializes ``fmt::formatter`` for its own record.

  What a view derives beyond its fields (S2) is added to the class ``bind_view`` returns, each with
  ``.def("<name>", f)`` where ``<name>`` is a string and ``f`` refers to the member function of that name:
  ``&View::<name>``, one overload of it picked by ``nb::overload_cast<...>(&View::<name>)`` or a ``static_cast``
  (several overloads are several ``.def`` under the one name), or a member template given its tags,
  ``&View::template get_literals<FluentTag>``, whose name puts the tags' names after ``get_``:
  ``get_fluent_literals``. No lambda, no free function, no other name: the Python class mirrors the C++ view. A free
  function over the view is bound with ``m.def``. No binding defines a class of a record's data or view by hand
  (``nb::class_<urd::data<T>>``, ``nb::class_`` of its view): the Python names are the C++ names, ``get_<field>`` and
  the fields' names, in every library alike.

  .. code-block:: cpp

     // python/src/pylib/formalism/atom.cpp
     urd::python::bind_data<lib::formalism::Atom>(m);
     urd::python::bind_view<lib::formalism::AtomView>(m).def("get_arity", &lib::formalism::AtomView::get_arity);

  :Name: ``schema-record-binding``
  :Check: ``python -m pybrokkr.rules S3`` (with the compile database of a configured build)

Status
------

``python -m pybrokkr.rules S`` checks the three rules: S1 and S2 on every tracked header and source that defines a
``urd::data`` or ``urd::view_mixin`` specialization, tests included, S3 on the binding sources under ``python/src``,
each file parsed by libclang (a header as a translation unit that includes it alone, a source with its own compile
command, or that of the unity source that includes it); what it reports is where a library does not follow them yet. A
file that does not parse, or a source with no compile command, is a finding, not a skip: what it holds is not known.
