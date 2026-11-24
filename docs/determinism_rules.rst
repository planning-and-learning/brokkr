Determinism
===========

A result of urd, yggdrasil, loki, tyr or runir (a plan, a search's statistics, a heuristic value, a numbering, an
output) is the same on every platform, standard library and compiler. Hash containers keep their elements in an order
that nothing specifies: gtl's tables place them in groups of 16 slots with SSE2 (x86-64) and of 8 elsewhere (arm64),
the standard library's unordered containers by their own growth policy, and any of them by their capacity and history.
With the same hashes, the same elements come out in another order. These rules keep that order out of results. They
apply to all five repositories and are maintained only here.

A test that compares exact statistics shows a violation only on the platform whose order differs. On x86-64, a build
with ``-DGTL_HAVE_SSE2=0 -DGTL_HAVE_SSSE3=0`` gives gtl's tables the portable groups of arm64, and so their order there.

Order
-----

- .. rule:: determinism-unordered-iteration
  .. rule:: D1

  :ruleid:`D1` :judgment:`judgment`
  **Iterate an unordered set or map only for work its order does not change.**

  :Name: ``determinism-unordered-iteration``

  Unordered are ``urd::set`` and ``urd::map`` without ``urd::dense`` or ``urd::sorted`` (urd selects a hash table for
  them) and the standard library's ``std::unordered_*``. Work their order does not change: lookups, counting,
  clearing, aggregation that is commutative (a sum, a minimum, a maximum) and inserting into another unordered
  container. In tyr's ground Datalog solver, a cost bucket hands out its facts in a hash set's order; counting down the
  conditions of the rules waiting on them is such work, but the order in which the rules then become ready is not
  (:rule:`D2`).

- .. rule:: determinism-defined-order
  .. rule:: D2

  :ruleid:`D2` :judgment:`judgment`
  **Where the order of elements decides a result, iterate a store whose order is defined.**

  :Name: ``determinism-defined-order``

  A result an order decides: the order in which rules fire or successors are generated, which of equal alternatives
  wins (:rule:`D3`), a numbering, an output, a serialization. A store with a defined order: ``urd::dense`` (index
  order), ``urd::sorted`` (key order), or a sequence whose inserts come in a defined order themselves. Request the
  order in the store's tags (``urd::dense, urd::sorted``), so that urd selects only a container that keeps it, and the
  type states that the order matters. tyr's Datalog solvers keep the rules to fire this way: the lifted one its active
  rules sorted, the ground one its ready rules in a dense, sorted set of rule indices.

- .. rule:: determinism-stated-tie-break
  .. rule:: D3

  :ruleid:`D3` :judgment:`judgment`
  **Break a tie by a stated key, not by the order in which the alternatives arrive.**

  :Name: ``determinism-stated-tie-break``

  Among equally good alternatives (achievers of equal cost, open states of equal priority), the one with the smallest
  key wins, and the code that breaks the tie states the key: a rule's index (program order), the number a queue gives
  each entry as it is pushed. In tyr, the witness of a fact is the first of its equally cheap achievers, so the ground
  solver fires the ready rules in program order: which achiever that is, and so the relaxed plan FF extracts and its
  value, is the same on every platform.
