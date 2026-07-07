"""Project-wide lint scan driven through the Flake8 plugin surface.

This mirrors ``tests/lint/test_linting.py::test_code_style_custom_rules`` (the
frozen reference implementation that walks the real project tree with a manual
AST linter) but exercises the **production** Flake8 plugin instead:
``ProjectRulesPlugin.run()`` yields the same diagnostics Flake8 would emit when
the ``X`` rules run over a file.

The set of directories to lint is built by :func:`covered_dirs`, which both this
suite and the reference suite share, so the two linters always scan exactly the
same files and therefore report exactly the same violations.

Scope is further narrowed by the ``[tool.flake8_lint_tests]`` section of
``pyproject.toml`` (see ``tests/flake8_lint/config.py``): ``include``/
``exclude`` pick which directories - or individual files - are scanned
(default: ``src`` and ``tests``), ``select``/``ignore`` pick which of the
custom X-rules gate this test, and ``allow_noqa`` (default ``True``)
controls whether a ``# noqa`` comment can suppress a diagnostic here at all
- so the two suites (this one and ``test_plugin_direct.py``) always enforce
the same policy.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path
from typing import Union

import pytest

from flake8_project_rules.plugin import ProjectRulesPlugin
from tests.flake8_lint.config import active_rule_codes, allow_noqa, configured_directories

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


def _excluded_dirs(excluded: list[Union[str, Path]], exclude_recursive: bool) -> set[Path]:
    """Resolve directory entries of *excluded* to the full set of dirs they remove."""
    removed: set[Path] = set()
    for entry in excluded:
        removed.update(_expand(entry, exclude_recursive))
    return removed


def _file_entries(entries: list[Union[str, Path]]) -> set[Path]:
    """Resolve the entries of *entries* that name an individual file (not a directory)."""
    return {_resolve(entry) for entry in entries if _resolve(entry).is_file()}


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
    virtualenvs, or caches. Entries that name an individual file rather than a
    directory contribute nothing here - see :func:`covered_files`.

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

    removed = _excluded_dirs(excluded, exclude_recursive)

    result = [
        directory
        for directory in selected
        if directory not in removed and not (_DEFAULT_EXCLUDED_DIR_NAMES & set(directory.parts))
    ]
    return sorted(str(directory) for directory in result)


def covered_files(
    included: list[Union[str, Path]],
    excluded: list[Union[str, Path]],
    exclude_recursive: bool = True,
) -> list[str]:
    """Individual files named directly in *included*, minus the excluded ones.

    Mirrors :func:`covered_dirs`' whitelist-then-blacklist order: a file named
    in *included* is dropped when it is itself named in *excluded*, or when it
    falls under a directory named in *excluded* - the blacklist always wins.

    :param included: entries that may name an individual file to lint.
    :param excluded: entries (files or directories) that veto an included file.
    :param exclude_recursive: when True, an excluded directory vetoes files in
        its subdirectories too, not just its immediate children.
    :return: a sorted list of file paths (as strings) to lint.
    """
    removed_dirs = _excluded_dirs(excluded, exclude_recursive)
    excluded_files = _file_entries(excluded)

    result = [
        path for path in _file_entries(included) if path not in excluded_files and path.parent not in removed_dirs
    ]
    return sorted(str(path) for path in result)


def _iter_python_files() -> Iterable[Path]:
    """Yield the ``*.py`` files selected by ``[tool.flake8_lint_tests]``.

    Covered directories (see :func:`covered_dirs`) contribute their top-level
    files (non-recursive glob per directory); individual files named directly
    in ``include``/``exclude`` are layered on top via :func:`covered_files`,
    with the exclude blacklist always winning. Defaults to ``src`` and
    ``tests`` when ``include`` is empty.
    """
    include, exclude = configured_directories(["src", "tests"])
    excluded_files = _file_entries(exclude)

    seen: set[Path] = set()
    for dir_str in covered_dirs(include, exclude):
        for path in Path(dir_str).glob("*.py"):
            if path in excluded_files:
                continue
            seen.add(path)
            yield path

    for file_str in covered_files(include, exclude):
        path = Path(file_str)
        if path not in seen:
            yield path


def _run_plugin(path: Path) -> list[tuple[int, int, str]]:
    """Run the Flake8 plugin over *path* and return ``(line, col, message)`` tuples.

    Honours ``[tool.flake8_lint_tests] allow_noqa``: when the config disables
    it, every violation is reported regardless of any ``# noqa`` comment.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    plugin = ProjectRulesPlugin(tree, str(path), apply_noqa=allow_noqa())
    return [(lineno, col, text) for (lineno, col, text, _type) in plugin.run()]


def test_project_custom_flake8_rules_pass():
    """
    [Integration] flake8 plugin: covered source files pass all active custom X-rules.

    Scenario:
        Given the directories selected by [tool.flake8_lint_tests] include/exclude
        (the same top-level Python files the reference manual-AST linter in
        tests/lint/test_linting.py scans via covered_dirs())
        When the production Flake8 plugin (ProjectRulesPlugin) runs over them
        Then no diagnostic whose rule code is in the active select/ignore set
        is produced.

    Boundaries:
        - Real: AST parsing, flake8 plugin rule engine, file I/O
        - Scope: configured_directories(["src", "tests"]) via covered_dirs()
        - Rules: the active subset of X001-X011 from [tool.flake8_lint_tests]
        - Excludes: git-ignored dirs (.venv, build, dist, caches, ...)

    On failure, first check:
        - The specific violation message and line number in the output
        - Whether a recent code change introduced the violation
        - Whether the diagnostics match tests/lint/test_linting.py (they must)
        - The flake8_project_rules.rules module for the rule implementation.
    """
    active = set(active_rule_codes())
    diagnostics: list[str] = []

    for path in _iter_python_files():
        for lineno, col, message in _run_plugin(path):
            code = message.split(" ", 1)[0]
            if code in active:
                diagnostics.append(f"{path}:{lineno}:{col}: {message}")

    if diagnostics:
        msg = "Custom flake8 rule violations found:\n" + "\n".join(diagnostics)
        pytest.fail(msg)
