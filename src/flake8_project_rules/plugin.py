"""Flake8 AST plugin that exposes custom project rules X001–X012."""

from __future__ import annotations

from pathlib import Path

from flake8_project_rules.rules import check_tree


class ProjectRulesPlugin:
    """Flake8 AST plugin for project-specific lint rules X001–X012."""

    name = "flake8-project-rules"
    version = "0.1.0"

    def __init__(self, tree, filename="<unknown>", apply_noqa: bool = True):
        """Initialise the plugin with the parsed AST and source filename.

        :param apply_noqa: forwarded to :func:`check_tree`; real flake8 runs
            always get the default (``True``), only test harnesses that read
            ``[tool.flake8_lint_tests] allow_noqa`` override it.
        """
        self.tree = tree
        self.filename = filename
        self._apply_noqa = apply_noqa

    def run(self):
        """Yield Flake8 diagnostics for every rule violation found in the tree."""
        source = None

        if self.filename not in (None, "-", "stdin", "<unknown>"):
            try:
                source = Path(self.filename).read_text(encoding="utf-8")
            except OSError:
                source = None

        for violation in check_tree(self.tree, self.filename, source, apply_noqa=self._apply_noqa):
            yield (
                violation.lineno,
                violation.col_offset,
                f"{violation.code} {violation.message}",
                type(self),
            )
