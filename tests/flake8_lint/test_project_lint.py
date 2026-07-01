"""Project-wide lint scan driven through the Flake8 plugin surface.

This mirrors ``tests/lint/test_linting.py::test_code_style_custom_rules`` (the
frozen reference implementation that walks the real project tree with a manual
AST linter) but exercises the **production** Flake8 plugin instead:
``ProjectRulesPlugin.run()`` yields the same diagnostics Flake8 would emit when
the ``X`` rules run over a file.

The set of directories to lint is built by :func:`covered_dirs`, which both this
suite and the reference suite share, so the two linters always scan exactly the
same files and therefore report exactly the same violations.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path
from typing import Union

import pytest

from flake8_project_rules.plugin import ProjectRulesPlugin

PROJECT_ROOT = Path(__file__).parents[2]

# Directory names that are conventionally git-ignored. They are always dropped,
# even when a broad root such as `src` or `tests` is included, so a scan
# never descends into build artifacts, virtualenvs, or tool caches. The list
# mirrors the directory entries in the project `.gitignore`
_DEFAULT_EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".venv",
        "venv",
        "env",
        ".eggs",
        "eggs",
        "develop-eggs",
        "build",
        "dist",
        "downloads",
        "sdist",
        "wheels",
        "lib",
        "lib64",
        "parts",
        "var",
        ".tox",
        ".nox",
        ".cache",
        ".pytest_cache",
        ".mypy_cache",
        ".hypothesis",
        ".htmlcov",
        "cover",
        ".idea",
        ".vscode",
        "node_modules",
        "instance",
    }
)


def _resolve(entry: Union[str, Path]) -> Path:
    """Resolve *entry* against the project root unless it is already absolute."""
    path = Path(entry)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _expand(entry: Union[str, Path], recursive: bool) -> list[Path]:
    """Return the directory for *entry*, plus its subdirectories when *recursive*."""
    root = _resolve(entry)
    if not root.is_dir():
        return []
    if not recursive:
        return [root]
    dirs = [root]
    for sub in root.rglob("*"):
        if sub.is_dir():
            dirs.append(sub)
    return dirs


def covered_dirs(
    included: list[Union[str, Path]],
    excluded: list[Union[str, Path]],
    include_recursive: bool = True,
    exclude_recursive: bool = True,
) -> list[str]:
    """Build the directory list to lint: included directories minus excluded ones.

    Every directory in *included* is collected first (recursively when
    *include_recursive*); then every directory in *excluded* is removed
    (recursively when *exclude_recursive*). Conventionally git-ignored
    directories (see :data:`_DEFAULT_EXCLUDED_DIR_NAMES`) are always dropped, so
    a broad include like ``src`` or ``tests`` never pulls in build artefacts,
    virtualenvs, or caches.

    :param included: directories (``str`` or :class:`~pathlib.Path`, relative to
        the project root or absolute) whose Python files should be linted.
    :param excluded: directories to remove from the included set.
    :param include_recursive: when True, expand each included directory to all of
        its subdirectories.
    :param exclude_recursive: when True, expand each excluded directory to all of
        its subdirectories.
    :return: a sorted list of directory paths (as strings) to lint.
    """
    selected: set[Path] = set()
    for entry in included:
        selected.update(_expand(entry, include_recursive))

    removed: set[Path] = set()
    for entry in excluded:
        removed.update(_expand(entry, exclude_recursive))

    result = [
        directory
        for directory in selected
        if directory not in removed and not (_DEFAULT_EXCLUDED_DIR_NAMES & set(directory.parts))
    ]
    return sorted(str(directory) for directory in result)


def _iter_python_files() -> Iterable[Path]:
    """Yield top-level ``*.py`` files in every covered directory (non-recursive)."""
    for dir_str in covered_dirs(["src", "tests"], []):
        for path in Path(dir_str).glob("*.py"):
            yield path


def _run_plugin(path: Path) -> list[tuple[int, int, str]]:
    """Run the Flake8 plugin over *path* and return ``(line, col, message)`` tuples."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    plugin = ProjectRulesPlugin(tree, str(path))
    return [(lineno, col, text) for (lineno, col, text, _type) in plugin.run()]


def test_project_custom_flake8_rules_pass():
    """
    [Integration] flake8 plugin: covered source files pass all custom X-rules.

    Scenario:
        Given the same top-level Python files that the reference manual-AST
        linter (tests/lint/test_linting.py) scans via covered_dirs()
        When the production Flake8 plugin (ProjectRulesPlugin) runs over them
        Then no custom-rule diagnostics are produced
        And the result is identical to the reference linter's verdict.

    Boundaries:
        - Real: AST parsing, flake8 plugin rule engine, file I/O
        - Scope: covered_dirs(["src", "tests"], []) - same set as the reference
        - Excludes: git-ignored dirs (.venv, build, dist, caches, ...)

    On failure, first check:
        - The specific violation message and line number in the output
        - Whether a recent code change introduced the violation
        - Whether the diagnostics match tests/lint/test_linting.py (they must)
        - The flake8_project_rules.rules module for the rule implementation.
    """
    diagnostics: list[str] = []

    for path in _iter_python_files():
        for lineno, col, message in _run_plugin(path):
            diagnostics.append(f"{path}:{lineno}:{col}: {message}")

    if diagnostics:
        msg = "Custom flake8 rule violations found:\n" + "\n".join(diagnostics)
        pytest.fail(msg)
