"""Direct, config-driven tests for the Flake8 rule engine (flake8_project_rules.rules).

Each custom rule ``X001``..``X011`` is paired with a dedicated sample file under
``tests/flake8_lint/samples/``. Instead of one hand-written test per rule, the
suite is parametrised over a single source of truth (:data:`RULE_SAMPLES`) and
the set of rules it actually exercises is **configurable from a TOML file**.

Configuration lives in its own section of the project ``pyproject.toml``::

    [tool.flake8_lint_tests]
    include = ["X001", "X002"]   # whitelist: when non-empty, only these run
    exclude = ["X011"]           # blacklist: removed after include is applied

Resolution rules:

* When ``include`` is empty/absent, every known rule is selected.
* When ``include`` is non-empty, only the listed codes are selected.
* ``exclude`` is always subtracted last, so it wins over ``include``.
* Unknown codes in either list are ignored (they cannot match a sample).

With no section present, the default is "test every rule", matching the
previous behaviour.
"""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Dict, List, Set

import pytest

from flake8_project_rules.rules import RuleViolation, check_tree

PROJECT_ROOT = Path(__file__).parents[2]
SAMPLES_DIR = Path(__file__).parent / "samples"

# Name of the dedicated settings section in pyproject.toml.
_CONFIG_SECTION = "flake8_lint_tests"

# Single source of truth: each rule code maps to the sample file(s) that are
# expected to trigger it. Adding a rule means adding one entry here.
RULE_SAMPLES: Dict[str, List[str]] = {
    "X001": ["x001_bare_except.py"],
    "X002": ["x002_broad_exception.py"],
    "X003": ["x003_settings_set.py"],
    "X004": ["x004_muted_exception.py"],
    "X005": ["x005_missing_docstring.py", "x005_structured_test_docstring.py"],
    "X006": ["x006_local_import.py"],
    "X007": ["x007_missing_return_annotation.py"],
    "X008": ["x008_none_return_annotation.py"],
    "X009": ["x009_percent_formatting.py"],
    "X010": ["x010_import_error_suppression.py"],
    "X011": ["x011_union_none.py"],
}


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, List[str]]:
    """Read the ``[tool.flake8_lint_tests]`` section from the project pyproject.toml.

    Returns an empty mapping when the file or section is missing, so the suite
    falls back to "test every rule".
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        return {}
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    section = data.get("tool", {}).get(_CONFIG_SECTION, {})
    return section if isinstance(section, dict) else {}


def active_rule_codes() -> List[str]:
    """Resolve which rule codes to exercise, honouring the include/exclude config.

    :return: rule codes (a subset of :data:`RULE_SAMPLES`) in their canonical
        order, with ``include`` applied as a whitelist and ``exclude`` as a
        blacklist that takes precedence.
    """
    config = _load_config()
    include: Set[str] = set(config.get("include") or [])
    exclude: Set[str] = set(config.get("exclude") or [])

    known = list(RULE_SAMPLES)
    selected = [code for code in known if code in include] if include else list(known)
    return [code for code in selected if code not in exclude]


# Resolved once at collection time so parametrisation reflects the TOML config.
_ACTIVE_CODES: List[str] = active_rule_codes()
_DETECTION_CASES: List[tuple[str, str]] = [
    (code, sample) for code in _ACTIVE_CODES for sample in RULE_SAMPLES[code]
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_new_checker(path: Path) -> List[RuleViolation]:
    """Parse *path* and run the rule engine, returning all violations."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return list(check_tree(tree, str(path), source))


def violation_codes(path: Path) -> Set[str]:
    """Return the set of rule codes found in *path*."""
    return {v.code for v in run_new_checker(path)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("code", "sample"), _DETECTION_CASES)
def test_active_rule_is_detected(code: str, sample: str):
    """
    [Unit] rules: each configured rule fires on its dedicated sample file.

    Scenario:
        Given a rule code that the TOML config keeps active and its sample file
        When the rule engine runs over that sample
        Then the rule code appears in the reported violation set.

    Boundaries:
        - Input: tests/flake8_lint/samples/<sample for the active rule>
        - Rules: the active subset of X001-X011 from [tool.flake8_lint_tests]
        - Excludes: any code dropped by include/exclude is not parametrised here

    On failure, first check:
        - That the sample file still contains the construct the rule targets
        - That the rule implementation in flake8_project_rules.rules still fires
        - That RULE_SAMPLES maps the code to the correct sample file
    """
    codes = violation_codes(SAMPLES_DIR / sample)
    assert code in codes, f"Expected {code} in {sample}, got: {sorted(codes)}"


@pytest.mark.parametrize("code", _ACTIVE_CODES)
def test_active_rule_absent_on_clean_module(code: str):
    """
    [Unit] rules: no configured rule fires on the valid clean module.

    Scenario:
        Given a rule code that the TOML config keeps active
        When the rule engine runs over the intentionally clean module
        Then that rule code is not reported.

    Boundaries:
        - Input: tests/flake8_lint/samples/valid_clean_module.py
        - Rules: the active subset of X001-X011 from [tool.flake8_lint_tests]

    On failure, first check:
        - That valid_clean_module.py has not been accidentally modified
        - That the specific rule is not over-firing on compliant code
    """
    codes = violation_codes(SAMPLES_DIR / "valid_clean_module.py")
    assert code not in codes


def test_valid_clean_module_has_no_active_violations():
    """
    [Unit] rules: clean module produces zero violations among active rules.

    Scenario:
        Given a module that intentionally satisfies all custom rules
        When the rule engine runs
        Then no violation whose code is currently active is reported.

    Boundaries:
        - Input: tests/flake8_lint/samples/valid_clean_module.py
        - Rules: the active subset of X001-X011 from [tool.flake8_lint_tests]

    On failure, first check:
        - That valid_clean_module.py has not been accidentally modified
        - Which specific active rule is firing and why
    """
    active = set(_ACTIVE_CODES)
    violations = [
        v for v in run_new_checker(SAMPLES_DIR / "valid_clean_module.py") if v.code in active
    ]
    assert violations == [], (
        "Expected no violations among active rules but got:\n"
        + "\n".join(f"  {v.code} {v.filename}:{v.lineno} {v.message}" for v in violations)
    )


def test_config_selection_is_consistent_with_rule_table():
    """
    [Unit] config: resolved active rule set is a subset of the known rule table.

    Scenario:
        Given the include/exclude configuration in [tool.flake8_lint_tests]
        When active_rule_codes() resolves the rules to exercise
        Then every resolved code is a known rule and order is preserved.

    Boundaries:
        - Input: pyproject.toml [tool.flake8_lint_tests] include/exclude
        - Real: tomllib parsing of the project pyproject.toml

    On failure, first check:
        - That include/exclude in pyproject.toml only list valid X-codes
        - That RULE_SAMPLES still defines every rule referenced by the config
    """
    active = active_rule_codes()
    assert set(active).issubset(set(RULE_SAMPLES))
    assert active == [code for code in RULE_SAMPLES if code in set(active)]
