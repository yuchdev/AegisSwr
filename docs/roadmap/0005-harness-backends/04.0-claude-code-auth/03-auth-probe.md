# 03 - Startup auth-probe + `ClaudeCodeUnavailableError` distinction

**Parent task:** 04.0 Claude Code Subscription/Login Authentication
**State:** ⬜ Not started
**Depends on:** 01 (`auth_mode` field + config-error surface), 02 (the resolved
credential the probe verifies), Task 03.0 (the spawn primitive the probe reuses)
**Blocks:** Task 05.0 (canonical `exceptions.py`), Task 10.0 (`aegis code-intel
check` surfaces the probe)

## Objective

Add a **startup auth-probe** to `ClaudeCodeTool` (delegating the actual spawn to
`ClaudeCodeProcess`) that verifies the credential resolved by subtask 02 is
actually usable **before the first `delegate()` call**, rather than discovering
an auth failure mid-investigation. The probe:

- runs a lightweight, side-effect-minimal `claude` invocation (no real
  investigation task) that exercises credential resolution only;
- raises `ClaudeCodeUnavailableError` (a **runtime capability failure**) when
  the credential does not resolve to a working session — kept **strictly
  distinct** from `ClaudeCodeConfigError` (the **settings-shape / ambiguity
  failure** subtask 01 raises at construction);
- emits the `claude_code.auth_failed` event (taxonomy defined in Task 05.0,
  C10) carrying only a coarse failure-reason label, never a credential;
- is the method [Task 10.0](/docs/roadmap/0005-harness-backends/plan.md)'s
  backend-agnostic `aegis code-intel check` will call. **This task defines the
  probe method only** — wiring it into the CLI is Task 10.0's job.

The probe matters most for `subscription` mode with a stored `claude login`
session and no `CLAUDE_CODE_OAUTH_TOKEN` (subtask 02's
`relies_on_stored_login=True` case): that session can be absent or expired, and
C7 requires the failure surface **before** the first `delegate()`.

## File: `claude_code/tool.py`

```python
from __future__ import annotations

from typing import Optional

from aegis_swr.claude_code.exceptions import ClaudeCodeUnavailableError
from aegis_swr.claude_code.process import ResolvedCredential, resolve_credential


class ClaudeCodeTool:
    """The Claude Code ``CodeIntelBackend`` (Task 03.0), extended with C7 auth.

    This subtask adds only :meth:`probe_auth`; the ``delegate`` implementation,
    the one-shot spawn, NDJSON parsing, and real token accounting are Task
    03.0's and are unchanged here.
    """

    async def probe_auth(self) -> None:
        """Verify the resolved credential is usable before the first delegate().

        Resolves the credential (subtask 02), then runs a minimal ``claude``
        invocation via :class:`ClaudeCodeProcess` that forces credential
        resolution without executing an investigation task. On success returns
        ``None``. On any auth-related failure it emits ``claude_code.auth_failed``
        (C10) with a coarse reason label and raises
        :class:`ClaudeCodeUnavailableError`.

        In ``auth_mode="auto"`` the probe still runs but adds no auth-specific
        interpretation - it reports only whether the binary produced a usable
        session, preserving the Task 03.0 default behaviour.

        :raises ClaudeCodeUnavailableError: when the resolved credential does
            not yield a working session (no stored login, expired/rejected
            token, or an ambiguous-credential resolution the binary reports).
            The exception message and the emitted event carry **no** credential
            value (C7, C13).
        """
        ...
```

## File: `claude_code/exceptions.py`

```python
from __future__ import annotations

from typing import Optional


class ClaudeCodeUnavailableError(RuntimeError):
    """Raised when Claude Code is configured correctly but not usable at runtime.

    A **capability** failure, distinct from :class:`ClaudeCodeConfigError` (a
    settings-shape / ambiguity failure raised at construction, subtask 01).
    Neither subclasses the other. Forward-declared here and made canonical in
    Task 05.0's ``exceptions.py`` (same module, import-compatible - downstream
    imports never change when 05.0 lands).

    :param reason: A coarse, non-secret failure label - one of
        ``"ambiguous_credential"``, ``"no_stored_login"``, ``"token_rejected"``
        (the same closed set the ``claude_code.auth_failed`` event uses, C10).
    :ivar reason: The stored failure label; safe to log and to place in the
        event payload because it is drawn from a fixed vocabulary and contains
        no credential material.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Claude Code credential unavailable: {reason}")
```

## The two-error distinction (C7)

| Failure                  | Error type                   | Raised at                                                    | Example                                                                                        |
|--------------------------|------------------------------|--------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| Config-shape / ambiguity | `ClaudeCodeConfigError`      | settings **construction** (subtask 01)                       | `auth_mode="subscription"` while `ANTHROPIC_API_KEY` is set; `subscription` + `--bare`         |
| Runtime capability       | `ClaudeCodeUnavailableError` | **health-check / composition** (this subtask's `probe_auth`) | stored `claude login` session absent or expired; `CLAUDE_CODE_OAUTH_TOKEN` rejected by the API |

Keeping these separate lets `aegis code-intel check` (Task 10.0) tell an
operator whether to **fix their configuration** (config error, deterministic,
found before any process spawns) or **re-authenticate** (unavailable error,
discovered by actually exercising the credential). Neither error type
subclasses the other, mirroring the harness's own `HarnessConfigError` vs
`HarnessUnavailableError` split (C2).

## Failure-reason vocabulary

`probe_auth` maps outcomes onto the closed set the `claude_code.auth_failed`
event carries (C10) — never free-form text derived from `claude`'s stderr,
which could echo a credential:

- `"no_stored_login"` — `subscription` mode, `relies_on_stored_login=True`, and
  no working session in the credential store.
- `"token_rejected"` — a `CLAUDE_CODE_OAUTH_TOKEN` (or, in `api_key` mode, an
  API key) that the binary reports as invalid/expired.
- `"ambiguous_credential"` — the probe observes a credential resolution that
  contradicts the operator's `auth_mode` intent in a way subtask 01 could not
  catch at construction (defensive; the common ambiguity is already rejected
  earlier).

## Implementation notes

- **Reuse Task 03.0's spawn, do not fork it.** The probe issues a minimal
  invocation through the existing `ClaudeCodeProcess` one-shot path with the
  credential env/argv from `resolve_credential` (subtask 02), so argv-safety
  (C6) and the timeout/failure-path discipline (C13) are inherited, not
  re-implemented. Keep the probe's own timeout short and independent of
  `request_timeout_s` (a probe should fail fast).
- **Classify from exit status and structured stream, never from raw stderr
  text.** Map the process outcome onto the closed reason vocabulary above.
  Never place `claude`'s raw stderr/stdout into the exception, the log, or the
  event — it may contain credential fragments (C13). If a specific reason
  cannot be determined, use the most conservative applicable label and log at
  `warning` with the label only.
- **Idempotent, run-once semantics.** The probe is intended to run at
  health-check time (before the first `delegate()`); it must be safe to call
  more than once (e.g. once by `aegis code-intel check`, once at composition).
  It holds no persistent connection (there is no sidecar — C6).
- **Dry-run.** Consistent with the per-backend dry-run rule (C13), a probe
  invoked under `--dry-run` short-circuits to success without spawning any
  process — dry-run must never require a live credential.
- **Event emission.** On failure emit exactly one `claude_code.auth_failed`
  (Task 05.0's `DomainEvent` subclass) with `reason` set to the closed-set
  label and the standard `run_id` / UTC `timestamp`; emit nothing carrying a
  credential (C10, C13).
- **`ClaudeCodeUnavailableError` forward-declaration discipline.** Define it in
  `claude_code/exceptions.py` now, import-compatible with Task 05.0's canonical
  taxonomy so no downstream import path changes when 05.0 lands (the same
  discipline OpenClaude used for `OpenClaudeConfigError` in Milestone 0004).

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `ClaudeCodeUnavailableError` and `ClaudeCodeConfigError` are **distinct** and neither subclasses the other (C7).
- No credential value (OAuth token, `CLAUDE_CODE_OAUTH_TOKEN`, API key, credential-file contents) or raw `claude` stderr ever reaches the exception message, a log sink, or the `claude_code.auth_failed` payload (C7, C13); `SensitiveFilter` covers `tool.py`'s and `exceptions.py`'s loggers.
- The probe has its own short timeout and a defined failure path; no bare `except:`; RAII via context managers for the subprocess (inherited from Task 03.0's `ClaudeCodeProcess`) (C13).
- `asyncio.sleep` for any backoff, never `time.sleep` (C13).
- This subtask does **not** wire the probe into the CLI — that is Task 10.0's `aegis code-intel check` work; it only defines and exports the method.

## Success criteria

- [ ] `probe_auth()` returns `None` (no raise) when the resolved credential is usable, in every one of `auto` / `api_key` / `subscription`.
- [ ] `probe_auth()` in `subscription` mode with no `CLAUDE_CODE_OAUTH_TOKEN` and no valid stored `claude login` session raises `ClaudeCodeUnavailableError(reason="no_stored_login")`.
- [ ] `probe_auth()` with a rejected/expired `CLAUDE_CODE_OAUTH_TOKEN` raises `ClaudeCodeUnavailableError(reason="token_rejected")`.
- [ ] `ClaudeCodeUnavailableError` is not a subclass of `ClaudeCodeConfigError` and vice versa; both importable from `claude_code/exceptions.py`.
- [ ] The exception message, every captured `SensitiveFilter` log line, and the `claude_code.auth_failed` event payload contain **no** credential value and **no** raw `claude` stderr — only a closed-set `reason` label.
- [ ] `probe_auth()` under `--dry-run` returns success without spawning a process.
- [ ] The probe reuses `ClaudeCodeProcess`'s spawn path (argv-safety, timeout, RAII) rather than constructing a bare subprocess of its own.
- [ ] `replace_optional.py --check` clean; `ruff` clean; RST docstrings on the new method and exception class.
