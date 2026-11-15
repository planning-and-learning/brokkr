Reading the rules
=================

Each page holds the rules of one topic, grouped in sections. A rule starts with its ID, its class and its statement in
bold; the text after the statement gives the reason and the details, and the rule ends with its name and, where one
exists, its check.

- **ID.** A letter for the page and a number: ``L`` for :doc:`directory_layout`, ``I`` for :doc:`include_rules`, ``T``
  for :doc:`template_rules`, ``S`` for :doc:`schema_rules`. An ID is given once, in the order the rule is added, and
  never changes or goes to another rule, also when the rules are reordered or one is removed. Code, commits and
  findings cite a rule by its ID and its name (``T3 (template-opt-in-extern-lists)``); a link to a rule is written
  ``:rule:`T3```.
- **Name.** What the rule is about, in a few words (``template-opt-in-extern-lists``), so that a citation reads without
  the page.
- **Class.** What can tell whether code follows the rule. Whether a property of code can be decided by a program
  depends on the property: one of its text, its syntax tree or its include graph can, one of its behavior in general
  cannot (Rice's theorem), and a checker of such a rule misses violations, reports false ones, or both.
- **Check.** The command that checks the rule, where one exists. A decidable rule without a check is not yet
  enforced: a check is the next thing to write for it.

.. list-table::
   :header-rows: 1
   :widths: 18 82

   * - Class
     - What tells whether code follows the rule
   * - :decidable:`decidable`
     - A program: the rule is a property of the source text, the syntax tree or the include graph, which a check decides
       exactly, without misses or false findings, for every configuration that is built. Templates that are never
       instantiated and branches of ``#if`` that are never active are not built, so the checks run over every
       configuration and instantiate what the library declares.
   * - :measured:`measured`
     - A measurement: the rule is about cost (compile time, compiler memory, run time), which the code does not decide
       for every compiler. A build with a fixed compiler, version and flags decides it for that build, against a limit.
   * - :judgment:`judgment`
     - A reviewer: the rule depends on what the code is meant to do (which types are heavy, what a parameter is for). A
       program checks only an approximation of it; a rule restated so that a program decides it becomes decidable.
   * - :process:`process`
     - Nothing in the code: the rule says how to change code (measure before and after), not what the code is.
