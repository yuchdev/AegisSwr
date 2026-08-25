"""Unit tests for Milestone 0005 Task 04.0 - Claude Code auth modes (C7).

Scenario: the ``auth_mode`` construction-time invariants (subtask 01), the
credential-resolution helper and the spawn-time filtered environment / TOCTOU
re-check (subtask 02 + threat-model Finding 1), and the startup auth-probe and
its closed-set failure taxonomy (subtask 03) are exercised in isolation.

Boundaries: unit - no real ``claude`` binary is ever spawned;
``asyncio.create_subprocess_exec`` and ``ClaudeCodeProcess`` / ``parse_stream``
are replaced by fakes. ``os.environ`` is mutated only through ``monkeypatch``.

On failure: the C7 precedence chain, the two-error distinction, the secrecy
discipline (C13), or the Task 03.0 behavioural freeze for ``auto`` drifted from
contract.
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from loguru import logger

from aegis_swr.claude_code import tool as tool_mod
from aegis_swr.claude_code.config import ClaudeCodeConfigError, ClaudeCodeSettings
from aegis_swr.claude_code.events import ClaudeCodeAuthFailed
from aegis_swr.claude_code.exceptions import ClaudeCodeUnavailableError
from aegis_swr.claude_code.process import (
    ClaudeCodeProcess,
    ClaudeCodeStreamResult,
    ClaudeCodeUsage,
    build_argv,
    resolve_credential,
)
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus

#: Credential env vars that outrank a subscription login, cleared before each test.
_OUTRANKING = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "AWS_BEARER_TOKEN_BEDROCK")
#: The subscription OAuth token variable.
_OAUTH = "CLAUDE_CODE_OAUTH_TOKEN"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Strip every credential and ``CLAUDE_CODE_*`` var so no ambient value leaks in.

    :param monkeypatch: the pytest monkeypatch fixture.
    """
    for key in (*_OUTRANKING, _OAUTH):
        monkeypatch.delenv(key, raising=False)
    for key in list(os.environ):
        if key.startswith("CLAUDE_CODE_"):
            monkeypatch.delenv(key, raising=False)


def _capture_logs() -> tuple[list[str], int]:
    """Attach a TRACE loguru sink capturing rendered messages.

    :return: the captured-records list and the sink id to remove afterwards.
    """
    records: list[str] = []
    sink_id = logger.add(records.append, level="TRACE", format="{message}")
    return records, sink_id


# ---------------------------------------------------------------------------
# Subtask 01 - auth_mode field + subscription-mode rejection validator
# ---------------------------------------------------------------------------


def test_auth_mode_defaults_to_auto():
    """[Unit] auth: auth_mode defaults to ``auto`` and constructs cleanly.

    Scenario: settings are built with no ``CLAUDE_CODE_AUTH_MODE`` set.

    Boundaries: exercises the documented default only.

    On failure, first check: the default must be ``"auto"`` (the licensing-driven
    opt-in default) and construction must not raise.
    """
    settings = ClaudeCodeSettings()
    assert settings.auth_mode == "auto"
    assert settings.bare is False


def test_auth_mode_bogus_value_rejected():
    """[Unit] auth: an unknown auth_mode value is rejected by the Literal type.

    Scenario: ``auth_mode="bogus"`` is passed to the constructor.

    Boundaries: exercises the ``Literal`` field type only.

    On failure, first check: a validation error must be raised (``Literal`` rejects
    the value).
    """
    with pytest.raises((ClaudeCodeConfigError, ValueError)):
        ClaudeCodeSettings(auth_mode="bogus")


def test_subscription_without_outranking_creds_constructs():
    """[Unit] auth: subscription mode with no API-key credential constructs.

    Scenario: ``auth_mode="subscription"`` with neither ``ANTHROPIC_API_KEY`` nor
    ``ANTHROPIC_AUTH_TOKEN`` set.

    Boundaries: exercises the subscription validator's clean path.

    On failure, first check: construction must not raise when no outranking
    credential is present.
    """
    settings = ClaudeCodeSettings(auth_mode="subscription")
    assert settings.auth_mode == "subscription"


@pytest.mark.parametrize("var", ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])
def test_subscription_rejects_present_outranking_credential(monkeypatch: pytest.MonkeyPatch, var: str):
    """[Unit] auth: subscription mode rejects a present outranking API credential.

    Scenario: ``auth_mode="subscription"`` while *var* is set to a credential value
    in the environment the subprocess would inherit.

    Boundaries: exercises the construction-time rejection validator (C7 ranks 2-3).

    On failure, first check: a ``ClaudeCodeConfigError`` must be raised, its message
    must name *var* but contain **no** part of the credential value (C13).
    """
    cred_value = "outranking-key-material-000"
    monkeypatch.setenv(var, cred_value)
    with pytest.raises(ClaudeCodeConfigError) as excinfo:
        ClaudeCodeSettings(auth_mode="subscription")
    assert var in str(excinfo.value)
    assert cred_value not in str(excinfo.value)


@pytest.mark.parametrize("var", ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])
def test_subscription_empty_outranking_credential_is_absent(monkeypatch: pytest.MonkeyPatch, var: str):
    """[Unit] auth: an empty outranking credential is treated as absent.

    Scenario: ``auth_mode="subscription"`` while *var* is set to the empty string
    (the classic unset-CI-secret artifact).

    Boundaries: exercises the empty==absent coercion in the subscription validator.

    On failure, first check: construction must **not** raise - an empty value is
    neither an outranking credential nor a working one.
    """
    monkeypatch.setenv(var, "")
    settings = ClaudeCodeSettings(auth_mode="subscription")
    assert settings.auth_mode == "subscription"


def test_api_key_mode_ignores_present_credential(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: api_key mode constructs even with ANTHROPIC_API_KEY present.

    Scenario: ``auth_mode="api_key"`` while ``ANTHROPIC_API_KEY`` is set.

    Boundaries: proves the presence check is scoped to subscription mode only.

    On failure, first check: construction must not raise - api_key mode *uses* the
    host key, so its presence is expected, not rejected.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-material-abc")
    settings = ClaudeCodeSettings(auth_mode="api_key")
    assert settings.auth_mode == "api_key"


def test_auto_mode_adds_no_validation_with_credential_present(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: auto mode is a validation no-op even with a credential present.

    Scenario: default ``auth_mode="auto"`` while ``ANTHROPIC_API_KEY`` is set (the
    Task 03.0 behavioural-freeze guard).

    Boundaries: proves the subscription validator never fires outside subscription.

    On failure, first check: construction must not raise and ``auth_mode`` must be
    ``"auto"`` - auto adds no credential branching (regression guard for C7 freeze).
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-material-abc")
    settings = ClaudeCodeSettings()
    assert settings.auth_mode == "auto"


def test_subscription_with_bare_rejected():
    """[Unit] auth: subscription + bare is rejected at construction (C7).

    Scenario: ``auth_mode="subscription"`` combined with ``bare=True``.

    Boundaries: exercises the ``--bare`` exclusion rule at the settings layer.

    On failure, first check: a ``ClaudeCodeConfigError`` must be raised - bare mode
    never reads OAuth/login credentials, so it is unusable for subscription.
    """
    with pytest.raises(ClaudeCodeConfigError) as excinfo:
        ClaudeCodeSettings(auth_mode="subscription", bare=True)
    assert "bare" in str(excinfo.value).lower()


def test_api_key_with_bare_constructs():
    """[Unit] auth: api_key + bare constructs (bare is eligible only here).

    Scenario: ``auth_mode="api_key"`` with ``bare=True``.

    Boundaries: exercises the bare toggle's permitted mode.

    On failure, first check: construction must not raise - ``--bare`` is allowed in
    api_key mode for reproducibility.
    """
    settings = ClaudeCodeSettings(auth_mode="api_key", bare=True)
    assert settings.bare is True


def test_auto_with_bare_rejected():
    """[Unit] auth: bare=True under the default auto mode is rejected (FIX 3).

    Scenario: ``bare=True`` with the default ``auth_mode="auto"`` (no explicit mode).

    Boundaries: exercises the ``_validate_bare_requires_api_key`` model validator -
    the gap where ``auto`` previously accepted ``bare`` silently and then dropped it.

    On failure, first check: a ``ClaudeCodeConfigError`` must be raised naming the
    ``bare`` field and the required ``api_key`` mode - silent-accept-then-drop is the
    exact failure class C7 exists to eliminate.
    """
    with pytest.raises(ClaudeCodeConfigError) as excinfo:
        ClaudeCodeSettings(bare=True)
    assert excinfo.value.field == "bare"
    assert "api_key" in str(excinfo.value)


def test_bare_never_reaches_argv_under_auto():
    """[Unit] auth: even a forced bare flag never yields --bare under auto (FIX 3).

    Scenario: construction rejects auto+bare, so the validator is bypassed via
    ``object.__setattr__`` to force ``bare=True`` onto an ``auto`` settings object;
    the resolver and argv builder are then exercised.

    Boundaries: exercises ``resolve_credential`` / ``build_argv`` defence-in-depth -
    ``--bare`` is an ``api_key``-only concern and must never appear under ``auto``.

    On failure, first check: ``--bare`` must be absent from both ``extra_argv`` and
    the built argv regardless of a forced ``bare`` flag under ``auto``.
    """
    settings = ClaudeCodeSettings(auth_mode="auto")
    object.__setattr__(settings, "bare", True)

    cred = resolve_credential(settings)
    assert "--bare" not in cred.extra_argv
    assert "--bare" not in build_argv(settings)


# ---------------------------------------------------------------------------
# Subtask 02 - resolve_credential matrix
# ---------------------------------------------------------------------------


def test_resolve_auto_is_a_no_op():
    """[Unit] auth: resolve_credential(auto) is a genuine no-op.

    Scenario: ``auth_mode="auto"`` is resolved.

    Boundaries: exercises the auto branch of the resolver.

    On failure, first check: ``extra_argv`` and ``env_passthrough`` must both be
    empty and ``relies_on_stored_login`` must be ``False`` - preserving Task 03.0.
    """
    cred = resolve_credential(ClaudeCodeSettings(auth_mode="auto"))
    assert cred.mode == "auto"
    assert cred.extra_argv == ()
    assert cred.env_passthrough == ()
    assert cred.relies_on_stored_login is False


def test_resolve_subscription_with_oauth_token(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: subscription with CLAUDE_CODE_OAUTH_TOKEN forwards it by name.

    Scenario: ``auth_mode="subscription"`` with ``CLAUDE_CODE_OAUTH_TOKEN`` set.

    Boundaries: exercises the token-present branch of the resolver.

    On failure, first check: ``env_passthrough`` must be ``("CLAUDE_CODE_OAUTH_TOKEN",)``
    (a name, not a value), ``relies_on_stored_login`` must be ``False``, and
    ``--bare`` must be absent from ``extra_argv``.
    """
    monkeypatch.setenv(_OAUTH, "oauth-material-value")
    cred = resolve_credential(ClaudeCodeSettings(auth_mode="subscription"))
    assert cred.env_passthrough == (_OAUTH,)
    assert cred.relies_on_stored_login is False
    assert "--bare" not in cred.extra_argv
    # The value must never be materialised into the resolved credential (C13).
    assert "oauth-material-value" not in repr(cred)


def test_resolve_subscription_without_token_relies_on_stored_login():
    """[Unit] auth: subscription with no token relies on the stored login session.

    Scenario: ``auth_mode="subscription"`` with ``CLAUDE_CODE_OAUTH_TOKEN`` unset.

    Boundaries: exercises the stored-login branch of the resolver.

    On failure, first check: ``relies_on_stored_login`` must be ``True``,
    ``env_passthrough`` must be empty (session lives in the credential store), and
    ``--bare`` must be absent.
    """
    cred = resolve_credential(ClaudeCodeSettings(auth_mode="subscription"))
    assert cred.relies_on_stored_login is True
    assert cred.env_passthrough == ()
    assert "--bare" not in cred.extra_argv


def test_resolve_api_key_permits_bare():
    """[Unit] auth: api_key mode appends --bare when requested and never an OAuth token.

    Scenario: ``auth_mode="api_key"`` with ``bare=True``.

    Boundaries: exercises the api_key branch of the resolver.

    On failure, first check: ``--bare`` must be in ``extra_argv`` and
    ``CLAUDE_CODE_OAUTH_TOKEN`` must never be forwarded in api_key mode.
    """
    cred = resolve_credential(ClaudeCodeSettings(auth_mode="api_key", bare=True))
    assert cred.extra_argv == ("--bare",)
    assert _OAUTH not in cred.env_passthrough


def test_resolve_api_key_without_bare_omits_flag():
    """[Unit] auth: api_key mode omits --bare unless explicitly requested.

    Scenario: ``auth_mode="api_key"`` with ``bare=False`` (the default).

    Boundaries: exercises the api_key no-bare branch of the resolver.

    On failure, first check: ``extra_argv`` must be empty - the resolver only
    *permits* ``--bare``, it does not force it.
    """
    cred = resolve_credential(ClaudeCodeSettings(auth_mode="api_key"))
    assert cred.extra_argv == ()


def test_subscription_never_emits_bare_even_conceptually():
    """[Unit] auth: --bare is absent from every subscription resolution (C7).

    Scenario: subscription mode resolved without an OAuth token.

    Boundaries: exercises the defence-in-depth ``--bare`` omission in the resolver.

    On failure, first check: ``--bare`` must never appear in ``extra_argv`` for a
    subscription resolution, regardless of the token state.
    """
    without = resolve_credential(ClaudeCodeSettings(auth_mode="subscription"))
    assert "--bare" not in without.extra_argv


# ---------------------------------------------------------------------------
# Finding 1 - explicit filtered child env + spawn-time TOCTOU re-check
# ---------------------------------------------------------------------------


def test_build_child_env_auto_returns_none():
    """[Unit] auth: auto mode inherits the ambient env (env=None) unchanged.

    Scenario: ``ClaudeCodeProcess`` in ``auto`` mode builds its child env.

    Boundaries: exercises ``_build_child_env`` directly for the no-op modes.

    On failure, first check: ``_build_child_env`` must return ``None`` so
    ``create_subprocess_exec`` inherits ``os.environ`` bit-for-bit (Task 03.0).
    """
    settings = ClaudeCodeSettings(auth_mode="auto")
    proc = ClaudeCodeProcess(settings, "task")
    assert proc._build_child_env(resolve_credential(settings)) is None


def test_build_child_env_api_key_returns_none(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: api_key mode also inherits the ambient env unchanged.

    Scenario: ``ClaudeCodeProcess`` in ``api_key`` mode builds its child env with
    ``ANTHROPIC_API_KEY`` present.

    Boundaries: exercises ``_build_child_env`` for the api_key mode.

    On failure, first check: ``_build_child_env`` must return ``None`` - api_key
    mode does not strip the host key (it uses it).
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-material")
    settings = ClaudeCodeSettings(auth_mode="api_key")
    proc = ClaudeCodeProcess(settings, "task")
    assert proc._build_child_env(resolve_credential(settings)) is None


def test_build_child_env_subscription_strips_outranking_keeps_platform(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: subscription env strips outranking creds, keeps platform + token.

    Scenario: subscription mode with ``CLAUDE_CODE_OAUTH_TOKEN`` and platform vars
    set but no outranking credential present at construction; the child env is built
    fresh.

    Boundaries: exercises ``_build_child_env`` filtering with a token present.

    On failure, first check: the returned env must omit every outranking credential
    while retaining the platform vars (``PATH``/``SYSTEMROOT``/``USERPROFILE``) the
    Windows child needs and the ``CLAUDE_CODE_OAUTH_TOKEN`` winner.
    """
    monkeypatch.setenv(_OAUTH, "the-oauth-material")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("USERPROFILE", r"C:\Users\svc")
    settings = ClaudeCodeSettings(auth_mode="subscription")
    proc = ClaudeCodeProcess(settings, "task")

    child_env = proc._build_child_env(resolve_credential(settings))

    assert child_env is not None
    # The outranking creds and the C7 rank-1 routing toggles (FIX 4) are never
    # forwarded; when present they trip the re-check instead (see the TOCTOU test).
    for var in (*_OUTRANKING, "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
        assert var not in child_env
    assert child_env["PATH"] == "/usr/bin:/bin"
    assert child_env["SYSTEMROOT"] == r"C:\Windows"
    assert child_env["USERPROFILE"] == r"C:\Users\svc"
    assert child_env[_OAUTH] == "the-oauth-material"


@pytest.mark.parametrize(
    "var",
    [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
    ],
)
def test_toctou_reappearing_credential_raises_ambiguous(monkeypatch: pytest.MonkeyPatch, var: str):
    """[Unit] auth: an outranking var injected after construction fails the spawn re-check.

    Scenario: subscription settings are constructed cleanly, then *var* is set in
    the environment (late injection) before the child env is built at spawn time.

    Boundaries: exercises the spawn-time TOCTOU re-check in ``_build_child_env``
    (threat model Finding 1, CWE-367); no subprocess is spawned.

    On failure, first check: ``ClaudeCodeUnavailableError`` with
    ``reason="ambiguous_credential"`` must be raised, and its message must contain
    no credential value.
    """
    settings = ClaudeCodeSettings(auth_mode="subscription")
    proc = ClaudeCodeProcess(settings, "task")
    monkeypatch.setenv(var, "late-injected-material-value")

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        proc._build_child_env(resolve_credential(settings))

    assert excinfo.value.reason == "ambiguous_credential"
    assert "late-injected-material-value" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# argv wiring - --bare only reaches argv in api_key mode
# ---------------------------------------------------------------------------


class _FakeStdin:
    """Fake stdin writer recording bytes and close."""

    def __init__(self):
        """Initialise an empty buffer and closed flag."""
        self.data = b""
        self.closed = False

    def write(self, chunk: bytes):
        """Record *chunk*."""
        self.data += chunk

    async def drain(self):
        """No-op drain."""

    def close(self):
        """Mark stdin closed."""
        self.closed = True


class _FakeReader:
    """Fake stream reader that yields immediate EOF."""

    async def readline(self) -> bytes:
        """Return EOF immediately."""
        return b""


class _FakeSpawnProcess:
    """Fake ``asyncio.subprocess.Process`` that completes immediately."""

    def __init__(self):
        """Initialise fake pipes and a clean return code."""
        self.stdin = _FakeStdin()
        self.stdout = _FakeReader()
        self.stderr = _FakeReader()
        self.returncode: Optional[int] = None

    def terminate(self):
        """Reap the fake process on terminate."""
        self.returncode = 0

    def kill(self):
        """Reap the fake process on kill."""
        self.returncode = -9

    async def wait(self) -> int:
        """Return a clean exit code."""
        self.returncode = 0
        return 0


def _patch_spawn(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Monkeypatch ``asyncio.create_subprocess_exec`` and record each call's kwargs.

    :param monkeypatch: the pytest monkeypatch fixture.
    :return: a list of ``{"args", "kwargs"}`` records, one per spawn.
    """
    calls: list[dict] = []

    async def _spawn(*args: object, **kwargs: object) -> _FakeSpawnProcess:
        """Record the spawn arguments and return a fake process."""
        calls.append({"args": args, "kwargs": kwargs})
        return _FakeSpawnProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return calls


async def test_spawn_passes_filtered_env_in_subscription(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: the subscription spawn passes an explicit filtered env=.

    Scenario: a subscription ``ClaudeCodeProcess`` is entered with platform vars
    present; the spawn is faked and its kwargs read.

    Boundaries: exercises the ``__aenter__`` wiring of ``_build_child_env`` into
    ``create_subprocess_exec``; no real binary is spawned.

    On failure, first check: the recorded ``env=`` kwarg must be a dict that omits
    every outranking credential while retaining ``PATH``.
    """
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    settings = ClaudeCodeSettings(auth_mode="subscription")
    calls = _patch_spawn(monkeypatch)

    async with ClaudeCodeProcess(settings, "task"):
        pass

    env = calls[0]["kwargs"]["env"]
    assert isinstance(env, dict)
    for var in _OUTRANKING:
        assert var not in env
    assert env["PATH"] == "/usr/bin:/bin"


async def test_spawn_inherits_env_in_auto(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: the auto-mode spawn passes env=None (inherit, unchanged).

    Scenario: an ``auto`` ``ClaudeCodeProcess`` is entered and the spawn faked.

    Boundaries: exercises the ``__aenter__`` env wiring for the no-op mode.

    On failure, first check: the recorded ``env=`` kwarg must be ``None`` so the
    child inherits ``os.environ`` exactly as Task 03.0 shipped it.
    """
    settings = ClaudeCodeSettings(auth_mode="auto")
    calls = _patch_spawn(monkeypatch)

    async with ClaudeCodeProcess(settings, "task"):
        pass

    assert calls[0]["kwargs"]["env"] is None


async def test_api_key_bare_reaches_argv_subscription_never(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: --bare reaches argv only in api_key mode, never in subscription.

    Scenario: the spawn argv is captured for api_key+bare and for subscription.

    Boundaries: exercises the argv assembly (``build_argv`` + ``extra_argv``) via
    the faked spawn.

    On failure, first check: ``--bare`` must be present in the api_key+bare argv and
    absent from the subscription argv (C7, defence in depth).
    """
    api_settings = ClaudeCodeSettings(auth_mode="api_key", bare=True)
    calls = _patch_spawn(monkeypatch)
    async with ClaudeCodeProcess(api_settings, "task"):
        pass
    api_argv = list(calls[0]["args"])
    assert "--bare" in api_argv

    sub_settings = ClaudeCodeSettings(auth_mode="subscription")
    calls2 = _patch_spawn(monkeypatch)
    async with ClaudeCodeProcess(sub_settings, "task"):
        pass
    sub_argv = list(calls2[0]["args"])
    assert "--bare" not in sub_argv


def test_build_argv_never_emits_bare():
    """[Unit] auth: build_argv itself is structurally incapable of emitting --bare.

    Scenario: ``build_argv`` is called for subscription and api_key+bare settings.

    Boundaries: exercises the builder in isolation (the credential resolver owns
    ``--bare``, not the builder).

    On failure, first check: no ``build_argv`` output may contain ``--bare`` -
    credential flags are appended by ``ClaudeCodeProcess`` from ``extra_argv``.
    """
    assert "--bare" not in build_argv(ClaudeCodeSettings(auth_mode="subscription"))
    assert "--bare" not in build_argv(ClaudeCodeSettings(auth_mode="api_key", bare=True))


# ---------------------------------------------------------------------------
# Subtask 03 - startup auth-probe
# ---------------------------------------------------------------------------


class _FakeProbeProcess:
    """Async-context fake standing in for ``ClaudeCodeProcess`` on the probe path."""

    def __init__(self, *, spawn_error: Optional[BaseException] = None, exit_code: int = 0):
        """Configure the exit code and an optional spawn-time error.

        :param spawn_error: an exception to raise from ``__aenter__``, or ``None``.
        :param exit_code: the exit code returned by ``wait_exit``.
        """
        self._spawn_error = spawn_error
        self._exit_code = exit_code

    async def __aenter__(self) -> _FakeProbeProcess:
        """Enter the fake context, raising the configured spawn error if any."""
        if self._spawn_error is not None:
            raise self._spawn_error
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object):
        """Record context exit; never suppress an in-flight exception."""

    def stdout_lines(self) -> object:
        """Return a stdout sentinel (``parse_stream`` is patched)."""
        return object()

    async def wait_exit(self) -> int:
        """Return the configured exit code."""
        return self._exit_code


def _clean_stream() -> ClaudeCodeStreamResult:
    """Build a usable, non-error stream result with real usage.

    :return: a clean :class:`ClaudeCodeStreamResult`.
    """
    return ClaudeCodeStreamResult(
        content="ok",
        usage=ClaudeCodeUsage(input_tokens=1, output_tokens=1),
        is_error=False,
    )


def _failed_stream() -> ClaudeCodeStreamResult:
    """Build a stream result with no usable ``result`` message.

    :return: a :class:`ClaudeCodeStreamResult` signalling an unusable session.
    """
    return ClaudeCodeStreamResult(content="", usage=None, is_error=False)


def _patch_probe_process(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stream: ClaudeCodeStreamResult,
    exit_code: int = 0,
    spawn_error: Optional[BaseException] = None,
):
    """Patch ``ClaudeCodeProcess`` and ``parse_stream`` on the probe path.

    :param monkeypatch: the pytest monkeypatch fixture.
    :param stream: the stream result ``parse_stream`` returns.
    :param exit_code: the exit code the fake process reports.
    :param spawn_error: an exception the fake process raises on entry, or ``None``.
    """

    def _factory(settings: object, task: str, *, credential: object = None) -> _FakeProbeProcess:
        """Return the configured fake probe process (accepts the threaded credential)."""
        return _FakeProbeProcess(spawn_error=spawn_error, exit_code=exit_code)

    async def _parse(stdout: object) -> ClaudeCodeStreamResult:
        """Return the scripted stream result."""
        return stream

    monkeypatch.setattr(tool_mod, "ClaudeCodeProcess", _factory)
    monkeypatch.setattr(tool_mod, "parse_stream", _parse)


def _make_probe_tool(**settings_kwargs: object) -> tuple[ClaudeCodeTool, MagicMock]:
    """Build a probe tool over real settings and a recording bus.

    :param settings_kwargs: keyword arguments forwarded to ``ClaudeCodeSettings``.
    :return: the tool and the recording event-bus mock.
    """
    settings = ClaudeCodeSettings(**settings_kwargs)
    bus = MagicMock(spec=EventBus)
    tool = ClaudeCodeTool(settings, bus, CallBudget(max_tokens=1_000_000))
    return tool, bus


def _auth_events(bus: MagicMock) -> list[ClaudeCodeAuthFailed]:
    """Return the ``ClaudeCodeAuthFailed`` events published on *bus*.

    :param bus: the recording event-bus mock.
    :return: the matching published events.
    """
    return [c.args[0] for c in bus.publish.call_args_list if isinstance(c.args[0], ClaudeCodeAuthFailed)]


@pytest.mark.parametrize("mode", ["auto", "api_key", "subscription"])
async def test_probe_success_returns_none(monkeypatch: pytest.MonkeyPatch, mode: str):
    """[Unit] auth: a usable credential makes probe_auth return None in every mode.

    Scenario: the probe spawns, gets a clean exit and a usage-bearing result, in
    each of ``auto`` / ``api_key`` / ``subscription``.

    Boundaries: ``ClaudeCodeProcess`` / ``parse_stream`` are faked; no real spawn.

    On failure, first check: ``probe_auth`` must return ``None`` and emit **no**
    ``ClaudeCodeAuthFailed`` event when the credential is usable.
    """
    if mode == "subscription":
        monkeypatch.setenv(_OAUTH, "usable-material")
    tool, bus = _make_probe_tool(auth_mode=mode)
    _patch_probe_process(monkeypatch, stream=_clean_stream(), exit_code=0)

    assert await tool.probe_auth() is None
    assert _auth_events(bus) == []


async def test_probe_no_stored_login(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: subscription with no token and no session -> no_stored_login.

    Scenario: subscription mode, ``CLAUDE_CODE_OAUTH_TOKEN`` unset, the probe exits
    non-zero with no usable result (a stored login absent/expired).

    Boundaries: ``ClaudeCodeProcess`` / ``parse_stream`` faked.

    On failure, first check: ``ClaudeCodeUnavailableError(reason="no_stored_login")``
    must be raised and exactly one matching ``ClaudeCodeAuthFailed`` emitted.
    """
    tool, bus = _make_probe_tool(auth_mode="subscription")
    _patch_probe_process(monkeypatch, stream=_failed_stream(), exit_code=1)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()

    assert excinfo.value.reason == "no_stored_login"
    events = _auth_events(bus)
    assert len(events) == 1
    assert events[0].reason == "no_stored_login"
    assert events[0].auth_mode == "subscription"


async def test_probe_token_rejected(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a rejected OAuth token maps to token_rejected.

    Scenario: subscription mode with ``CLAUDE_CODE_OAUTH_TOKEN`` set, the probe
    exits non-zero with no usable result (the token was rejected).

    Boundaries: ``ClaudeCodeProcess`` / ``parse_stream`` faked.

    On failure, first check: ``ClaudeCodeUnavailableError(reason="token_rejected")``
    must be raised - the failure derives from the resolved credential state, not
    from stderr.
    """
    monkeypatch.setenv(_OAUTH, "rejected-material")
    tool, bus = _make_probe_tool(auth_mode="subscription")
    _patch_probe_process(monkeypatch, stream=_failed_stream(), exit_code=1)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()

    assert excinfo.value.reason == "token_rejected"
    assert _auth_events(bus)[0].reason == "token_rejected"


async def test_probe_result_error_maps_to_failure(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a clean exit but an is_error result is still an auth failure.

    Scenario: subscription+token, the probe exits 0 but the ``result`` message has
    ``is_error`` set.

    Boundaries: ``ClaudeCodeProcess`` / ``parse_stream`` faked.

    On failure, first check: ``ClaudeCodeUnavailableError`` must be raised
    (``token_rejected``) - a usage-bearing but error result is not a usable session.
    """
    monkeypatch.setenv(_OAUTH, "some-material")
    tool, _ = _make_probe_tool(auth_mode="subscription")
    error_stream = ClaudeCodeStreamResult(
        content="",
        usage=ClaudeCodeUsage(input_tokens=1, output_tokens=1),
        is_error=True,
    )
    _patch_probe_process(monkeypatch, stream=error_stream, exit_code=0)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()
    assert excinfo.value.reason == "token_rejected"


async def test_probe_ambiguous_credential_from_spawn(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a spawn-time ambiguous-credential error surfaces as auth_failed.

    Scenario: the faked spawn raises
    ``ClaudeCodeUnavailableError(reason="ambiguous_credential")`` (the TOCTOU
    re-check firing inside the process).

    Boundaries: ``ClaudeCodeProcess`` faked to raise on entry.

    On failure, first check: the probe must re-raise with
    ``reason="ambiguous_credential"`` and emit a matching ``ClaudeCodeAuthFailed``.
    """
    tool, bus = _make_probe_tool(auth_mode="subscription")
    spawn_error = ClaudeCodeUnavailableError("ambiguous", binary="claude", reason="ambiguous_credential")
    _patch_probe_process(monkeypatch, stream=_clean_stream(), spawn_error=spawn_error)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()

    assert excinfo.value.reason == "ambiguous_credential"
    assert _auth_events(bus)[0].reason == "ambiguous_credential"


async def test_probe_spawn_failed_propagates_without_auth_event(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a missing-binary spawn_failed is not treated as an auth failure.

    Scenario: the faked spawn raises
    ``ClaudeCodeUnavailableError(reason="spawn_failed")`` (the ``claude`` binary is
    missing).

    Boundaries: ``ClaudeCodeProcess`` faked to raise on entry.

    On failure, first check: the error must propagate unchanged and **no**
    ``ClaudeCodeAuthFailed`` event may be emitted - it is a capability, not auth,
    failure.
    """
    tool, bus = _make_probe_tool(auth_mode="subscription")
    spawn_error = ClaudeCodeUnavailableError("missing", binary="claude", reason="spawn_failed")
    _patch_probe_process(monkeypatch, stream=_clean_stream(), spawn_error=spawn_error)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()

    assert excinfo.value.reason == "spawn_failed"
    assert _auth_events(bus) == []


async def test_probe_timeout_is_conservative(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a stalled probe uses its own short timeout and a conservative label.

    Scenario: ``_probe_once`` hangs; the probe's independent short timeout fires.

    Boundaries: ``_probe_once`` replaced with a sleeper; the probe timeout is
    shortened via monkeypatch.

    On failure, first check: ``ClaudeCodeUnavailableError`` must be raised (not hang)
    with the conservative ``no_stored_login`` label and a matching event.
    """
    monkeypatch.setattr(tool_mod, "_PROBE_TIMEOUT_S", 0.01)
    tool, bus = _make_probe_tool(auth_mode="subscription")

    async def _hang(credential: object):
        """Sleep long enough to trip the short probe timeout (accepts the credential)."""
        await asyncio.sleep(1.0)

    monkeypatch.setattr(tool, "_probe_once", _hang)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()

    assert excinfo.value.reason == "no_stored_login"
    assert _auth_events(bus)[0].reason == "no_stored_login"


async def test_probe_timeout_with_forwarded_token_is_token_rejected(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a stalled probe under a forwarded token labels token_rejected (FIX 8).

    Scenario: subscription mode with ``CLAUDE_CODE_OAUTH_TOKEN`` set (so the run does
    NOT rely on a stored login); ``_probe_once`` hangs and the short probe timeout
    fires.

    Boundaries: ``_probe_once`` replaced with a sleeper; the probe timeout is
    shortened via monkeypatch. Proves the timeout arm branches on the single
    resolved-credential state rather than hard-coding ``no_stored_login``.

    On failure, first check: the timeout label must be ``token_rejected`` (a stored
    login is not what timed out) - ``no_stored_login`` would be wrong here and in
    ``api_key`` mode, the bug FIX 8 corrects.
    """
    monkeypatch.setattr(tool_mod, "_PROBE_TIMEOUT_S", 0.01)
    monkeypatch.setenv(_OAUTH, "forwarded-oauth-token")
    tool, bus = _make_probe_tool(auth_mode="subscription")

    async def _hang(credential: object):
        """Sleep long enough to trip the short probe timeout (accepts the credential)."""
        await asyncio.sleep(1.0)

    monkeypatch.setattr(tool, "_probe_once", _hang)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        await tool.probe_auth()

    assert excinfo.value.reason == "token_rejected"
    assert _auth_events(bus)[0].reason == "token_rejected"


async def test_probe_dry_run_is_a_no_op(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a dry-run probe returns success without spawning.

    Scenario: ``probe_auth(dry_run=True)`` with the process factory booby-trapped to
    fail if instantiated.

    Boundaries: ``ClaudeCodeProcess`` replaced with a raising factory.

    On failure, first check: ``probe_auth`` must return ``None`` without spawning
    and emit no event - a dry-run must never require a live credential (C13).
    """
    tool, bus = _make_probe_tool(auth_mode="subscription")

    def _boom(settings: object, task: str) -> object:
        """Fail if the probe attempts to spawn under dry-run."""
        raise AssertionError("dry-run probe must not spawn a process")

    monkeypatch.setattr(tool_mod, "ClaudeCodeProcess", _boom)

    assert await tool.probe_auth(dry_run=True) is None
    assert _auth_events(bus) == []


async def test_probe_uses_supplied_run_id(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a supplied run_id is stamped onto the emitted auth_failed event.

    Scenario: a failing subscription probe is called with an explicit ``run_id``.

    Boundaries: ``ClaudeCodeProcess`` / ``parse_stream`` faked.

    On failure, first check: the emitted ``ClaudeCodeAuthFailed.run_id`` must equal
    the supplied id (correlation is preserved).
    """
    rid = str(uuid4())
    tool, bus = _make_probe_tool(auth_mode="subscription")
    _patch_probe_process(monkeypatch, stream=_failed_stream(), exit_code=1)

    with pytest.raises(ClaudeCodeUnavailableError):
        await tool.probe_auth(run_id=rid)

    assert _auth_events(bus)[0].run_id == rid


# ---------------------------------------------------------------------------
# Secrecy - no credential, path, or stderr on any surface (C13)
# ---------------------------------------------------------------------------


async def test_probe_failure_leaks_no_secret_to_logs_error_or_event(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: a probe failure leaks no credential to logs, exception, or event.

    Scenario: subscription mode with a distinctive ``CLAUDE_CODE_OAUTH_TOKEN``
    value; the probe fails and every surface is captured.

    Boundaries: ``ClaudeCodeProcess`` / ``parse_stream`` faked; a TRACE loguru sink
    captures records.

    On failure, first check: the credential value, a ``~/.claude`` credential-file
    path, and any raw stderr must appear in **none** of the captured logs, the
    exception message, or the ``ClaudeCodeAuthFailed`` payload - only a closed-set
    label.
    """
    cred_value = "TOP-CRED-OAUTH-VALUE-DEADBEEF"
    monkeypatch.setenv(_OAUTH, cred_value)
    tool, bus = _make_probe_tool(auth_mode="subscription")
    _patch_probe_process(monkeypatch, stream=_failed_stream(), exit_code=1)

    records, sink_id = _capture_logs()
    try:
        with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
            await tool.probe_auth()
    finally:
        logger.remove(sink_id)

    event = _auth_events(bus)[0]
    joined_logs = "\n".join(records)
    assert cred_value not in str(excinfo.value)
    assert cred_value not in joined_logs
    assert cred_value not in str(event)
    assert cred_value not in repr(event)
    assert ".credentials.json" not in str(excinfo.value)
    assert ".credentials.json" not in joined_logs
    # Only the closed-set label is operator-facing.
    assert event.reason in {"ambiguous_credential", "no_stored_login", "token_rejected"}


def test_config_rejection_names_variable_not_value(monkeypatch: pytest.MonkeyPatch):
    """[Unit] auth: the construction rejection names the var but never its value.

    Scenario: subscription mode with a distinctive ``ANTHROPIC_API_KEY`` value; the
    validator rejects construction and a TRACE sink captures any log output.

    Boundaries: exercises the subscription validator's error surface (C13).

    On failure, first check: ``ANTHROPIC_API_KEY`` must be named while the credential
    value appears in neither the exception message nor any captured log record.
    """
    cred_value = "ANTHROPIC-CRED-VALUE-XYZ-999"
    monkeypatch.setenv("ANTHROPIC_API_KEY", cred_value)

    records, sink_id = _capture_logs()
    try:
        with pytest.raises(ClaudeCodeConfigError) as excinfo:
            ClaudeCodeSettings(auth_mode="subscription")
    finally:
        logger.remove(sink_id)

    assert "ANTHROPIC_API_KEY" in str(excinfo.value)
    assert cred_value not in str(excinfo.value)
    assert cred_value not in "\n".join(records)
