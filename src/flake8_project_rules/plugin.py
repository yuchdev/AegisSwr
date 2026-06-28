"""Flake8 AST plugin that exposes custom project rules X001–X011."""
from __future__ import annotations

from pathlib import Path

from flake8_project_rules.rules import check_tree


class ProjectRulesPlugin:
    """Flake8 AST plugin for project-specific lint rules X001–X011."""

    name = "flake8-project-rules"
    version = "0.1.0"

    def __init__(self, tree, filename="<unknown>"):
        """Initialise the plugin with the parsed AST and source filename."""
        self.tree = tree
        self.filename = filename

    def run(self):
        """Yield Flake8 diagnostics for every rule violation found in the tree."""
        source = None

        if self.filename not in (None, "-", "stdin", "<unknown>"):
            try:
                source = Path(self.filename).read_text(encoding="utf-8")
            except OSError:
                source = None

        for violation in check_tree(self.tree, self.filename, source):
            yield (
                violation.lineno,
                violation.col_offset,
                f"{violation.code} {violation.message}",
                type(self),
            )
