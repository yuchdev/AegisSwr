"""Direct tests for the new Flake8 rule engine (flake8_project_rules.rules).

Each test loads a dedicated sample file from ``tests/flake8_project_rules/samples/``
and asserts that the expected rule code is (or is not) present in the violation set.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List

import pytest

from flake8_project_rules.rules import RuleViolation, check_tree

SAMPLES_DIR = Path(__file__).parent / "samples"


def run_new_checker(path: Path) -> List[RuleViolation]:
    """Parse *path* and run the new rule engine, returning all violations."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return list(check_tree(tree, str(path), source))


def violation_codes(path: Path):
    """Return the set of rule codes found in *path*."""
    return {v.code for v in run_new_checker(path)}


# ---------------------------------------------------------------------------
# X001 – bare except
# ---------------------------------------------------------------------------

def test_x001_bare_except_detected():
    """
    [Unit] rules: X001 bare except is detected.

    Scenario:
        Given a sample file with a bare `except` clause
        When the new rule engine runs
        Then X001 is reported

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x001_bare_except.py
        - Rule: X001

    On failure, first check:
        - That the sample file still contains a bare `except:` clause
        - That _check_broad_exception fires for node.type is None
    """
    codes = violation_codes(SAMPLES_DIR / "x001_bare_except.py")
    assert "X001" in codes


def test_x001_not_on_clean_module():
    """
    [Unit] rules: X001 not reported on a clean module.

    Scenario:
        Given a valid clean module
        When the new rule engine runs
        Then X001 is not reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/valid_clean_module.py
        - Rule: X001

    On failure, first check:
        - That valid_clean_module.py has no bare except handlers
    """
    codes = violation_codes(SAMPLES_DIR / "valid_clean_module.py")
    assert "X001" not in codes


# ---------------------------------------------------------------------------
# X002 – broad Exception
# ---------------------------------------------------------------------------

def test_x002_broad_exception_detected():
    """
    [Unit] rules: X002 broad Exception is detected.

    Scenario:
        Given a sample file with `except Exception:`
        When the new rule engine runs
        Then X002 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x002_broad_exception.py
        - Rule: X002

    On failure, first check:
        - That the sample file still contains `except Exception:`
    """
    codes = violation_codes(SAMPLES_DIR / "x002_broad_exception.py")
    assert "X002" in codes


# ---------------------------------------------------------------------------
# X003 – Settings.set()
# ---------------------------------------------------------------------------

def test_x003_settings_set_detected():
    """
    [Unit] rules: X003 Settings.set() is detected.

    Scenario:
        Given a sample file with a `set` method on a `Settings` class
        When the new rule engine runs
        Then X003 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x003_settings_set.py
        - Rule: X003

    On failure, first check:
        - That the sample file still defines Settings.set()
    """
    codes = violation_codes(SAMPLES_DIR / "x003_settings_set.py")
    assert "X003" in codes


# ---------------------------------------------------------------------------
# X004 – muted exception handler
# ---------------------------------------------------------------------------

def test_x004_muted_exception_detected():
    """
    [Unit] rules: X004 muted exception handler is detected.

    Scenario:
        Given a sample file with an except block containing only `pass`
        When the new rule engine runs
        Then X004 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x004_muted_exception.py
        - Rule: X004

    On failure, first check:
        - That the sample file still has an except: pass block
    """
    codes = violation_codes(SAMPLES_DIR / "x004_muted_exception.py")
    assert "X004" in codes


# ---------------------------------------------------------------------------
# X005 – missing / malformed docstring
# ---------------------------------------------------------------------------

def test_x005_missing_docstring_detected():
    """
    [Unit] rules: X005 is reported for a function without a docstring.

    Scenario:
        Given a sample file with a function that has no docstring
        When the new rule engine runs
        Then X005 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x005_missing_docstring.py
        - Rule: X005

    On failure, first check:
        - That the sample function still lacks a docstring
    """
    codes = violation_codes(SAMPLES_DIR / "x005_missing_docstring.py")
    assert "X005" in codes


def test_x005_structured_test_docstring_detected():
    """
    [Unit] rules: X005 is reported for a test function with a non-structured docstring.

    Scenario:
        Given a sample test file with a test function whose docstring lacks
        the required structured header and sections
        When the new rule engine runs
        Then X005 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x005_structured_test_docstring.py
        - Rule: X005

    On failure, first check:
        - That the sample test function still lacks the [Type] header / sections
    """
    codes = violation_codes(SAMPLES_DIR / "x005_structured_test_docstring.py")
    assert "X005" in codes


def test_x005_not_on_clean_module():
    """
    [Unit] rules: X005 not reported on a clean module.

    Scenario:
        Given a valid clean module where all classes and functions have docstrings
        When the new rule engine runs
        Then X005 is not reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/valid_clean_module.py
        - Rule: X005

    On failure, first check:
        - That valid_clean_module.py has docstrings everywhere
    """
    codes = violation_codes(SAMPLES_DIR / "valid_clean_module.py")
    assert "X005" not in codes


# ---------------------------------------------------------------------------
# X006 – local import
# ---------------------------------------------------------------------------

def test_x006_local_import_detected():
    """
    [Unit] rules: X006 local import is detected.

    Scenario:
        Given a sample file with an import statement inside a function body
        When the new rule engine runs
        Then X006 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x006_local_import.py
        - Rule: X006

    On failure, first check:
        - That the sample function still imports inside its body
    """
    codes = violation_codes(SAMPLES_DIR / "x006_local_import.py")
    assert "X006" in codes


# ---------------------------------------------------------------------------
# X007 – missing return type annotation
# ---------------------------------------------------------------------------

def test_x007_missing_return_annotation_detected():
    """
    [Unit] rules: X007 missing return annotation is detected.

    Scenario:
        Given a sample file with a function that returns a value but lacks
        a return type annotation
        When the new rule engine runs
        Then X007 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x007_missing_return_annotation.py
        - Rule: X007

    On failure, first check:
        - That the sample function still returns a value without an annotation
    """
    codes = violation_codes(SAMPLES_DIR / "x007_missing_return_annotation.py")
    assert "X007" in codes


# ---------------------------------------------------------------------------
# X008 – explicit None return annotation
# ---------------------------------------------------------------------------

def test_x008_none_return_annotation_detected():
    """
    [Unit] rules: X008 explicit `-> None` annotation is detected.

    Scenario:
        Given a sample file with a function annotated `-> None`
        When the new rule engine runs
        Then X008 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x008_none_return_annotation.py
        - Rule: X008

    On failure, first check:
        - That the sample function still has `-> None` in its signature
    """
    codes = violation_codes(SAMPLES_DIR / "x008_none_return_annotation.py")
    assert "X008" in codes


# ---------------------------------------------------------------------------
# X009 – percent-style string formatting
# ---------------------------------------------------------------------------

def test_x009_percent_formatting_detected():
    """
    [Unit] rules: X009 percent formatting is detected.

    Scenario:
        Given a sample file that uses `"..." % value` syntax
        When the new rule engine runs
        Then X009 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x009_percent_formatting.py
        - Rule: X009

    On failure, first check:
        - That the sample file still uses `%s` style formatting
    """
    codes = violation_codes(SAMPLES_DIR / "x009_percent_formatting.py")
    assert "X009" in codes


# ---------------------------------------------------------------------------
# X010 – suppressed ImportError
# ---------------------------------------------------------------------------

def test_x010_import_error_suppression_detected():
    """
    [Unit] rules: X010 suppressed ImportError is detected.

    Scenario:
        Given a sample file with a try/except block that catches ImportError
        and silently assigns None instead of re-raising
        When the new rule engine runs
        Then X010 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x010_import_error_suppression.py
        - Rule: X010

    On failure, first check:
        - That the sample file still has an unguarded except ImportError block
    """
    codes = violation_codes(SAMPLES_DIR / "x010_import_error_suppression.py")
    assert "X010" in codes


# ---------------------------------------------------------------------------
# X011 – Type | None union annotation
# ---------------------------------------------------------------------------

def test_x011_union_none_detected():
    """
    [Unit] rules: X011 Type | None annotation is detected.

    Scenario:
        Given a sample file with a function parameter annotated `int | None`
        When the new rule engine runs
        Then X011 is reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/x011_union_none.py
        - Rule: X011

    On failure, first check:
        - That the sample function parameter still uses `| None` syntax
    """
    codes = violation_codes(SAMPLES_DIR / "x011_union_none.py")
    assert "X011" in codes


# ---------------------------------------------------------------------------
# Valid clean module
# ---------------------------------------------------------------------------

def test_valid_clean_module_has_no_violations():
    """
    [Unit] rules: clean module produces zero violations.

    Scenario:
        Given a module that intentionally satisfies all custom rules
        When the new rule engine runs
        Then no violations are reported.

    Boundaries:
        - Input: tests/flake8_project_rules/samples/valid_clean_module.py
        - Rules: X001-X011

    On failure, first check:
        - That valid_clean_module.py has not been accidentally modified
        - Which specific rule is firing and why
    """
    violations = run_new_checker(SAMPLES_DIR / "valid_clean_module.py")
    assert violations == [], (
        "Expected no violations but got:\n"
        + "\n".join(f"  {v.code} {v.filename}:{v.lineno} {v.message}" for v in violations)
    )
