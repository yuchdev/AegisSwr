"""Unit tests for :mod:`aegis_swr.claude_code.config`.

Covers both subtask specs' success criteria: subtask 01's field defaults, CSV
env parsing, tool validation, turn/timeout bounds, and empty-env coercion; and
subtask 02's ``permission_mode`` bypass rejection and disposable ``scratch_cwd``
validation matrix.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from loguru import logger

from aegis_swr.claude_code.config import ClaudeCodeConfigError, ClaudeCodeSettings


@pytest.fixture(autouse=True)
def _clear_claude_code_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no ambient ``CLAUDE_CODE_*`` env var leaks into the tests."""
    for key in list(os.environ):
        if key.startswith("CLAUDE_CODE_"):
            monkeypatch.delenv(key, raising=False)


def _capture_logs() -> tuple[list[str], int]:
    """Attach a loguru sink capturing rendered messages; return (records, sink_id)."""
    records: list[str] = []
    sink_id = logger.add(records.append, level="WARNING", format="{message}")
    return records, sink_id


# --- Subtask 01: class shape & defaults -------------------------------------


def test_defaults_no_env():
    """[Unit] claude_code config: defaults construct cleanly with enabled=False.

    Scenario: settings are built with no ``CLAUDE_CODE_*`` env vars set.

    Boundaries: exercises the documented default values only.

    On failure, first check: ``enabled`` must be ``False`` and every documented
    default (binary, tools, turns, timeout, permission mode, scratch cwd) must
    match without raising.
    """
    settings = ClaudeCodeSettings()
    assert settings.enabled is False
    assert settings.binary_path == "claude"
    assert settings.allowed_tools == ["Read", "Grep", "Glob"]
    assert settings.max_turns == 8
    assert settings.request_timeout_s == 120
    assert settings.permission_mode == "default"
    assert settings.scratch_cwd is None


def test_enabled_true_via_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] claude_code config: CLAUDE_CODE_ENABLED=true yields enabled=True.

    Scenario: ``CLAUDE_CODE_ENABLED`` is set to ``true`` with a valid scratch cwd.

    Boundaries: exercises the boolean presence-signal env coercion.

    On failure, first check: ``enabled`` must be ``True``.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    scratch = tmp_path / "scratch"
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", str(scratch))
    settings = ClaudeCodeSettings()
    assert settings.enabled is True


def test_enabled_empty_env_falls_back_to_false(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_ENABLED falls back to False.

    Scenario: ``CLAUDE_CODE_ENABLED`` is set to an empty string (an unset CI secret
    expanding to ``""``).

    Boundaries: regression guard for FIX 2 - an empty bool value must never raise a
    raw pydantic ``bool_parsing`` error and must resolve to the fail-safe default.

    On failure, first check: the ``_coerce_enabled`` mode="before" validator must
    coerce the blank value to ``False`` without raising.
    """
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "")
    settings = ClaudeCodeSettings()
    assert settings.enabled is False


def test_enabled_blank_string_falls_back_to_false():
    """[Unit] claude_code config: a whitespace-only enabled value falls back to False.

    Scenario: ``enabled`` is passed as a whitespace-only string to the constructor.

    Boundaries: regression guard for FIX 2 - the fail-safe direction, an empty
    value must never resolve to ``True``.

    On failure, first check: ``_coerce_enabled`` must return ``False`` for a blank
    string.
    """
    assert ClaudeCodeSettings(enabled="   ").enabled is False


def test_scratch_cwd_error_does_not_leak_resolved_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] claude_code config: a scratch_cwd error omits the resolved path (C13).

    Scenario: ``enabled=True`` with ``scratch_cwd`` pointing at an existing regular
    file whose path carries a distinctive token.

    Boundaries: regression guard for FIX 1 - the resolved absolute path (which can
    carry the home directory and username) must never appear in the error text.

    On failure, first check: the three ``scratch_cwd`` reasons must be value-free.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "SECRET-scratch-token-file"
    target.write_text("x")
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(enabled=True, scratch_cwd=target)
    assert exc.value.field == "scratch_cwd"
    assert "SECRET-scratch-token-file" not in str(exc.value)
    assert str(target.resolve()) not in str(exc.value)


def test_allowed_tools_csv_env_roundtrip(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: a CSV allowed-tools env parses into a list.

    Scenario: ``CLAUDE_CODE_ALLOWED_TOOLS`` is a comma-separated string with spaces.

    Boundaries: exercises the CSV env source splitting.

    On failure, first check: the parsed list must be the trimmed token sequence.
    """
    monkeypatch.setenv("CLAUDE_CODE_ALLOWED_TOOLS", "Read, Grep")
    settings = ClaudeCodeSettings()
    assert settings.allowed_tools == ["Read", "Grep"]


def test_allowed_tools_csv_direct_string():
    """[Unit] claude_code config: a CSV string passed in code parses into a list.

    Scenario: ``allowed_tools`` is passed as a raw comma-separated string.

    Boundaries: exercises the ``mode="before"`` coercion validator.

    On failure, first check: the constructor path must split the string too.
    """
    settings = ClaudeCodeSettings(allowed_tools="Read,Glob")
    assert settings.allowed_tools == ["Read", "Glob"]


def test_unknown_tool_rejected():
    """[Unit] claude_code config: an unrecognised allowed-tool name is rejected.

    Scenario: ``allowed_tools`` includes ``WriteFile``.

    Boundaries: exercises the allowed-tools validator.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``allowed_tools`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(allowed_tools=["Read", "WriteFile"])
    assert exc.value.field == "allowed_tools"


def test_write_tool_warns_not_raises():
    """[Unit] claude_code config: allowing Write warns but does not raise.

    Scenario: ``allowed_tools`` includes ``Write`` while a WARNING sink is attached.

    Boundaries: exercises the soft-warning branch of the tools validator.

    On failure, first check: the value must be kept and a single compromised-
    read-only-mode warning must be emitted.
    """
    records, sink_id = _capture_logs()
    try:
        settings = ClaudeCodeSettings(allowed_tools=["Read", "Write"])
    finally:
        logger.remove(sink_id)
    assert settings.allowed_tools == ["Read", "Write"]
    combined = "\n".join(records)
    assert "Write" in combined
    assert "read-only forensic mode is compromised" in combined
    assert len(records) == 1


def test_max_turns_zero_rejected():
    """[Unit] claude_code config: a non-positive max_turns is rejected.

    Scenario: ``max_turns`` is set to 0.

    Boundaries: exercises the max_turns lower-bound validator.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``max_turns`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(max_turns=0)
    assert exc.value.field == "max_turns"


def test_request_timeout_zero_rejected():
    """[Unit] claude_code config: a non-positive request_timeout_s is rejected.

    Scenario: ``request_timeout_s`` is set to 0.

    Boundaries: exercises the request-timeout validator.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``request_timeout_s`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(request_timeout_s=0)
    assert exc.value.field == "request_timeout_s"


def test_binary_empty_string_falls_back_to_default():
    """[Unit] claude_code config: an empty binary_path falls back to the default.

    Scenario: ``binary_path`` is passed as an empty and a whitespace-only string.

    Boundaries: models an unset CI secret expanding to ``""``.

    On failure, first check: ``binary_path`` must coerce to ``"claude"`` without
    raising.
    """
    assert ClaudeCodeSettings(binary_path="").binary_path == "claude"
    assert ClaudeCodeSettings(binary_path="   ").binary_path == "claude"


def test_binary_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_BINARY env falls back.

    Scenario: ``CLAUDE_CODE_BINARY`` is set to an empty string.

    Boundaries: models the unset-CI-secret case flowing through the env.

    On failure, first check: ``binary_path`` must be ``"claude"``, not empty.
    """
    monkeypatch.setenv("CLAUDE_CODE_BINARY", "")
    assert ClaudeCodeSettings().binary_path == "claude"


def test_binary_custom_path_preserved():
    """[Unit] claude_code config: a non-empty binary_path is preserved verbatim.

    Scenario: ``binary_path`` is set to an absolute path.

    Boundaries: exercises the pass-through branch of the coercion validator.

    On failure, first check: the value must be stored unchanged.
    """
    assert ClaudeCodeSettings(binary_path="/opt/claude").binary_path == "/opt/claude"


def test_request_timeout_reads_documented_env(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: CLAUDE_CODE_REQUEST_TIMEOUT populates the field.

    Scenario: ``CLAUDE_CODE_REQUEST_TIMEOUT`` is set to 90.

    Boundaries: exercises the documented env alias.

    On failure, first check: ``request_timeout_s`` must be 90.
    """
    monkeypatch.setenv("CLAUDE_CODE_REQUEST_TIMEOUT", "90")
    assert ClaudeCodeSettings().request_timeout_s == 90


# --- Subtask 02: permission_mode --------------------------------------------


def test_permission_mode_plan_ok():
    """[Unit] claude_code config: the conservative plan mode is accepted.

    Scenario: ``permission_mode`` is set to ``plan``.

    Boundaries: exercises the permission-mode accept path.

    On failure, first check: the value must be stored verbatim.
    """
    assert ClaudeCodeSettings(permission_mode="plan").permission_mode == "plan"


def test_permission_mode_accept_edits_ok():
    """[Unit] claude_code config: the acceptEdits mode is accepted.

    Scenario: ``permission_mode`` is set to ``acceptEdits``.

    Boundaries: exercises the permission-mode accept path.

    On failure, first check: the value must be stored verbatim.
    """
    assert ClaudeCodeSettings(permission_mode="acceptEdits").permission_mode == "acceptEdits"


def test_permission_mode_bypass_rejected():
    """[Unit] claude_code config: bypassPermissions is rejected.

    Scenario: ``permission_mode`` is set to ``bypassPermissions``.

    Boundaries: exercises the bypass rejection branch.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``permission_mode`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(permission_mode="bypassPermissions")
    assert exc.value.field == "permission_mode"


def test_permission_mode_dangerous_flag_rejected():
    """[Unit] claude_code config: the raw skip-permissions flag is rejected.

    Scenario: ``permission_mode`` is the ``--dangerously-skip-permissions`` string.

    Boundaries: exercises the bypass rejection against the raw flag string.

    On failure, first check: construction must raise ``ClaudeCodeConfigError``.
    """
    with pytest.raises(ClaudeCodeConfigError):
        ClaudeCodeSettings(permission_mode="--dangerously-skip-permissions")


def test_permission_mode_bare_bypass_rejected():
    """[Unit] claude_code config: the bare ``bypass`` token is rejected.

    Scenario: ``permission_mode`` is the bare ``bypass`` string listed in
    ``_BYPASS_PERMISSION_VALUES``.

    Boundaries: exercises the bare-``bypass`` member of the bypass set, which no
    other test covered.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``permission_mode`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(permission_mode="bypass")
    assert exc.value.field == "permission_mode"


def test_permission_mode_bypass_case_insensitive():
    """[Unit] claude_code config: an upper-case bypass value is still rejected.

    Scenario: ``permission_mode`` is ``BYPASSPERMISSIONS``.

    Boundaries: exercises the case-insensitive comparison.

    On failure, first check: construction must raise ``ClaudeCodeConfigError``.
    """
    with pytest.raises(ClaudeCodeConfigError):
        ClaudeCodeSettings(permission_mode="BYPASSPERMISSIONS")


def test_permission_mode_unknown_rejected():
    """[Unit] claude_code config: an unknown non-bypassing mode is rejected.

    Scenario: ``permission_mode`` is ``nonsense``.

    Boundaries: exercises the unknown-mode rejection so a typo cannot degrade
    silently.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``permission_mode`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(permission_mode="nonsense")
    assert exc.value.field == "permission_mode"


# --- Subtask 02: scratch_cwd ------------------------------------------------


def test_scratch_cwd_default_none_when_disabled():
    """[Unit] claude_code config: scratch_cwd defaults to None when disabled.

    Scenario: settings are built with no env and ``enabled=False``.

    Boundaries: exercises the presence-signal-as-falsy default (C5).

    On failure, first check: ``scratch_cwd`` must be ``None`` without raising.
    """
    assert ClaudeCodeSettings().scratch_cwd is None


def test_scratch_cwd_empty_env_coerces_to_none(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_SCRATCH_CWD coerces to None.

    Scenario: ``CLAUDE_CODE_SCRATCH_CWD`` is set to an empty string, backend off.

    Boundaries: models an unset CI secret expanding to ``""``.

    On failure, first check: ``scratch_cwd`` must be ``None`` and construction
    must not raise.
    """
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", "")
    assert ClaudeCodeSettings().scratch_cwd is None


def test_scratch_cwd_whitespace_coerces_to_none():
    """[Unit] claude_code config: a whitespace-only scratch_cwd coerces to None.

    Scenario: ``scratch_cwd`` is passed as a whitespace-only string, backend off.

    Boundaries: exercises the ``mode="before"`` coercion validator directly.

    On failure, first check: ``scratch_cwd`` must be ``None`` without raising.
    """
    assert ClaudeCodeSettings(scratch_cwd="   ").scratch_cwd is None


def test_scratch_cwd_mandatory_when_enabled():
    """[Unit] claude_code config: an enabled backend must set scratch_cwd.

    Scenario: ``enabled=True`` with ``scratch_cwd`` unset.

    Boundaries: exercises the mandatory-when-enabled model validator.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``scratch_cwd`` field.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(enabled=True)
    assert exc.value.field == "scratch_cwd"


def test_scratch_cwd_writable_dir_ok_no_side_effect(tmp_path: Path):
    """[Unit] claude_code config: a writable scratch cwd is accepted, no mkdir.

    Scenario: ``enabled=True`` with ``scratch_cwd`` a not-yet-created subdir of a
    writable temp directory.

    Boundaries: exercises the creatable/writable accept path and the no-side-
    effect contract.

    On failure, first check: construction must not raise and must not create the
    directory.
    """
    target = tmp_path / "scratch"
    settings = ClaudeCodeSettings(enabled=True, scratch_cwd=target)
    assert settings.scratch_cwd == target
    assert not target.exists()


def test_scratch_cwd_existing_writable_dir_ok(tmp_path: Path):
    """[Unit] claude_code config: an existing writable scratch dir is accepted.

    Scenario: ``enabled=True`` with ``scratch_cwd`` an existing temp directory.

    Boundaries: exercises the existing-directory writable branch.

    On failure, first check: construction must not raise.
    """
    settings = ClaudeCodeSettings(enabled=True, scratch_cwd=tmp_path)
    assert settings.scratch_cwd == tmp_path


def test_scratch_cwd_repo_root_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] claude_code config: a scratch cwd at the repo root is rejected.

    Scenario: ``enabled=True`` with ``scratch_cwd`` equal to a directory marked as
    the repository root via a ``.git`` marker.

    Boundaries: exercises the not-repo-root guard using an isolated fake repo so
    the real cwd does not affect the result.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``scratch_cwd`` field.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(enabled=True, scratch_cwd=tmp_path)
    assert exc.value.field == "scratch_cwd"


def test_scratch_cwd_repo_ancestor_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] claude_code config: a scratch cwd that is an ancestor of the repo is rejected.

    Scenario: ``enabled=True`` with a repo root nested under ``scratch_cwd``.

    Boundaries: exercises the ancestor-of-repo-root branch of the guard.

    On failure, first check: construction must raise ``ClaudeCodeConfigError``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.chdir(repo)
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(enabled=True, scratch_cwd=tmp_path)
    assert exc.value.field == "scratch_cwd"


def test_scratch_cwd_existing_file_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] claude_code config: a scratch cwd pointing at a file is rejected.

    Scenario: ``enabled=True`` with ``scratch_cwd`` an existing regular file.

    Boundaries: exercises the not-a-directory invalid-input branch.

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` on
    the ``scratch_cwd`` field.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "afile"
    target.write_text("x")
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(enabled=True, scratch_cwd=target)
    assert exc.value.field == "scratch_cwd"


def test_scratch_cwd_env_string_parsed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """[Unit] claude_code config: a scratch cwd env string parses to a Path.

    Scenario: ``CLAUDE_CODE_SCRATCH_CWD`` is a real writable temp path with the
    backend enabled.

    Boundaries: exercises env-string-to-Path parsing through the enabled path.

    On failure, first check: ``scratch_cwd`` must equal the env-provided path.
    """
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    scratch = tmp_path / "scratch"
    monkeypatch.setenv("CLAUDE_CODE_ENABLED", "true")
    monkeypatch.setenv("CLAUDE_CODE_SCRATCH_CWD", str(scratch))
    settings = ClaudeCodeSettings()
    assert settings.enabled is True
    assert settings.scratch_cwd == scratch


# --- Empty-env coercion audit (FIX 5) ---------------------------------------


def test_auth_mode_empty_env_falls_back_to_auto(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_AUTH_MODE falls back to auto.

    Scenario: ``CLAUDE_CODE_AUTH_MODE`` is set to an empty string (an unset CI
    secret expanding to ``""``).

    Boundaries: regression guard for FIX 5 - the ``Literal`` field would otherwise
    raise a raw ``literal_error`` ``ValidationError`` that ``__init__`` does not
    unwrap, crashing a zero-/partial-config construction.

    On failure, first check: ``_coerce_auth_mode`` must coerce the blank value to
    the licensing-driven default ``"auto"`` without raising.
    """
    monkeypatch.setenv("CLAUDE_CODE_AUTH_MODE", "")
    settings = ClaudeCodeSettings()
    assert settings.auth_mode == "auto"


def test_auth_mode_whitespace_direct_falls_back_to_auto():
    """[Unit] claude_code config: a whitespace-only auth_mode coerces to auto (FIX 5).

    Scenario: ``auth_mode="   "`` is passed directly to the constructor.

    Boundaries: the fail-safe direction of the ``_coerce_auth_mode`` before-validator.

    On failure, first check: ``auth_mode`` must be ``"auto"`` for a blank value.
    """
    settings = ClaudeCodeSettings(auth_mode="   ")
    assert settings.auth_mode == "auto"


def test_max_turns_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_MAX_TURNS falls back to default.

    Scenario: ``CLAUDE_CODE_MAX_TURNS`` is set to an empty string.

    Boundaries: FIX 5 audit - an empty int value must not raise a raw
    ``int_parsing`` ``ValidationError`` at construction.

    On failure, first check: ``max_turns`` must fall back to the default ``8``.
    """
    monkeypatch.setenv("CLAUDE_CODE_MAX_TURNS", "")
    settings = ClaudeCodeSettings()
    assert settings.max_turns == 8


def test_request_timeout_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_REQUEST_TIMEOUT falls back.

    Scenario: ``CLAUDE_CODE_REQUEST_TIMEOUT`` is set to an empty string.

    Boundaries: FIX 5 audit - an empty int value must not crash construction.

    On failure, first check: ``request_timeout_s`` must fall back to ``120``.
    """
    monkeypatch.setenv("CLAUDE_CODE_REQUEST_TIMEOUT", "")
    settings = ClaudeCodeSettings()
    assert settings.request_timeout_s == 120


def test_permission_mode_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_PERMISSION_MODE falls back.

    Scenario: ``CLAUDE_CODE_PERMISSION_MODE`` is set to an empty string.

    Boundaries: FIX 5 audit - an empty value must not be rejected as an "unknown
    mode" and crash construction.

    On failure, first check: ``permission_mode`` must fall back to the fail-safe
    non-bypassing default ``"default"``.
    """
    monkeypatch.setenv("CLAUDE_CODE_PERMISSION_MODE", "")
    settings = ClaudeCodeSettings()
    assert settings.permission_mode == "default"


def test_allowed_tools_empty_env_falls_back_to_default(monkeypatch: pytest.MonkeyPatch):
    """[Unit] claude_code config: an empty CLAUDE_CODE_ALLOWED_TOOLS falls back (FIX 6).

    Scenario: ``CLAUDE_CODE_ALLOWED_TOOLS`` is set to an empty string.

    Boundaries: the empty-secret artifact must fall back to the read-only default
    rather than an empty list (which the FIX 6 guard rejects) or a crash.

    On failure, first check: ``allowed_tools`` must equal the read-only default set
    ``["Read", "Grep", "Glob"]``.
    """
    monkeypatch.setenv("CLAUDE_CODE_ALLOWED_TOOLS", "")
    settings = ClaudeCodeSettings()
    assert settings.allowed_tools == ["Read", "Grep", "Glob"]


def test_allowed_tools_empty_string_direct_falls_back_to_default():
    """[Unit] claude_code config: a blank allowed_tools string coerces to default (FIX 6).

    Scenario: ``allowed_tools="  "`` is passed directly to the constructor.

    Boundaries: the direct-construction blank path mirrors the env path.

    On failure, first check: a blank string must coerce to the read-only default,
    not an empty allowlist.
    """
    settings = ClaudeCodeSettings(allowed_tools="  ")
    assert settings.allowed_tools == ["Read", "Grep", "Glob"]


def test_allowed_tools_explicit_empty_list_rejected():
    """[Unit] claude_code config: an explicit empty allowed_tools list is rejected (FIX 6).

    Scenario: ``allowed_tools=[]`` is passed directly to the constructor.

    Boundaries: the fail-closed guard - an explicit empty allowlist is a
    construction error, never a silently-permissive default.

    On failure, first check: a ``ClaudeCodeConfigError`` for the ``allowed_tools``
    field must be raised (an empty allowlist omits ``--allowedTools`` and grants
    unrestricted access).
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        ClaudeCodeSettings(allowed_tools=[])
    assert exc.value.field == "allowed_tools"
