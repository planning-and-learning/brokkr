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
   <svg viewBox="0 0 1260 650" width="100%" style="max-width: 1260px; font-family: var(--font-stack--monospace); font-size: 13px;" role="img" aria-label="UML class diagram of a record, its Store, its index, its views, its builder and the borrowed view of a builder or a record">
     <defs>
       <marker id="uml-open" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10" orient="auto">
         <path d="M0,0 L11,6 L0,12" fill="none" stroke="currentColor" stroke-width="1.5"/>
       </marker>
     </defs>
     <g fill="none" stroke="currentColor" stroke-width="1.4">
       <rect x="460" y="20" width="340" height="130"/>
       <line x1="460" y1="70" x2="800" y2="70"/>
       <line x1="460" y1="100" x2="800" y2="100"/>
       <rect x="460" y="220" width="340" height="130"/>
       <line x1="460" y1="270" x2="800" y2="270"/>
       <line x1="460" y1="300" x2="800" y2="300"/>
       <rect x="460" y="430" width="340" height="190"/>
       <line x1="460" y1="480" x2="800" y2="480"/>
       <line x1="460" y1="550" x2="800" y2="550"/>
       <rect x="900" y="220" width="340" height="114" style="stroke: var(--color-brand-primary);" stroke-width="2.2"/>
       <line x1="900" y1="254" x2="1240" y2="254" style="stroke: var(--color-brand-primary);" stroke-width="2.2"/>
       <line x1="900" y1="304" x2="1240" y2="304" style="stroke: var(--color-brand-primary);" stroke-width="2.2"/>
       <rect x="900" y="460" width="340" height="94"/>
       <line x1="900" y1="494" x2="1240" y2="494"/>
       <line x1="900" y1="524" x2="1240" y2="524"/>
       <rect x="20" y="220" width="340" height="114"/>
       <line x1="20" y1="254" x2="360" y2="254"/>
       <line x1="20" y1="304" x2="360" y2="304"/>
       <rect x="20" y="430" width="340" height="190"/>
       <line x1="20" y1="480" x2="360" y2="480"/>
       <line x1="20" y1="550" x2="360" y2="550"/>
       <polyline points="190,220 190,85 446,85"/>
       <path d="M460,85 l-14,-9 l0,18 z" fill="var(--color-background-primary)"/>
       <polyline points="1070,220 1070,85 814,85"/>
       <path d="M800,85 l14,-9 l0,18 z" fill="var(--color-background-primary)"/>
       <line x1="360" y1="285" x2="458" y2="285" marker-end="url(#uml-open)"/>
       <line x1="900" y1="285" x2="802" y2="285" marker-end="url(#uml-open)"/>
       <path d="M630,350 l-7,10 l7,10 l7,-10 z" fill="currentColor"/>
       <line x1="630" y1="370" x2="630" y2="430"/>
       <line x1="190" y1="334" x2="190" y2="428" marker-end="url(#uml-open)"/>
       <line x1="1070" y1="334" x2="1070" y2="458" marker-end="url(#uml-open)"/>
       <line x1="800" y1="507" x2="898" y2="507" marker-end="url(#uml-open)"/>
       <line x1="360" y1="525" x2="458" y2="525" stroke-dasharray="6 4" marker-end="url(#uml-open)"/>
       <line x1="360" y1="320" x2="458" y2="446" marker-end="url(#uml-open)"/>
     </g>
     <g fill="currentColor" stroke="none">
       <text x="630" y="40" text-anchor="middle" font-style="italic" font-size="12">«mixin»</text>
       <text x="630" y="58" text-anchor="middle" font-weight="700">view_mixin&lt;Atom, V&gt;</text>
       <text x="470" y="120">+ get_predicate()</text>
       <text x="470" y="140">+ get_terms()</text>
       <text x="630" y="240" text-anchor="middle" font-style="italic" font-size="12">«pool»</text>
       <text x="630" y="258" text-anchor="middle" font-weight="700">Store</text>
       <text x="470" y="320">+ insert(data&lt;Atom&gt;) : index&lt;Atom&gt;</text>
       <text x="470" y="340">+ operator[](index&lt;Atom&gt;) : data&lt;Atom&gt;</text>
       <text x="630" y="450" text-anchor="middle" font-style="italic" font-size="12">«record»</text>
       <text x="630" y="468" text-anchor="middle" font-weight="700">data&lt;Atom&gt;</text>
       <text x="470" y="500">+ index : index&lt;Atom&gt;</text>
       <text x="470" y="520">+ predicate : index&lt;Predicate&gt;</text>
       <text x="470" y="540">+ terms : flat_vector&lt;index&lt;Term&gt;&gt;</text>
       <text x="470" y="570">+ fields()</text>
       <text x="470" y="590">+ identifying_members()</text>
       <text x="470" y="610">+ cista_members()</text>
       <text x="1070" y="242" text-anchor="middle" font-weight="700" style="fill: var(--color-brand-primary);">index_view&lt;Atom, Store&gt;</text>
       <text x="910" y="274">- index : index&lt;Atom&gt;</text>
       <text x="910" y="294">- context : const Store*</text>
       <text x="910" y="324">+ member&lt;&amp;F&gt;()</text>
       <text x="1070" y="482" text-anchor="middle" font-weight="700">index&lt;Atom&gt;</text>
       <text x="910" y="514">+ value : uint32</text>
       <text x="190" y="242" text-anchor="middle" font-weight="700">borrowed_view&lt;Atom, Store, R&gt;</text>
       <text x="30" y="274">- record : const R*</text>
       <text x="30" y="294">- context : const Store*</text>
       <text x="30" y="324">+ member&lt;&amp;F&gt;()</text>
       <text x="190" y="450" text-anchor="middle" font-style="italic" font-size="12">«builder»</text>
       <text x="190" y="468" text-anchor="middle" font-weight="700">builder&lt;Atom, C&gt;</text>
       <text x="30" y="500">+ index : index&lt;Atom&gt;</text>
       <text x="30" y="520" font-size="12">+ predicate : built_t&lt;index&lt;Predicate&gt;, C&gt;</text>
       <text x="30" y="540" font-size="12">+ terms : built_t&lt;flat_vector&lt;index&lt;Term&gt;&gt;, C&gt;</text>
       <text x="30" y="570">+ fields()</text>
       <text x="30" y="590">+ identifying_members()</text>
       <text x="409" y="277" text-anchor="middle" font-size="12">context</text>
       <text x="851" y="277" text-anchor="middle" font-size="12">context</text>
       <text x="640" y="412" font-size="12">0..*</text>
       <text x="198" y="385" font-size="12">record (R = builder)</text>
       <text x="372" y="368" font-size="12">record</text>
       <text x="372" y="383" font-size="12">(R = data)</text>
       <text x="1078" y="400" font-size="12">index</text>
       <text x="849" y="499" text-anchor="middle" font-size="12">index</text>
       <text x="409" y="517" text-anchor="middle" font-size="11">«same fields»</text>
     </g>
   <figcaption>Running example: the record <code>Atom</code> in UML: the Store owns its records and returns their indices;
   a view holds an index and the Store (its context) and inherits the field getters of its mixin. Its builder has the
   record's fields, each in its built form (<code>built_t</code>, S2): an index a child (<code>child&lt;Predicate,
   C&gt;</code>: its index, or a handle that owns a builder of its own or a record not interned yet; no context), a
   flat vector a <code>std::vector</code> of children, each in its own form; it only mutates. A borrowed view reads a
   builder, or a record not in the Store (R = data), through the Store with the same mixin; a child reads through that
   view's context: an index as its index_view, a handle as its record's borrowed view.</figcaption>
   </figure>

A value that has no Store of its own, held in records or computed where it is read (a column's label and type, a fact
of a state, a row's key), is a record with no index: ``urd::data<T>`` all the same (``urd::data<ygg::ColumnLayout>``,
``urd::data<FDRFact<F>>``), by S1 to S4, read through its views as any record (``urd::borrowed_view<T, C>``); see
Values (S5).

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
  (its row); their views share one mixin or have one each (S3).

- .. rule:: schema-record-builder
  .. rule:: S2

  :ruleid:`S2` :decidable:`decidable`
  **A record's builder is** ``urd::builder<T, C>``, **with the record's index and fields, each in its built form, and
  functions that change it.**

  :Name: ``schema-record-builder``
  :Check: ``python -m pybrokkr.rules S2`` (with the compile database of a configured build)

  A record that is built before it is interned has a builder: a specialization ``urd::builder<T, C>`` of its tag, with
  the template header of its record and the context type ``C`` it is read through. ``C`` is a type only: no member
  holds a context. It names a built child's builder (``builder<U, C>``, so that a nested tree shares one ``C``), the
  context a specialization that needs one names (a stateful ``order_by``, below), and what the builder is interned into
  and read through (``BuilderStorage<C, ...>``, ``borrowed_view<T, C, builder<T, C>>``). Each specialization has, in
  this order:

  #. ``urd::index<T> index;``, where its record has one;
  #. for each field of ``data<T>``, in its order and under its name, ``urd::built_t<M, Context> <field>;``, where ``M``
     is the field's type as the record declares it and ``Context`` the repository that holds ``M``'s records (``C`` for
     the record's own). ``built_t`` gives the field's built form: an index of a record its child
     (``urd::child<T, Context>``: its key, or a handle that owns a builder of its own or a record not interned yet), a
     ``urd::data<T>`` its builder, urd's
     flat containers std's (a ``flat_vector`` a ``std::vector``, a ``flat_optional`` a ``std::optional``, ...), and
     anything else as it is;
  #. ``fields()``, which names each field as ``data<T>``'s does, by member pointers of the builder;
  #. ``identifying_members()``, as its record's (``urd::members_of(fields())``);
  #. public member functions that change it, none ``const`` and none ``static``: a builder is its record's mutable
     form, read through its view (``urd::borrowed_view<T, C, builder<T, C>>``) and that view's mixin as the record is
     (S3), so a public read on the builder would be a second place for it. Private member functions are helpers of
     their own, of any form: no reader reaches them;
  #. ``functions()``, where it has public member functions: each listed under its Python name, as a mixin lists its
     functions (``urd::function<"clear", &builder::clear>``), so that what a builder offers in Python is decided where
     it is (S4).

  A builder declares nothing else: no base, constructor, alias, variable, friend, nor a member that refers to its
  context. It is made before any repository is known (a builder storage hands it out empty and reuses it, Python makes
  one from its fields) and is read through whichever context its view is made with: no child holds a context, a key is
  resolved through the view's, a handle reads as its record. A builder with a field that owns a child is move-only, as
  the child's built form owns its record by a unique handle (from a pool, or ``urd::make_owned`` on the heap);
  ``urd::clone`` copies it deeply.

  The builder of the lifted atoms:

  .. code-block:: cpp

     // include/lib/formalism/atom_builder.hpp
     #include "lib/formalism/atom_data.hpp"

     #include <urd/elements/children.hpp>

     namespace urd
     {
     template<lib::formalism::FactKind F, typename C>
     struct builder<lib::formalism::Atom<lib::LiftedTag, F>, C>
     {
         urd::index<lib::formalism::Atom<lib::LiftedTag, F>> index;
         urd::built_t<urd::index<lib::formalism::Predicate<F>>, C> predicate;
         urd::built_t<urd::flat_vector<urd::index<lib::formalism::Term>>, C> terms;

         static constexpr auto fields() noexcept
         {
             return urd::Fields<urd::field<"predicate", &builder::predicate>, urd::field<"terms", &builder::terms>> {};
         }
         static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }

         void clear() noexcept { terms.clear(); }

         static constexpr auto functions() noexcept { return urd::Functions<urd::function<"clear", &builder::clear>> {}; }
     };
     }

  .. note::

     A field of a type of the library's own whose form in a builder is not that type itself (a packed form, a list of
     keys a builder keeps sorted) gets its built form by a specialization of ``urd::built_form<M, C>`` beside the type,
     so that the builder's field is written ``built_t`` as any other. The specialization gives the form, ``type``, and,
     where it can be made from the record's member alone, ``from`` (no context: a key is a child as it is). A form
     whose order needs the context names it in a stateful ``order_by``, whose instance the builder's members give the
     Store (``urd::Store(order)``, as ``std::set(compare)``). A relation's rows, which its record holds as a list of row
     keys, ordered by their values, which a key names only in its repository:

     .. code-block:: cpp

        /// Tuple order of row children, each read through the context it holds (set by initialize).
        template<typename F, typename C>
        struct ygg::RowOrder
        {
            using is_transparent = void;
            const C* context = nullptr;
            template<typename L, typename R>
            bool operator()(const L& lhs, const R& rhs) const;
        };

        /// A relation's rows as its builder holds them: row children, in tuple order and unique (no from: row keys
        /// alone have no order).
        template<typename F, typename C>
        struct urd::built_form<urd::flat_vector<ygg::RowIndex<F>>, C>
        {
            using type = urd::Store<urd::multiset<urd::child<ygg::Row<F>, C, ygg::RowIndex<F>>>,
                                    urd::sorted, urd::unique, urd::order_by<ygg::RowOrder<F, C>>>;
        };

        // builder<Relation<F>, C>::initialize(repository, pool, columns):
        //     rows = urd::built_t<urd::flat_vector<ygg::RowIndex<F>>, C>(ygg::RowOrder<F, C> { &repository });

- .. rule:: schema-record-view
  .. rule:: S3

  :ruleid:`S3` :decidable:`decidable` **A record's view has one** ``get_<field>()`` **per field and may derive more from
  them, never reading** ``record()``.

  :Name: ``schema-record-view``
  :Check: ``python -m pybrokkr.rules S3`` (with the compile database of a configured build)

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
     getters, and the free functions of the view that are offered with it, whose sole parameter is the view (a member
     may take more: which column, which values; a free function that does is an algorithm over the view, bound with
     ``m.def``):
     ``urd::Functions<urd::function<"<name>", &F, urd::arg<"<parameter>">...>...>``, with an ``urd::arg`` per
     parameter beside the view, in order and under its C++ name, so that Python passes it by keyword too
     (``urd::function<"value", &view_mixin::value, urd::arg<"column">>``). A member template whose template arguments its callers
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

  .. note::

     A field of a type of the library's own (a key of a record that no ``urd::index`` names) tells urd how a view reads
     it and what it is written from, by a specialization of ``urd::resolution<M>`` beside the type: ``of``, the field
     resolved through the view's context, which its getter returns; ``stored``, the field written from what reads as it
     (the key itself, or a view of what it names). A row key:

     .. code-block:: cpp

        /// A row key held in a record resolves to its view, through its context (context.view(key)).
        template<typename F>
        struct urd::resolution<ygg::RowIndex<F>>
        {
            template<typename C>
            static auto of(ygg::RowIndex<F> key, const C& context) { return context.view(key); }

            /// Written from the key itself, or from a stored row's view (its index()).
            template<std::same_as<ygg::RowIndex<F>> R>
            static ygg::RowIndex<F> stored(const R& readout) noexcept { return readout; }

            template<ygg::StoredRowView<F> V>
            static ygg::RowIndex<F> stored(const V& view) noexcept { return view.index(); }
        };

- .. rule:: schema-record-binding
  .. rule:: S4

  :ruleid:`S4` :decidable:`decidable`
  **A record is bound in Python by** ``urd::python::bind_index<T>(m)`` **where it holds its index,**
  ``urd::python::bind_data<T>(m)``, ``urd::python::bind_builder<T, C>(m)`` **for its builder and**
  ``urd::python::bind_view<View>(m)`` **for each of its views, one class each, and by nothing else.**

  :Name: ``schema-record-binding``
  :Check: ``python -m pybrokkr.rules S4`` (with the compile database of a configured build)

  Nothing else is needed: urd binds a record's fields, its index, comparison, hashing, ``str`` and ``repr``, and its
  views' field getters and ``functions()`` (S3). They define the classes below, named from the record's
  name ``<Name>``, ``urd::name<T>()``: its tag's ``static constexpr std::string_view name``, as the tag declares it, so
  that no binding names a record or a field by hand; each call returns the class it defines. A tag of a family is named
  after its arguments where it says so (``urd::joined_name<"Condition", Tag::name>``: ``Condition<AndTag>`` is
  ``ConditionAnd``), as the records of one module need names of their own, and not where each is bound in a module of
  its own (``State<Kind>`` is ``State`` in ``pytyr.planning.ground`` and in ``pytyr.planning.lifted``). ``bind_view`` binds a record's view and a
  builder's view alike: a view that borrows its record is ``<Name>Borrowed``, one that owns it ``<Name>Owned``, one
  that shares it ``<Name>Shared``, and a view of a builder has ``Builder`` before these, so that the classes of one
  record in one module have names of their own: ``State``, ``StateBorrowed``, ``StateData``, ``StateBuilder``,
  ``StateBuilderBorrowed`` and ``StateBuilderShared``. A library binds every builder it defines (``include/``):

  .. list-table::
     :header-rows: 1
     :widths: 22 78

     * - Class
       - Members
     * - ``<Name>Index``
       - ``bind_index``, ``urd::index<T>``, before ``bind_data`` where the record holds an ``urd::index<T> index``
         (``bind_data`` throws where it is not bound yet), and for a tag of no record (a column, a slot): ``value``,
         ``is_none()``, ``int()``, comparison and hashing; a view that gives this index converts to it wherever an
         index is expected. An index is bound once, by whichever module binds it first; every other names that class.
         ``bind_index<K>`` of a key of a library's own (a type with ``fields()``, Values) binds the key under its name:
         an ``__init__`` from its fields, each field read and written, comparison, hashing, ``str`` and ``repr``
     * - ``<Name>Data``
       - ``bind_data``, ``urd::data<T>``: an ``__init__`` from the fields in order, each field read and written under
         its name (flat containers as Python lists and values), comparison by the identifying members, ``str`` and
         ``repr`` by its ``fmt::formatter``
     * - ``<Name>``
       - ``bind_view``, the view: each ``get_<field>()`` of S3 (of its record's fields), comparison and hashing by its
         identity, ``str`` and ``repr`` by its ``fmt::formatter``, ``context()`` (its context, referred to, not
         copied), ``index()`` where it names its index, and the entries of ``functions()``
     * - ``<Name>Builder``
       - ``bind_builder``, ``urd::builder<T, C>``: an ``__init__`` that takes each field by its name, every one
         optional (empty where it is not given), and ``set_<field>(value)`` for each field, neither with a context: a
         child takes its key (an index, or a view, which converts to it), a builder or a record of its kind (a copy,
         which the child owns), a list, optional or variant of these element by element, a value as nanobind casts
         it; the entries of its ``functions()`` (S2), its mutators (their reference arguments kept alive with it);
         and ``view(context)``, its view through a context (``<Name>BuilderBorrowed``), which every read goes
         through. A library's repository interns a builder with its children, built ones first
         (``Repository.insert(builder)``): a whole tree is written as one nested value and interned once

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
     urd::python::bind_index<lib::formalism::Atom>(m);
     urd::python::bind_data<lib::formalism::Atom>(m);
     urd::python::bind_builder<lib::formalism::Atom, lib::Repository>(m);  // set_predicate, set_terms, clear, view
     urd::python::bind_view<lib::formalism::AtomView>(m);  // get_predicate, get_terms and functions(): is_ground

Values
------

A value is a record no Store holds: ``urd::data<T>`` of a tag ``T``, with no index. A key (a row's), a layout (a
column's), a handle (a tree pool's): fields, compared, hashed, written and bound as a record is, by the same rules.
Builders and views exist to build and resolve children: a value that holds a child (an index of a record: a fact's
variable) is built by its builder (S2) and read through its view (S3), as a record; so is a value read through its
context, which says so by declaring a view mixin (a state's storage: its pool's handle names rows in the repository's
pools). A value with neither (no index, no record's index among its fields, no mixin: a column's label and type, a
pool's handle; ``urd::PlainValue``) is held, built and read as it is, with no builder, view or bound view of its own.

A key is no value: it names a record (``urd::index<T>``, a row's key ``ygg::RowIndex<F>``, a state's packed storage
``tyr::planning::PackedStorage<S>``) and reads as what it names, the view its context makes of it. A key of a
library's own is a plain struct of fields with ``identifying_members()``, a ``urd::resolution`` specialization (it reads
as what it names) and a ``fmt::formatter``; it is bound by ``urd::python::bind_index<K>(m)``, as an index is. A
builder holds a key as it is, unless its library gives the key's built form (``urd::built_form``): a packed storage is
built as its storage unpacked. Only its pool packs and unpacks it, so that form has no ``from()``, and nothing that
holds it is made from a record (``urd::made_from_record``): its builder's setter takes no record of its kind, only a
builder.

- .. rule:: schema-value
  .. rule:: S5

  :ruleid:`S5` :decidable:`decidable`
  **A type that declares** ``fields()`` **and** ``identifying_members()`` **is a** ``urd::data<T>``
  **specialization, or a key.**

  :Name: ``schema-value``
  :Check: ``python -m pybrokkr.rules S5`` (with the compile database of a configured build)

  Every struct or class template with a static ``fields()`` and ``identifying_members()`` is a record, one with an index
  held by a Store, one without a value, both following S1 to S4 (a value has no ``index``, so ``bind_index`` binds
  none); or a key, one ``urd::resolution`` reads (a specialization of it for the type, wherever it is written). A type with ``fields()`` alone (and ``name``) is printable, not a value: urd's formatter writes it, and nothing
  else is asked of it. A class with behaviour (private state, member functions) compared by ``identifying_members()``
  declares no ``fields()``; it is written by a ``fmt::formatter`` of its own.

  .. code-block:: cpp

     // include/lib/formalism/declarations.hpp
     template<typename F>
     struct RowIndex
     {
         static constexpr std::string_view name = urd::joined_name<"RowIndex", F::name>;
     };

     template<typename F>
     struct urd::data<lib::formalism::RowIndex<F>>
     {
         urd::index<F> relation;
         urd::index<lib::formalism::Row<F>> row;

         data() = default;
         data(urd::index<F> relation_, urd::index<lib::formalism::Row<F>> row_) : relation(relation_), row(row_) {}

         static constexpr bool copyable() noexcept
         {
             static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
             return true;
         }

         static constexpr auto fields() noexcept { return urd::Fields<urd::field<"relation", &data::relation>, urd::field<"row", &data::row>> {}; }
         static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
         static constexpr auto cista_members() noexcept { return urd::Members<&data::relation, &data::row> {}; }
     };

     // python/src/pylib/formalism/row_index.cpp
     urd::python::bind_data<lib::formalism::RowIndex<lib::formalism::Predicate>>(m);  // RowIndexPredicateData

Status
------

``python -m pybrokkr.rules S`` checks the five rules on every tracked file, tests included; what it reports is where a
library does not follow them yet. A file it cannot parse is a finding, not a skip.
