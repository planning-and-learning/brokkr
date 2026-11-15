# Copyright (C) 2026 Dominik Drexler
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sphinx configuration for brokkr's documentation.

Build it with `build/docs-venv/bin/sphinx-build -W -b html docs build/docs/html`; the virtual environment comes from
docs/requirements.txt.
"""

from typing import Protocol

project = "brokkr"
author = "Dominik Drexler"
project_copyright = "2026, Dominik Drexler"

extensions = ["sphinx.ext.githubpages"]

# A rule's ID and its class (reading_the_rules.rst): the ID in bold, the class a colored badge; a list of rules shows no
# bullets, as each rule starts with its ID.
rst_prolog = """
.. role:: ruleid
.. role:: decidable
.. role:: measured
.. role:: judgment
.. role:: process

.. raw:: html

   <style>
   span.decidable, span.measured, span.judgment, span.process {
     color: #fff; border-radius: 0.25em; padding: 0.05em 0.4em; font-size: 0.8em; font-weight: 600;
   }
   span.decidable { background: #2e7d32; }
   span.measured { background: #1565c0; }
   span.judgment { background: #b26a00; }
   span.process { background: #616161; }
   span.ruleid { font-weight: 700; margin-right: 0.3em; }
   li:has(> p > span.ruleid) { list-style: none; }
   </style>
"""

html_theme = "furo"
html_title = "brokkr"
html_theme_options = {
    "source_repository": "https://github.com/planning-and-learning/brokkr/",
    "source_branch": "main",
    "source_directory": "docs/",
}


class _Sphinx(Protocol):
    """What setup uses of sphinx.application.Sphinx; sphinx is installed only where the documentation is built."""

    def add_crossref_type(self, directivename: str, rolename: str) -> None: ...


def setup(app: _Sphinx) -> None:
    """Register the rule directive and role: ``.. rule:: <name>`` marks a rule, ``:rule:`<name>``` links to it."""
    app.add_crossref_type("rule", "rule")
