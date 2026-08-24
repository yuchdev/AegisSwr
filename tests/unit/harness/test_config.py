"""Unit tests for ``HarnessSettings`` (Milestone 0005, Task 01.0.01 + 01.0.02).

Covers the class *shape* (subtask 01: the ``HarnessBackend`` enum, the
``AEGIS_CODE_INTEL_BACKEND`` selector via ``validation_alias``, nested
``default_factory`` composition, empty-selector coercion, and the ``__init__``
unwrap of :class:`HarnessConfigError`) and the C2 selection/ambiguity
*resolution* (subtask 02: ``presence_signals``, ``active_backend``, and the
ambiguity ``model_validator``). The full C2 truth-table matrix is exercised here,
including Milestone 0004's preserved backward-compatibility guarantee that an
``OPENCLAUDE_GRPC_URL``-only environment auto-selects OpenClaude.

All tests source configuration through monkeypatched environment or direct
constructor values; the ``_clean_harness_env`` autouse fixture strips every
relevant variable so no ambient environment leaks in.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from aegis_swr.harness.config import HarnessBackend, HarnessSettings
from aegis_swr.harness.exceptions import HarnessConfigError

#: Env-var name prefixes owned by the three nested families; any variable under
#: one of these can influence a nested settings object built via
#: ``default_factory`` and must be stripped for deterministic isolation.
_HARNESS_ENV_PREFIXES: tuple[str, ...] = (
    "OPENCLAUDE_",
    "CLAUDE_CODE_",
    "OPENHANDS_",
)

#: The standalone selector variable (no family prefix) that also drives selection.
_HARNESS_ENV_EXACT: tuple[str, ...] = ("AEGIS_CODE_INTEL_BACKEND",)


@pytest.fixture(autouse=True)
def _clean_harness_env(monkeypatch: pytest.MonkeyPatch):
    """Strip every harness-relevant env var so tests never see ambient config.

    Because ``HarnessSettings()`` constructs all three nested settings objects via
    ``default_factory``, any ambient sibling variable (e.g.
    ``CLAUDE_CODE_PERMISSION_MODE``) can break an otherwise unrelated harness test.
    This fixture therefore strips **every** variable whose name starts with a known
    family prefix, plus the standalone selector - a prefix-based sweep rather than a
    brittle allowlist, mirroring the sibling ``_clear_claude_code_env`` /
    ``_clear_openhands_env`` fixtures.
    """
    for key in list(os.environ):
        if key.startswith(_HARNESS_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    for var in _HARNESS_ENV_EXACT:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Subtask 01 - class shape
# ---------------------------------------------------------------------------


def test_no_env_constructs_with_defaults():
    """[Unit] config: A no-config HarnessSettings constructs at family defaults.

    Scenario: no env vars set -> constructs, backend is None, each nested object
    holds its family default with its presence signal absent.

    Boundaries: the no-config normal case; default_factory nesting only.

    On failure, first check: default_factory composition and empty-env selector
    coercion.
    """
    settings = HarnessSettings()

    assert settings.backend is None
    assert settings.openclaude.grpc_url is None
    assert settings.claude_code.enabled is False
    assert settings.openhands.server_url is None
    assert settings.active_backend is None
    assert settings.presence_signals == frozenset()


def test_explicit_backend_kwarg_parses_to_enum():
    """[Unit] config: An explicit backend kwarg parses to the HarnessBackend member.

    Scenario: HarnessSettings(backend="openclaude") -> backend is the enum member.

    Boundaries: the constructor selector path (init source, not env).

    On failure, first check: the mode="before" selector validator.
    """
    settings = HarnessSettings(backend="openclaude")

    assert settings.backend is HarnessBackend.OPENCLAUDE


def test_selector_sourced_from_env_alias(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: The selector sources from AEGIS_CODE_INTEL_BACKEND, not a prefix.

    Scenario: AEGIS_CODE_INTEL_BACKEND=claude_code -> backend resolves to the enum.

    Boundaries: the validation_alias env path; no env_prefix on this class.

    On failure, first check: validation_alias wiring (no env_prefix).
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", "claude_code")

    settings = HarnessSettings()

    assert settings.backend is HarnessBackend.CLAUDE_CODE


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_empty_selector_coerces_to_none(monkeypatch: pytest.MonkeyPatch, blank: str):
    """[Unit] config: An empty/whitespace selector coerces to None (auto-select).

    Scenario: AEGIS_CODE_INTEL_BACKEND="" (unset CI secret) -> backend is None, no
    ValidationError.

    Boundaries: the empty/whitespace edge of the selector validator.

    On failure, first check: the empty-selector coercion branch.
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", blank)

    settings = HarnessSettings()

    assert settings.backend is None
    assert settings.active_backend is None


def test_unrecognised_selector_raises_harness_config_error():
    """[Unit] config: An unknown non-empty selector raises HarnessConfigError.

    Scenario: HarnessSettings(backend="not_a_backend") -> HarnessConfigError (not a
    bare Pydantic ValidationError) naming field "backend".

    Boundaries: the invalid-input case; the __init__ ValidationError unwrap.

    On failure, first check: the __init__ ValidationError unwrap and the
    selector reject branch.
    """
    with pytest.raises(HarnessConfigError) as exc_info:
        HarnessSettings(backend="not_a_backend")

    assert exc_info.value.field == "backend"
    assert "not_a_backend" in str(exc_info.value)


def test_nested_family_sourced_only_from_own_env(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: Each nested sub-object sources only its own family's env vars.

    Scenario: OPENCLAUDE_GRPC_URL set -> openclaude.grpc_url set, claude_code and
    openhands stay at defaults; HarnessSettings reads no foreign env var.

    Boundaries: the C1 per-family env isolation via default_factory nesting.

    On failure, first check: default_factory nesting isolates family env.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    settings = HarnessSettings()

    assert settings.openclaude.grpc_url == "localhost:50051"
    assert settings.claude_code.enabled is False
    assert settings.openhands.server_url is None


# ---------------------------------------------------------------------------
# Subtask 02 - C2 truth table
# ---------------------------------------------------------------------------


def test_c2_unset_zero_signals_active_none():
    """[Unit] config: C2 row - selector unset + zero signals -> active_backend None.

    Scenario: no selector, no presence signals -> active_backend is None, no raise
    (unchanged from 0004 C4).

    Boundaries: the zero-signal capability-unavailable row.

    On failure, first check: active_backend's zero-signal return path.
    """
    settings = HarnessSettings()

    assert settings.active_backend is None
    assert settings.presence_signals == frozenset()


def test_c2_unset_one_signal_autoselects_openclaude(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 row - selector unset + one signal -> auto-select (0004 guarantee).

    Scenario: only OPENCLAUDE_GRPC_URL set -> active_backend == "openclaude"; an
    OPENCLAUDE_GRPC_URL-only deployment needs zero further changes.

    Boundaries: the preserved 0004 single-signal auto-select row.

    On failure, first check: presence_signals off openclaude.grpc_url and the
    one-signal branch of active_backend.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    settings = HarnessSettings()

    assert settings.presence_signals == frozenset({"openclaude"})
    assert settings.active_backend == "openclaude"


def test_c2_unset_one_signal_autoselects_claude_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] config: C2 row - selector unset + one claude_code signal -> auto-select.

    Scenario: only CLAUDE_CODE_ENABLED=true (with a valid scratch cwd) ->
    active_backend == "claude_code".

    Boundaries: the claude_code presence signal (enabled is True).

    On failure, first check: presence_signals reads claude_code.enabled.
    """
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", str(tmp_path / "scratch"))

    settings = HarnessSettings()

    assert settings.presence_signals == frozenset({"claude_code"})
    assert settings.active_backend == "claude_code"


def test_c2_unset_one_signal_autoselects_openhands(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 row - selector unset + one openhands signal -> auto-select.

    Scenario: only OPENHANDS_SERVER_URL set -> active_backend == "openhands".

    Boundaries: the openhands presence signal (server_url is not None).

    On failure, first check: presence_signals reads openhands.server_url.
    """
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")

    settings = HarnessSettings()

    assert settings.presence_signals == frozenset({"openhands"})
    assert settings.active_backend == "openhands"


def test_c2_unset_multiple_signals_raises_ambiguity(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 row - selector unset + >1 signal -> HarnessConfigError.

    Scenario: OPENCLAUDE_GRPC_URL and OPENHANDS_SERVER_URL both set with no
    selector -> HarnessConfigError at construction (not ValidationError).

    Boundaries: the sole new failure mode; fail loud, never silently pick one.

    On failure, first check: the _reject_ambiguous_selection model_validator and
    the __init__ unwrap.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")

    with pytest.raises(HarnessConfigError) as exc_info:
        HarnessSettings()

    assert exc_info.value.field == "backend"
    assert exc_info.value.signals == frozenset({"openclaude", "openhands"})


def test_c2_ambiguity_error_leaks_no_payload(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 ambiguity error names only signal names, no URL/token (C13).

    Scenario: two signals with distinctive URL values -> str(error) contains the
    family names but neither URL value.

    Boundaries: the C13 payload-free-exception guarantee.

    On failure, first check: the reason string in _reject_ambiguous_selection
    formats only sorted signal names.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "secret-host:50051")
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://secret-server:3000")

    with pytest.raises(HarnessConfigError) as exc_info:
        HarnessSettings()

    message = str(exc_info.value)
    assert "openclaude" in message
    assert "openhands" in message
    assert "secret-host" not in message
    assert "secret-server" not in message


def test_c2_unset_claude_code_plus_openhands_raises_ambiguity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] config: C2 - the claude_code bool signal accumulates into ambiguity.

    Scenario: CLAUDE_CODE_ENABLED=true (with a valid scratch cwd) plus
    OPENHANDS_SERVER_URL, no selector -> HarnessConfigError naming both families.

    Boundaries: proves the boolean ``enabled is True`` signal enters the frozenset
    equivalently to the two URL-based signals, unlike the URL-only ambiguity tests.

    On failure, first check: presence_signals reads claude_code.enabled and the
    ambiguity model_validator accumulates the bool signal.
    """
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", str(tmp_path / "scratch"))
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")

    with pytest.raises(HarnessConfigError) as exc_info:
        HarnessSettings()

    assert exc_info.value.field == "backend"
    assert exc_info.value.signals == frozenset({"claude_code", "openhands"})


def test_c2_unset_all_three_signals_raises_ambiguity(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] config: C2 - all three signals present with no selector -> ambiguity.

    Scenario: OPENCLAUDE_GRPC_URL, CLAUDE_CODE_ENABLED=true (with scratch cwd), and
    OPENHANDS_SERVER_URL all set, no selector -> HarnessConfigError naming all three.

    Boundaries: the maximal-ambiguity row; the bool signal accumulates alongside
    both URL signals.

    On failure, first check: presence_signals unions all three families and the
    ambiguity model_validator rejects.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", str(tmp_path / "scratch"))
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")

    with pytest.raises(HarnessConfigError) as exc_info:
        HarnessSettings()

    assert exc_info.value.field == "backend"
    assert exc_info.value.signals == frozenset({"openclaude", "claude_code", "openhands"})


def test_c2_selector_set_signal_present(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 row - selector set + its signal present -> that family.

    Scenario: backend=openclaude with OPENCLAUDE_GRPC_URL set -> active_backend
    == "openclaude", no raise.

    Boundaries: the selector-set-and-reachable row.

    On failure, first check: active_backend returns self.backend.value.
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", "openclaude")
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    settings = HarnessSettings()

    assert settings.active_backend == "openclaude"


def test_c2_selector_set_signal_absent_does_not_raise(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 row - selector set + its signal absent -> selector wins, no raise.

    Scenario: backend=claude_code with CLAUDE_CODE_ENABLED unset -> active_backend
    == "claude_code" and NO exception (HarnessUnavailableError is Task 10.0's).

    Boundaries: the selector-set-but-unreachable row deferred to composition time.

    On failure, first check: model_validator short-circuits when backend is set.
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", "claude_code")

    settings = HarnessSettings()

    assert settings.active_backend == "claude_code"
    assert settings.presence_signals == frozenset()


def test_c2_selector_wins_over_different_family_signal(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: C2 - selector set while a different family's signal is present.

    Scenario: backend=openhands but only OPENCLAUDE_GRPC_URL is set ->
    active_backend returns the selected "openhands", no HarnessConfigError.

    Boundaries: the selector-wins edge - a set selector is never ambiguous.

    On failure, first check: active_backend prefers self.backend over signals.
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", "openhands")
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    settings = HarnessSettings()

    assert settings.active_backend == "openhands"
    assert settings.presence_signals == frozenset({"openclaude"})


def test_selector_set_with_multiple_signals_not_ambiguous(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: A set selector suppresses the ambiguity check entirely.

    Scenario: backend=openclaude with two other signals present -> no
    HarnessConfigError; active_backend is the selected family.

    Boundaries: a set selector bypasses _reject_ambiguous_selection.

    On failure, first check: the model_validator's backend-is-not-None guard.
    """
    monkeypatch.setenv("AEGIS_CODE_INTEL_BACKEND", "openclaude")
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")
    monkeypatch.setenv("OPENHANDS_SERVER_URL", "http://localhost:3000")

    settings = HarnessSettings()

    assert settings.active_backend == "openclaude"


def test_active_backend_returns_str_not_enum(monkeypatch: pytest.MonkeyPatch):
    """[Unit] config: active_backend returns a plain str, never a HarnessBackend.

    Scenario: an active backend resolves -> active_backend is a str instance and
    not a HarnessBackend member, so Task 10.0 need not import the enum.

    Boundaries: the return-type contract of active_backend.

    On failure, first check: active_backend returns .value, not the enum member.
    """
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    settings = HarnessSettings()

    active = settings.active_backend
    assert isinstance(active, str)
    assert not isinstance(active, HarnessBackend)


# ---------------------------------------------------------------------------
# C3 isolation boundary
# ---------------------------------------------------------------------------


def _imports_harness_config(package_dir: Path) -> list[Path]:
    """Return files under *package_dir* that import ``HarnessSettings`` (C3).

    :param package_dir: A source package directory to scan.
    :return: The offending file paths, empty when the boundary holds.
    """
    offenders: list[Path] = []
    for py_file in package_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "aegis_swr.harness.config":
                offenders.append(py_file)
            elif isinstance(node, ast.Import) and any(alias.name == "aegis_swr.harness.config" for alias in node.names):
                offenders.append(py_file)
    return offenders


def test_harness_settings_not_imported_by_isolated_packages():
    """[Unit] config: core/views/code_intel never import HarnessSettings (C3).

    Scenario: static AST scan of the three isolated packages -> none import
    aegis_swr.harness.config.

    Boundaries: the C3 module-isolation invariant, enforced statically.

    On failure, first check: the offending package's import of
    aegis_swr.harness.config (composition root and CLI only).
    """
    src_root = Path(__file__).resolve().parents[3] / "src" / "aegis_swr"
    for package in ("core", "views", "code_intel"):
        package_dir = src_root / package
        if not package_dir.exists():
            continue
        assert _imports_harness_config(package_dir) == []


def _imports_package(package_dir: Path, forbidden_root: str) -> list[Path]:
    """Return files under *package_dir* that import ``forbidden_root`` (C3).

    :param package_dir: A source package directory to scan.
    :param forbidden_root: The dotted package prefix (e.g. ``aegis_swr.openhands``)
        no file under *package_dir* may import.
    :return: The offending file paths, empty when the boundary holds.
    """
    prefix = f"{forbidden_root}."
    offenders: list[Path] = []
    for py_file in package_dir.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module == forbidden_root or node.module.startswith(prefix):
                    offenders.append(py_file)
            elif isinstance(node, ast.Import) and any(
                alias.name == forbidden_root or alias.name.startswith(prefix) for alias in node.names
            ):
                offenders.append(py_file)
    return offenders


def test_backend_packages_do_not_import_siblings():
    """[Unit] config: no backend package imports a sibling backend package (C3).

    Scenario: static AST scan of each backend package -> none import another backend
    family's package (claude_code must not import openhands or openclaude, and so on).

    Boundaries: the C3 per-family isolation invariant across sibling backends,
    enforced statically as the existing import-leaf scans do.

    On failure, first check: the offending backend's cross-family import - families
    are wired together only by the harness composition root, never sideways.
    """
    src_root = Path(__file__).resolve().parents[3] / "src" / "aegis_swr"
    backends = ("openclaude", "claude_code", "openhands")
    for package in backends:
        package_dir = src_root / package
        if not package_dir.exists():
            continue
        for sibling in backends:
            if sibling == package:
                continue
            offenders = _imports_package(package_dir, f"aegis_swr.{sibling}")
            assert offenders == [], f"{package} imports sibling backend {sibling}: {offenders}"
