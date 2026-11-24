brokkr
======

brokkr is what the planning-and-learning libraries (urd, yggdrasil, loki, tyr, runir) share that is not library code:

- the build tooling, ``pybrokkr``: CMake helpers and a PEP 517 backend for native C++ libraries shipped as Python
  wheels, described in the `README <https://github.com/planning-and-learning/brokkr#readme>`__;
- the rules below, which apply to every one of the libraries and are maintained only here.

.. toctree::
   :hidden:
   :caption: Introduction

   Overview <self>
   reading_the_rules

.. toctree::
   :maxdepth: 2
   :caption: Rules

   directory_layout
   include_rules
   template_rules
   schema_rules
   determinism_rules
   coding_rules

.. toctree::
   :maxdepth: 2
   :caption: Workflows

   release_cycle
