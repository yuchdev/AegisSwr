"""Shared TOML config loader for the ``[tool.flake8_lint_tests]`` pytest section.

Seven keys, analogous to Ruff's project config: ``include``/``exclude`` are
directories or individual files that scope *which paths* get linted, and
``select``/``ignore`` are rule codes that scope *which* of the custom X-rules
are enforced. Within each pair the whitelist (``include``/``select``) is applied
first and the blacklist (``exclude``/``ignore``) is subtracted last, so it always wins.
An empty whitelist means "everything".

``allow_noqa`` (bool, default ``True``) is a global switch: when ``False``,
``# noqa`` comments never suppress a violation project-wide.
``noqa_allowed`` and ``noqa_forbidden`` provide granular file- and directory-level
scoping for ``# noqa`` suppression: when ``noqa_allowed`` is non-empty, only matching
files/directories may use ``# noqa``. Entries in ``noqa_forbidden`` are always
disallowed (blacklist wins). When both lists are empty (the default), ``# noqa`` is
permitted in all files.

Both ``tests/flake8_lint/test_plugin_direct.py`` (per-rule detection tests
against dedicated samples) and ``tests/flake8_lint/test_project_lint.py``
(the real project-wide scan) resolve their scope through this module, so the
two suites always agree on what is currently enforced.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Optional, Union

PROJECT_ROOT = Path(__file__).parents[2]

# Canonical catalogue of custom rule codes. Adding a new rule to
# flake8_project_rules.rules means adding its code here too.
KNOWN_RULE_CODES: list[str] = [
    "X001",
    "X002",
    "X004",
    "X005",
    "X006",
    "X007",
    "X008",
    "X009",
    "X010",
    "X011",
    "X012",
    "X013",
    "X014",
    "X015",
]

_CONFIG_SECTION = "flake8_lint_tests"


def load_config() -> dict[str, Any]:
    """Read the ``[tool.flake8_lint_tests]`` section from pyproject.toml.

    :return: the section as a mapping (values are either a list of str for
        ``include``/``exclude``/``select``/``ignore``/``noqa_allowed``/``noqa_forbidden``,
        or a bool for ``allow_noqa``), or an empty mapping when the file or section
        is missing, so callers fall back to their own defaults ("select every
        rule", "scan every configured directory", "noqa is honoured").
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    section = data.get("tool", {}).get(_CONFIG_SECTION, {})
    return section if isinstance(section, dict) else {}


def active_rule_codes(known_codes: Optional[list[str]] = None) -> list[str]:
    """Resolve which of *known_codes* are active, honouring select/ignore.

    :param known_codes: candidate rule codes in canonical order; defaults to
        :data:`KNOWN_RULE_CODES`.
    :return: the subset of *known_codes* that is active: ``select`` is
        applied as a whitelist (non-empty -> only those codes survive), then
        ``ignore`` is subtracted, so it always wins over ``select``.
    """
    codes = known_codes if known_codes is not None else KNOWN_RULE_CODES
    config = load_config()
    select: set[str] = set(config.get("select") or [])
    ignore: set[str] = set(config.get("ignore") or [])

    selected = [code for code in codes if code in select] if select else list(codes)
    return [code for code in selected if code not in ignore]


def allow_noqa() -> bool:
    """Whether ``# noqa`` comments may suppress a violation globally.

    :return: the config's ``allow_noqa`` value (default ``True`` when absent).
        When ``False``, callers must pass ``apply_noqa=False`` through to
        :func:`flake8_project_rules.rules.check_tree` so every violation is
        reported regardless of any ``# noqa`` comment.
    """
    return bool(load_config().get("allow_noqa", True))


def _resolve_path(entry: Union[str, Path]) -> Path:
    """Resolve a path relative to PROJECT_ROOT and resolve symlinks/relative parts.

    :param entry: file or directory path string or Path object.
    :return: absolute, resolved Path instance.
    """
    path = Path(entry)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _path_matches_entries(target: Path, entries: list[str]) -> bool:
    """Check if *target* matches any file or directory in *entries*.

    :param target: target path to test.
    :param entries: list of configured paths (files or directories).
    :return: True if *target* matches an entry or falls inside an entry directory.
    """
    resolved_target = _resolve_path(target)
    for entry in entries:
        if not entry:
            continue
        resolved_entry = _resolve_path(entry)
        # Exact match (for files or exact directory)
        if resolved_target == resolved_entry:
            return True
        # Directory prefix match (target resides inside entry directory)
        if resolved_target.is_relative_to(resolved_entry):
            return True
    return False


def is_noqa_allowed_for_file(path: Union[str, Path]) -> bool:
    """Determine whether ``# noqa`` suppression is permitted for *path*.

    Resolution logic:
    1. If global ``allow_noqa`` is False, returns False immediately.
    2. Synthetic / non-filesystem paths (e.g. ``<unknown>``, ``<stdin>``, ``<noqa-test>``)
       default to True when global ``allow_noqa`` is True.
    3. If ``noqa_allowed`` whitelist is non-empty, *path* must match an entry.
    4. If ``noqa_forbidden`` blacklist matches *path*, returns False (blacklist wins).
    5. Returns True otherwise.

    :param path: file path as a string or Path object.
    :return: True if ``# noqa`` comments should suppress violations in this file.
    """
    if not allow_noqa():
        return False

    str_path = str(path)
    if str_path.startswith("<") and str_path.endswith(">"):
        return True

    config = load_config()
    allowed_entries: list[str] = list(config.get("noqa_allowed") or [])
    forbidden_entries: list[str] = list(config.get("noqa_forbidden") or [])

    # Step 1: Whitelist check (if specified)
    if allowed_entries and not _path_matches_entries(Path(path), allowed_entries):
        return False

    # Step 2: Blacklist check (forbidden always wins)
    if forbidden_entries and _path_matches_entries(Path(path), forbidden_entries):
        return False

    return True


def configured_directories(default_include: list[str]) -> tuple[list[str], list[str]]:
    """Resolve the (include, exclude) path lists, honouring the config.

    :param default_include: directories to scan when the config's
        ``include`` list is empty/absent.
    :return: a ``(include, exclude)`` pair of paths (relative to the project
        root or absolute), each entry either a directory or an individual
        file, ready for ``test_project_lint.covered_dirs``/``covered_files``.
    """
    config = load_config()
    include = list(config.get("include") or []) or list(default_include)
    exclude = list(config.get("exclude") or [])
    return include, exclude
