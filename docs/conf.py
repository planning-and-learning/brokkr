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
# bullets, as each rule starts with its ID; its statement (the paragraph with its ID) stands in a box above its
# explanation.
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
   /* A rule's statement (its first paragraph: ID, class, the rule itself) in a box; its explanation follows below. */
   li > p:has(> span.ruleid) {
     border: 1px solid var(--color-brand-primary);
     border-left-width: 0.4em;
     background: color-mix(in srgb, var(--color-brand-primary) 12%, var(--color-background-primary));
     padding: 0.8em 1em;
     margin: 1.2em 0 0.8em;
     border-radius: 0.3em;
     font-size: 1.05em;
     box-shadow: 0 1px 3px color-mix(in srgb, var(--color-foreground-primary) 15%, transparent);
   }
   /* Its name and check, right below the statement, close the box: one line each, the label before the value. */
   li > p:has(> span.ruleid):has(+ dl.field-list) {
     margin-bottom: 0;
     border-bottom: none;
     border-radius: 0.3em 0.3em 0 0;
     box-shadow: none;
   }
   li > p:has(> span.ruleid) + dl.field-list {
     display: grid;
     grid-template-columns: max-content 1fr;
     gap: 0.15em 0.8em;
     margin: 0 0 0.8em;
     padding: 0.4em 1em 0.7em;
     border: 1px solid var(--color-brand-primary);
     border-top: 1px dashed color-mix(in srgb, var(--color-brand-primary) 40%, transparent);
     border-left-width: 0.4em;
     border-radius: 0 0 0.3em 0.3em;
     background: color-mix(in srgb, var(--color-brand-primary) 12%, var(--color-background-primary));
     box-shadow: 0 1px 3px color-mix(in srgb, var(--color-foreground-primary) 15%, transparent);
     font-size: 0.9em;
   }
   li > p:has(> span.ruleid) + dl.field-list > dt,
   li > p:has(> span.ruleid) + dl.field-list > dd { margin: 0; padding: 0; }
   li > p:has(> span.ruleid) + dl.field-list > dd > p { margin: 0; }
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
