Schemas
=======

A schema fixes the exact form of a construct that recurs across the libraries, in every place it appears: its
definition, its view and its binding. Code either has that form or not, so a schema is decidable, and a new instance is
written by filling the schema in, not by copying a neighbor. They apply to every library of the chain and are
maintained only here.

Records
-------

A record is a type the libraries keep as flat byte buffers in a monotonically growing urd Store: a tag ``T``, its stored
form ``urd::data<T>``, its builder ``urd::builder<T, C>``, its views and their Python classes.

The examples use one library, ``lib``, with a component ``formalism`` and three records:

- ``Term``, an object or a variable;
- ``Predicate<F>``, a name and an arity, of a fact kind ``F`` (static or fluent);
- ``Atom<T, F>``, a predicate applied to terms, lifted (``T = LiftedTag``: its terms may be variables) or ground
  (``T = GroundTag``).

``<Name>`` is a record's name in CamelCase (``Atom``).

Kept flat, a record of any size costs no allocation of its own: a reused builder holds its fields, vectors included,
while it is built, and interning writes them into the Store's buffers, which only grow. Creating dynamically sized
objects therefore allocates nothing once those buffers have grown; an index handed out stays valid, as no record is
ever removed.

The record schema solves a problem that schema-driven data libraries such as `Protocol Buffers <https://protobuf.dev>`__
and `Cap'n Proto <https://capnproto.org>`__ also address: declare a structured type once, and get from that one
declaration how it is built, how it is read and how it reaches another language. Cap'n Proto comes closest. Its
generated code splits each struct into a Builder, which writes into arena segments, and a Reader, which reads the same
bytes in place, without a decoding step. urd's ``builder<T, C>`` and ``index_view<T, C>`` make the same split, and its
records are flat bytes as well. Protocol Buffers generates one message class that owns its fields and is encoded to and
decoded from a wire format.

The goal differs, and with it the design:

- **Deduplication instead of messages.** Both libraries build self-contained messages to exchange between programs: a
  message is a value, compared field by field, and neither keeps a store of distinct messages (Protocol Buffers'
  deterministic serialization is not canonical, so its bytes cannot serve as a key). A record lives in a Store that
  keeps each distinct record once and identifies it by a dense index: a builder interns its children first and brings
  its record into its domain's canonical form (sorted literals, say) before it is looked up, so that equal structures
  are one record; inserting an existing record returns its index, equality is comparing indices, and an index keys a
  table.
- **Typed references instead of embedded children.** A child of a message is embedded in it (Protocol Buffers copies
  submessages; a Cap'n Proto pointer stays within its message, and its builder cannot point twice at one object).
  Sharing a child would mean replacing it by an integer field, which the generated code neither types nor resolves. A
  child of a record is an ``index<T>`` of its own type, which its view resolves to the child's view, so records form one
  shared graph across the Store.
- **Reading through a context.** A Cap'n Proto Reader resolves pointers inside its own message. A view resolves its
  children through a context, the repository (S3), which can be layered over a frozen parent's (a Datalog program's
  rules refer to its planning task's atoms without copying them) or can nest the repositories its children live in.

.. raw:: html

   <figure class="record-diagram" style="margin: 1.5em 0; padding: 1em 1em 0.6em; text-align: center; border: 1px solid var(--color-background-border); border-radius: 0.4em;">
   <svg viewBox="0 0 1260 850" width="100%" style="max-width: 1260px; font-family: var(--font-stack--monospace); font-size: 13px;" role="img" aria-label="UML class diagram of a record, its Store, its index, its views, its builder, the Store of its builders and the borrowed view of a builder or a record">
     <defs>
       <marker id="uml-open" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="10" markerHeight="10" orient="auto">
         <path d="M0,0 L11,6 L0,12" fill="none" stroke="currentColor" stroke-width="1.5"/>
       </marker>
     </defs>
     <g fill="none" stroke="currentColor" stroke-width="1.4">
       <rect x="460" y="20" width="340" height="130"/>
       <line x1="460" y1="70" x2="800" y2="70"/>
       <line x1="460" y1="100" x2="800" y2="100"/>
       <rect x="460" y="220" width="340" height="150"/>
       <line x1="460" y1="270" x2="800" y2="270"/>
       <line x1="460" y1="320" x2="800" y2="320"/>
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
       <path d="M630,370 l-7,10 l7,10 l7,-10 z" fill="currentColor"/>
       <line x1="630" y1="390" x2="630" y2="430"/>
       <line x1="190" y1="334" x2="190" y2="428" marker-end="url(#uml-open)"/>
       <line x1="1070" y1="334" x2="1070" y2="458" marker-end="url(#uml-open)"/>
       <line x1="800" y1="507" x2="898" y2="507" marker-end="url(#uml-open)"/>
       <line x1="360" y1="525" x2="458" y2="525" stroke-dasharray="6 4" marker-end="url(#uml-open)"/>
       <line x1="360" y1="320" x2="458" y2="446" marker-end="url(#uml-open)"/>
       <rect x="20" y="700" width="340" height="120"/>
       <line x1="20" y1="750" x2="360" y2="750"/>
       <line x1="20" y1="780" x2="360" y2="780"/>
       <path d="M190,700 l-7,-10 l7,-10 l7,10 z" fill="currentColor"/>
       <line x1="190" y1="680" x2="190" y2="620"/>
     </g>
     <g fill="currentColor" stroke="none">
       <text x="630" y="40" text-anchor="middle" font-style="italic" font-size="12">«mixin»</text>
       <text x="630" y="58" text-anchor="middle" font-weight="700">view_mixin&lt;Atom, V&gt;</text>
       <text x="470" y="120">+ get_predicate()</text>
       <text x="470" y="140">+ get_terms()</text>
       <text x="630" y="240" text-anchor="middle" font-style="italic" font-size="12">«pool»</text>
       <text x="630" y="258" text-anchor="middle" font-weight="700">Store</text>
       <text x="470" y="290" font-size="12">pool&lt;data&lt;Atom&gt;, index&lt;Atom&gt;&gt;</text>
       <text x="470" y="310" font-size="12">{flat, stable_refs, layered}</text>
       <text x="470" y="340">+ insert(data&lt;Atom&gt;) : index&lt;Atom&gt;</text>
       <text x="470" y="360">+ operator[](index&lt;Atom&gt;) : stored_ref&lt;Atom&gt;</text>
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
       <text x="190" y="720" text-anchor="middle" font-style="italic" font-size="12">«slots»</text>
       <text x="190" y="738" text-anchor="middle" font-weight="700">Store</text>
       <text x="30" y="770" font-size="12">slots&lt;builder&lt;Atom, C&gt;&gt;</text>
       <text x="30" y="800" font-size="12">+ make_handle() : handle&lt;builder&lt;Atom, C&gt;&gt;</text>
       <text x="198" y="640" font-size="12">0..*</text>
     </g>
   </svg>
   <figcaption>The record <code>Atom</code> in UML. The Store keeps each record once and hands out its index; a view
   holds an index and the Store (its context) and inherits the field getters of its mixin. The builder has the record's
   fields, each in its built form (S2), and only mutates; builders are pooled in a Store of slots, so building allocates
   nothing once the slots have grown. A borrowed view reads a builder, or a record not in the Store, with the same
   mixin.</figcaption>
   </figure>

A repository reads a record by its index (``operator[]``, unchecked, and ``at``, checked), and inserts and finds a record
from its builder or its ``urd::data<T>``.

.. note::

   **Keys of several parts.** A record numbered within another (a row within its relation) is identified by a key of
   several parts, ``urd::key<Ts...>``, resolved in order, each part selecting the container the next is looked up in:
   ``urd::key<F, Row<F>>`` is a row's relation, then the row there. ``urd::index<T>`` is the key of one part, so every
   lookup, insertion and count takes a key, whatever its number of parts.

.. note::

   **The stored form.** A lookup hands a record out as ``urd::stored_ref<T>``, by value: by default a reference to the
   stored ``urd::data<T>``. A record kept in a representation of its own specializes the two together:
   ``urd::stored_ref_of<T>`` names what a lookup hands out, and ``urd::data<T>`` stays the owning form it is inserted
   and found from. A row is stored packed at its columns' widths: ``stored_ref_of<Row<F>>`` is ``PackedRow<F>``, a
   reader of its bits, and ``data<Row<F>>`` holds its relation and its values. The views read both through the same
   mixin (S3). This is the one customization point of how a record is stored.

- .. rule:: schema-record-data
  .. rule:: S1

  :ruleid:`S1` :decidable:`decidable`
  **A record is** ``urd::data<T>``, **with an index, its fields and nothing else.**

  :Name: ``schema-record-data``
  :Check: ``python -m pybrokkr.rules S1`` (with the compile database of a configured build)

  The tag ``T`` is an empty struct (``struct Term {};``), or a template of tags (``template<FactKind F> struct
  Predicate {};``). Each tag has one specialization ``data<T>``; a family of tags has one partial specialization per
  shape of its members whose fields differ (the lifted and the ground atoms), or one for the whole family.

  Each specialization has, in this order:

  #. ``urd::index<T> index;``, where the record has an index: the index its Store gives it, empty until then. A value
     held in other records has none (Values);
  #. the fields, data members of any type that urd can store as bytes;
  #. ``data() = default;`` and the constructor from the fields in order, which leaves ``index`` empty;
  #. either the copy deleted and the move and the destructor defaulted, as in the example, so that a copy that would
     cost the record's size is a compile error; or, for a trivially copyable record (indices and numbers only), its
     declaration that it is copied, which the compiler checks:

     .. code-block:: cpp

        static constexpr bool copyable() noexcept
        {
            static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
            return true;
        }

  #. ``fields()``, which names each field once, under its member's name: ``urd::Fields<urd::field<"<member>",
     &data::<member>>...>``;
  #. ``identifying_members()``, the members that make the record what it is: ``urd::members_of(fields())`` for all
     fields, or some of them where the record stores more than identifies it;
  #. ``cista_members()``: ``urd::Members<&data::index, &data::<member>...>``, the index and the fields in their order.

  A record declares nothing else: no other function, alias, variable or ``static_assert``. A value derived from the
  fields is a function of the view (S3), not a member. The lifted atoms' record:

  .. code-block:: cpp

     // include/lib/formalism/atom_data.hpp
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

- .. rule:: schema-record-builder
  .. rule:: S2

  :ruleid:`S2` :decidable:`decidable`
  **A record's builder is** ``urd::builder<T, C>``, **with the record's index and fields, each in its built form, and
  functions that change it.**

  :Name: ``schema-record-builder``
  :Check: ``python -m pybrokkr.rules S2`` (with the compile database of a configured build)

  A record that is built before it is interned has a builder: a specialization ``urd::builder<T, C>`` with the template
  header of its record and the type ``C`` of the context it is read through (a type only: no member holds a context).
  Each specialization has, in this order:

  #. ``urd::index<T> index;``, where its record has one;
  #. for each field of ``data<T>``, in its order and under its name, ``urd::built_t<M, Context> <field>;``, where ``M``
     is the field's type in the record and ``Context`` the repository that holds ``M``'s records (``C`` for the
     record's own). ``built_t`` gives the built form: an index becomes a child (its index, or a handle that owns a
     builder or a record not interned yet), a ``urd::data<T>`` its builder, urd's flat containers std's (a
     ``flat_vector`` a ``std::vector``), anything else stays as it is;
  #. ``fields()`` and ``identifying_members()``, as its record's, by member pointers of the builder;
  #. public member functions that change it, none ``const`` and none ``static``: a builder is read through its view
     (S3), so a public read on it would be a second place for it;
  #. ``functions()``, where it has public member functions, each listed under its Python name
     (``urd::function<"clear", &builder::clear>``), so that what a builder offers in Python is decided where it is
     (S4).

  A builder declares nothing else: no base, constructor, alias, variable, friend, nor a member that refers to its
  context. A builder whose child owns a record is move-only; ``urd::clone`` copies it deeply. The lifted atoms'
  builder:

  .. code-block:: cpp

     // include/lib/formalism/atom_builder.hpp
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

     **A built form of the library's own.** A field whose form in a builder is not its own type (a packed form, a list
     a builder keeps sorted) gets that form by a specialization ``urd::built_form<M, C>`` beside the type, so that the
     builder's field is still written ``built_t``. It gives ``type``, the form, and ``assign(value, into)``, where the
     form can be made from the record's member alone: written into the builder's own value, in place, so that nothing
     is allocated once its buffers have grown. A form whose order needs the context takes a stateful
     ``urd::order_by``, given to its Store as ``std::set`` takes its comparison: a relation's rows, kept sorted and
     unique by their values, which only the repository can read.

- .. rule:: schema-record-view
  .. rule:: S3

  :ruleid:`S3` :decidable:`decidable` **A record's view has one** ``get_<field>()`` **per field and may derive more from
  them, never reading** ``record()``.

  :Name: ``schema-record-view``
  :Check: ``python -m pybrokkr.rules S3`` (with the compile database of a configured build)

  A record's views (``urd::index_view``, and the borrowed, owning and shared views of its ``data<T>`` or
  ``builder<T, C>``) take their accessors from the specialization ``urd::view_mixin<T, V>`` of its tag. Each mixin has,
  in this order:

  #. a private ``self()``, the view: ``static_cast<const V&>(*this)``;
  #. for each field of ``fields()``, in order, ``get_<field>()``, which returns
     ``self().template member<&urd::record_of<V>::<field>>()``: the field resolved through the view's context;
  #. any further member derived from the fields (whether it is ground, a filtered range), built on the getters above;
  #. ``functions()``, which lists every member beyond ``self()`` and the field getters, and the free functions offered
     with the view, each under its Python name with an ``urd::arg`` per further parameter
     (``urd::function<"value", &view_mixin::value, urd::arg<"column">>``). A member template whose template arguments
     its callers write (``get<FluentTag>()``) is C++'s alone and not listed.

  A mixin declares member functions only (no data member, alias, nested type or using-declaration), has no base but its
  tag's mixin (a held form's mixin may inherit it), and never calls ``record()``, which would bypass the resolution
  ``member<>`` does and tie the view to how the record is laid out. A function derives something new: none only
  forwards a path of getters its callers could read themselves (``get_name()`` as ``get_symbol().get_name()``).

  A family of tags has a mixin per record specialization, or one generic mixin over its own parameters that serves
  several (``view_mixin<Atom<T, F>, V>`` serves the lifted and the ground atoms). The lifted atoms' mixin, with a
  derived function:

  .. code-block:: cpp

     // include/lib/formalism/atom_view.hpp
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

  ``is_ground`` may as well be a free function over the view, declared before the mixin and listed the same way
  (``&lib::formalism::is_ground<V>``); Python calls it as the same method, ``atom.is_ground()``.

  .. note::

     **A key of the library's own.** A field whose type no context resolves as an ``urd::index`` (a label, a packed
     handle) tells urd how a view reads it by a specialization ``urd::resolution<M>`` beside the type: ``of``, the
     field as its getter returns it, and ``stored``, the field written from what reads as it. A label that names
     nothing reads as itself.

- .. rule:: schema-record-binding
  .. rule:: S4

  :ruleid:`S4` :decidable:`decidable`
  **A record is bound in Python by** ``urd::python::bind_index<T>(m)`` **where it holds its index,**
  ``urd::python::bind_data<T>(m)``, ``urd::python::bind_builder<T, C>(m)`` **for its builder and**
  ``urd::python::bind_view<View>(m)`` **for each of its views, one class each, and by nothing else.**

  :Name: ``schema-record-binding``
  :Check: ``python -m pybrokkr.rules S4`` (with the compile database of a configured build)

  urd binds a record's fields, its index, comparison, hashing, ``str`` and ``repr``, and its views' field getters and
  ``functions()`` (S3). The classes are named from ``urd::name<T>()``, the tag's ``static constexpr std::string_view
  name``, so that no binding names a record or a field by hand:

  .. list-table::
     :header-rows: 1
     :widths: 22 78

     * - Class
       - Members
     * - ``<Name>Index``
       - ``bind_index``, ``urd::index<T>``: ``value``, ``is_none()``, ``int()``, comparison and hashing; bound once,
         before ``bind_data``, by whichever module binds it first
     * - ``<Name>Data``
       - ``bind_data``, ``urd::data<T>``: an ``__init__`` from the fields in order, each field read and written under
         its name, comparison by the identifying members, ``str`` and ``repr``
     * - ``<Name>``
       - ``bind_view``, the view: each ``get_<field>()``, comparison and hashing by its identity, ``str`` and
         ``repr``, ``context()``, ``index()``, and the entries of ``functions()``. A view that borrows, owns or shares
         its record is ``<Name>Borrowed``, ``<Name>Owned``, ``<Name>Shared``; a builder's view has ``Builder`` before
         these (``AtomBuilderBorrowed``)
     * - ``<Name>Builder``
       - ``bind_builder``, ``urd::builder<T, C>``: an ``__init__`` that takes each field by its name, every one
         optional, ``set_<field>(value)`` for each field, the entries of its ``functions()`` (S2), and
         ``view(context)``. A repository interns a builder with its children (``Repository.insert(builder)``)

  What a view offers in Python is decided where the view is, by ``fields()`` and ``functions()``, never by a ``.def``
  in a binding. A function that takes more than the view (options, a context) is an algorithm over it, bound with
  ``m.def``.

  .. code-block:: cpp

     // python/src/pylib/formalism/atom.cpp
     urd::python::bind_index<lib::formalism::Atom>(m);
     urd::python::bind_data<lib::formalism::Atom>(m);
     urd::python::bind_builder<lib::formalism::Atom, lib::Repository>(m);  // set_predicate, set_terms, clear, view
     urd::python::bind_view<lib::formalism::AtomView>(m);  // get_predicate, get_terms and functions(): is_ground

  .. note::

     **Names of a family.** A tag of a family is named after its arguments where the records of one module need names
     of their own (``urd::joined_name<"Atom", Tag::name>``), and not where each is bound in a module of its own.

Values
------

A value is a record no Store holds: ``urd::data<T>`` with no index, compared, hashed, written and bound as a record is,
by S1 to S4. A value that holds a child (an index of a record) is built by its builder and read through its views, as a
record. A value with neither an index nor a child (two numbers, a label: ``urd::PlainValue``) is held, built and read as
it is, with no builder or view of its own.

- .. rule:: schema-value
  .. rule:: S5

  :ruleid:`S5` :decidable:`decidable`
  **A type that declares** ``fields()`` **and** ``identifying_members()`` **is a** ``urd::data<T>``
  **specialization, or a key.**

  :Name: ``schema-value``
  :Check: ``python -m pybrokkr.rules S5`` (with the compile database of a configured build)

  Every type with a static ``fields()`` and ``identifying_members()`` is a record (S1 to S4) or a key of the library's
  own (one ``urd::resolution`` reads, S3). A type with ``fields()`` alone is printable, not a value. A class with
  behaviour (private state, member functions) declares no ``fields()`` and is written by a ``fmt::formatter`` of its
  own. A plain value, the bounds of an interval:

  .. code-block:: cpp

     // include/lib/formalism/declarations.hpp
     namespace lib::formalism
     {
     struct Bounds
     {
         static constexpr std::string_view name = "Bounds";
     };
     }

     template<>
     struct urd::data<lib::formalism::Bounds>
     {
         std::int64_t lower;
         std::int64_t upper;

         data() = default;
         data(std::int64_t lower_, std::int64_t upper_) : lower(lower_), upper(upper_) {}

         static constexpr bool copyable() noexcept
         {
             static_assert(std::is_trivially_copyable_v<data>, "a copyable record is trivially copyable");
             return true;
         }

         static constexpr auto fields() noexcept { return urd::Fields<urd::field<"lower", &data::lower>, urd::field<"upper", &data::upper>> {}; }
         static constexpr auto identifying_members() noexcept { return urd::members_of(fields()); }
         static constexpr auto cista_members() noexcept { return urd::Members<&data::lower, &data::upper> {}; }
     };

     // python/src/pylib/formalism/bounds.cpp
     urd::python::bind_data<lib::formalism::Bounds>(m);  // BoundsData

Status
------

``python -m pybrokkr.rules S`` checks the five rules on every tracked file, tests included; what it reports is where a
library does not follow them yet. A file it cannot parse is a finding, not a skip.
