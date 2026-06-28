from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import pytest
from lint_rules import check_file, RuleViolation

# Share the directory-selection logic with the Flake8 suite so the two linters
# always scan exactly the same files and report exactly the same violations.
# (``pythonpath = ["."]`` in pyproject.toml makes this package importable.)
from tests.flake8_lint.test_project_lint import covered_dirs

PROJECT_ROOT = Path(__file__).parents[2]


def iter_python_files() -> Iterable[Path]:
    """Yield all project top-level *.py files in covered_dirs (no subfolders)."""
    for dir_str in covered_dirs(["src", "tests"], []):
        for path in Path(dir_str).glob("*.py"):
            yield path


def test_code_style_custom_rules():
    """
    [Integration] Custom lint rules: all covered Python files pass custom linting checks.

    Scenario:
        Given a set of project Python files in covered directories
        When check_file() runs all custom lint rules (X001-X011)
        Then no RuleViolation instances are returned
        And all code follows the project's custom style guidelines.

    Boundaries:
        - Real: AST parsing, lint rule implementations, file I/O
        - Scope: source code, tests
        - Covers: broad exceptions, muted exceptions, Settings.set(), local imports, docstrings.

    On failure, first check:
        - The specific violation message and line number in the output
        - Whether a recent code change introduced the violation
        - The lint_rules.py module for the rule implementation
        - Whether the rule should be adjusted or the code should be fixed.
    """
    violations: List[RuleViolation] = []

    for path in iter_python_files():
        file_violations = check_file(path)
        if file_violations:
            for v in file_violations:
                violations.append(v)

    if violations:
        lines = [
            f"{v.filename}:{v.lineno}:{v.col_offset}: {v.code} {v.message}"
            for v in violations
        ]
        msg = "Custom lint violations found:\n" + "\n".join(lines)
        pytest.fail(msg)
