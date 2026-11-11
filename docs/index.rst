brokkr
======

brokkr is what the planning-and-learning libraries (urd, yggdrasil, loki, tyr, runir) share that is not library code:

- the build tooling, ``pybrokkr``: CMake helpers and a PEP 517 backend for native C++ libraries shipped as Python
  wheels, described in the `README <https://github.com/planning-and-learning/brokkr#readme>`__;
- the rules below, which apply to every one of the libraries and are maintained only here.

.. toctree::
   :maxdepth: 2
   :caption: Rules

   release_cycle
   template_rules
   coding_rules
