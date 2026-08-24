"""Direct, config-driven tests for the Flake8 rule engine (flake8_project_rules.rules).

Each custom rule ``X001``..``X011`` is paired with a dedicated sample file under
``tests/flake8_lint/samples/``. Instead of one hand-written test per rule, the
suite is parametrised over a single source of truth (:data:`RULE_SAMPLES`) and
the set of rules it actually exercises is **configurable from a TOML file**.

Configuration lives in its own section of the project ``pyproject.toml``::

    [tool.flake8_lint_tests]
    select = ["X001", "X002"]   # whitelist: when non-empty, only these run
    ignore = ["X011"]           # blacklist: removed after select is applied
    allow_noqa = true           # False disables all `# noqa` suppression

Resolution rules (see ``tests/flake8_lint/config.py`` for the shared
implementation, also used by ``test_project_lint.py``):

* When ``select`` is empty/absent, every known rule is selected.
* When ``select`` is non-empty, only the listed codes are selected.
* ``ignore`` is always subtracted last, so it wins over ``select``.
* Unknown codes in either list are ignored (they cannot match a sample).
* ``allow_noqa`` (default ``True``) is a global switch: when ``False``, every
  detection test runs as if no ``# noqa`` comment were present anywhere.

With no section present, the default is "test every rule", matching the
previous behaviour.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from flake8_project_rules.rules import RuleViolation, check_tree
from tests.flake8_lint.config import active_rule_codes, allow_noqa, is_noqa_allowed_for_file

SAMPLES_DIR = Path(__file__).parent / "samples"

# Single source of truth: each rule code maps to the sample file(s) that are
# expected to trigger it. Adding a rule means adding one entry here and to
# tests/flake8_lint/config.py::KNOWN_RULE_CODES.
RULE_SAMPLES: dict[str, list[str]] = {
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


# Resolved once at collection time so parametrisation reflects the TOML config.
# Passing RULE_SAMPLES' own keys (rather than config.KNOWN_RULE_CODES) keeps
# this suite's parametrisation scoped to rules that actually have a sample.
_ACTIVE_CODES: list[str] = active_rule_codes(list(RULE_SAMPLES))
_DETECTION_CASES: list[tuple[str, str]] = [(code, sample) for code in _ACTIVE_CODES for sample in RULE_SAMPLES[code]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_new_checker(path: Path) -> list[RuleViolation]:
    """Parse *path* and run the rule engine, returning all violations.

    Honours ``[tool.flake8_lint_tests] allow_noqa``: when the config disables
    it, every violation is reported regardless of any ``# noqa`` comment.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return list(check_tree(tree, str(path), source, apply_noqa=allow_noqa()))


def violation_codes(path: Path) -> set[str]:
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
        - Excludes: any code dropped by select/ignore is not parametrised here

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
    violations = [v for v in run_new_checker(SAMPLES_DIR / "valid_clean_module.py") if v.code in active]
    assert violations == [], "Expected no violations among active rules but got:\n" + "\n".join(
        f"  {v.code} {v.filename}:{v.lineno} {v.message}" for v in violations
    )


@pytest.mark.parametrize(
    ("comment", "suppressed"),
    [
        ("# noqa", True),
        ("# noqa: X002", True),
        ("# noqa: X001, X002", True),
        ("# noqa:X002", True),
        ("# noqa: BLE001, X002 - one bad subscriber must not block delivery", True),
        ("# noqa: X001", False),
        ("# noqa: BLE001", False),
        ("", False),
    ],
)
def test_noqa_comment_suppresses_matching_violation(comment: str, suppressed: bool):
    """
    [Unit] rules: a trailing # noqa comment suppresses the matching X-code.

    Scenario:
        Given source with an ``except Exception`` handler (X002) whose line
        carries the parametrised ``# noqa`` comment
        When the rule engine runs over the source with noqa filtering active
        Then X002 is dropped exactly when the comment covers it (bare noqa or a
        code list including X002) and retained otherwise.

    Boundaries:
        - Real: AST parsing, check_tree noqa filter
        - Rules: X002 broad-exception detection plus noqa suppression
        - Excludes: flake8's own multi-line/logical-line noqa nuances

    On failure, first check:
        - The _NOQA_RE regex and _is_noqa_suppressed logic in rules.py
        - That the violating line number lines up with the noqa comment line
        - That source (not just the AST) is passed into check_tree
    """
    source = "\n".join(
        [
            "def handler():",
            "    try:",
            "        risky()",
            f"    except Exception:  {comment}".rstrip(),
            "        recover()",
        ]
    )
    tree = ast.parse(source, filename="<noqa-test>")
    codes = {v.code for v in check_tree(tree, "<noqa-test>", source)}
    assert ("X002" not in codes) is suppressed


def test_noqa_filter_requires_source():
    """
    [Unit] rules: without source, noqa comments cannot suppress a violation.

    Scenario:
        Given source with a ``# noqa: X002`` on the ``except Exception`` line
        When check_tree runs with source omitted (source=None)
        Then X002 is still reported, because noqa filtering needs the raw text.

    Boundaries:
        - Real: AST parsing, check_tree with source=None
        - Rules: X002 broad-exception detection
        - Excludes: the noqa suppression path (inactive without source)

    On failure, first check:
        - That check_tree only filters when source is not None
        - That _check_broad_exception still fires on the AST alone
    """
    source = "\n".join(
        [
            "def handler():",
            "    try:",
            "        risky()",
            "    except Exception:  # noqa: X002",
            "        recover()",
        ]
    )
    tree = ast.parse(source, filename="<noqa-test>")
    codes = {v.code for v in check_tree(tree, "<noqa-test>", None)}
    assert "X002" in codes


def test_apply_noqa_false_disables_noqa_suppression():
    """
    [Unit] rules: apply_noqa=False reports every violation, noqa or not.

    Scenario:
        Given source with a bare ``# noqa`` on the ``except Exception`` line
        When check_tree runs with source provided but apply_noqa=False (the
        state ``[tool.flake8_lint_tests] allow_noqa = false`` forces)
        Then X002 is still reported, because noqa filtering is disabled
        wholesale regardless of the comment.

    Boundaries:
        - Real: AST parsing, check_tree with apply_noqa=False
        - Rules: X002 broad-exception detection
        - Excludes: config.allow_noqa() itself (see test_plugin_direct's
          run_new_checker, which is the thing that actually reads the TOML)

    On failure, first check:
        - That check_tree's apply_noqa flag gates the noqa filter, not just
          the presence of source
        - That ProjectRulesPlugin/run_new_checker forward allow_noqa() into
          apply_noqa consistently
    """
    source = "\n".join(
        [
            "def handler():",
            "    try:",
            "        risky()",
            "    except Exception:  # noqa",
            "        recover()",
        ]
    )
    tree = ast.parse(source, filename="<noqa-test>")
    codes = {v.code for v in check_tree(tree, "<noqa-test>", source, apply_noqa=False)}
    assert "X002" in codes


def test_config_selection_is_consistent_with_rule_table():
    """
    [Unit] config: resolved active rule set is a subset of the known rule table.

    Scenario:
        Given the select/ignore configuration in [tool.flake8_lint_tests]
        When active_rule_codes() resolves the rules to exercise
        Then every resolved code is a known rule and order is preserved.

    Boundaries:
        - Input: pyproject.toml [tool.flake8_lint_tests] select/ignore
        - Real: tomllib parsing of the project pyproject.toml

    On failure, first check:
        - That select/ignore in pyproject.toml only list valid X-codes
        - That RULE_SAMPLES still defines every rule referenced by the config
    """
    active = active_rule_codes(list(RULE_SAMPLES))
    assert set(active).issubset(set(RULE_SAMPLES))
    assert active == [code for code in RULE_SAMPLES if code in set(active)]


def test_is_noqa_allowed_default(monkeypatch):
    """
    [Unit] config: when both lists are empty and allow_noqa is true, noqa is allowed anywhere.

    Scenario:
        Given a configuration with allow_noqa=True, noqa_allowed=[], and noqa_forbidden=[]
        When checking whether noqa is permitted for files in the project
        Then is_noqa_allowed_for_file returns True for any file.

    Boundaries:
        - Input: mock config dictionary via monkeypatch
        - Real: tests.flake8_lint.config.is_noqa_allowed_for_file

    On failure, first check:
        - That empty noqa_allowed and noqa_forbidden default to allowing all files
        - That allow_noqa defaults to True
    """
    monkeypatch.setattr(
        "tests.flake8_lint.config.load_config",
        lambda: {"allow_noqa": True, "noqa_allowed": [], "noqa_forbidden": []},
    )
    assert is_noqa_allowed_for_file("src/aegis_swr/core/events.py") is True
    assert is_noqa_allowed_for_file("tests/unit/test_cli.py") is True


def test_is_noqa_allowed_whitelist(monkeypatch):
    """
    [Unit] config: when noqa_allowed is non-empty, unlisted files cannot suppress via noqa.

    Scenario:
        Given a configuration with allow_noqa=True and noqa_allowed restricting to a specific directory
        When checking whether noqa is permitted for listed and unlisted files
        Then is_noqa_allowed_for_file returns True only for matching files and False for unlisted files.

    Boundaries:
        - Input: mock config dictionary via monkeypatch with noqa_allowed set
        - Real: tests.flake8_lint.config.is_noqa_allowed_for_file

    On failure, first check:
        - That noqa_allowed whitelist filters out non-matching paths
        - That directory prefix matching works correctly
    """
    monkeypatch.setattr(
        "tests.flake8_lint.config.load_config",
        lambda: {
            "allow_noqa": True,
            "noqa_allowed": ["src/aegis_swr/core/"],
            "noqa_forbidden": [],
        },
    )
    assert is_noqa_allowed_for_file("src/aegis_swr/core/events.py") is True
    assert is_noqa_allowed_for_file("src/aegis_swr/cli/commands.py") is False


def test_is_noqa_allowed_blacklist_wins(monkeypatch):
    """
    [Unit] config: entries in noqa_forbidden take precedence over noqa_allowed.

    Scenario:
        Given a configuration with a broad noqa_allowed and a specific file in noqa_forbidden
        When checking whether noqa is permitted for the forbidden file vs other allowed files
        Then is_noqa_allowed_for_file returns False for the forbidden file and True for allowed files.

    Boundaries:
        - Input: mock config dictionary via monkeypatch with overlapping allowed and forbidden paths
        - Real: tests.flake8_lint.config.is_noqa_allowed_for_file

    On failure, first check:
        - That noqa_forbidden takes precedence over noqa_allowed
        - That un-blacklisted files in the whitelist remain allowed
    """
    monkeypatch.setattr(
        "tests.flake8_lint.config.load_config",
        lambda: {
            "allow_noqa": True,
            "noqa_allowed": ["src/aegis_swr/"],
            "noqa_forbidden": ["src/aegis_swr/core/events.py"],
        },
    )
    assert is_noqa_allowed_for_file("src/aegis_swr/cli/commands.py") is True
    assert is_noqa_allowed_for_file("src/aegis_swr/core/events.py") is False


def test_is_noqa_allowed_global_false_overrides_all(monkeypatch):
    """
    [Unit] config: when allow_noqa = false, noqa is forbidden regardless of whitelist.

    Scenario:
        Given a configuration with allow_noqa=False and files in noqa_allowed
        When checking whether noqa is permitted for any file
        Then is_noqa_allowed_for_file returns False for all files.

    Boundaries:
        - Input: mock config dictionary via monkeypatch with allow_noqa=False
        - Real: tests.flake8_lint.config.is_noqa_allowed_for_file

    On failure, first check:
        - That allow_noqa=False overrides any noqa_allowed configuration
    """
    monkeypatch.setattr(
        "tests.flake8_lint.config.load_config",
        lambda: {
            "allow_noqa": False,
            "noqa_allowed": ["src/aegis_swr/core/events.py"],
            "noqa_forbidden": [],
        },
    )
    assert is_noqa_allowed_for_file("src/aegis_swr/core/events.py") is False


def test_is_noqa_allowed_synthetic_path():
    """
    [Unit] config: synthetic paths default to allowed when global switch is true.

    Scenario:
        Given synthetic paths such as <stdin> or <noqa-test>
        When is_noqa_allowed_for_file evaluates them
        Then it returns True without error.

    Boundaries:
        - Input: string paths enclosed in angle brackets
        - Real: tests.flake8_lint.config.is_noqa_allowed_for_file

    On failure, first check:
        - That angle-bracketed synthetic paths are handled gracefully
    """
    assert is_noqa_allowed_for_file("<stdin>") is True
    assert is_noqa_allowed_for_file("<noqa-test>") is True
