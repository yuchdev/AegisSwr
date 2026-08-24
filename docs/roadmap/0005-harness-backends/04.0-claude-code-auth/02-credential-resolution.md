# 02 - Credential-resolution helper (`process.py` / `tool.py`)

**Parent task:** 04.0 Claude Code Subscription/Login Authentication
**State:** ⬜ Not started
**Depends on:** 01 (`auth_mode` field + validators), Task 03.0 (the subprocess
env/argv construction this helper feeds)
**Blocks:** 03 (the auth-probe verifies the credential this helper resolves)

## Objective

Add a **credential-resolution helper** to `claude_code/process.py` that maps a
validated `auth_mode` onto the concrete credential surface the one-shot
`claude` subprocess (Task 03.0) will use: which environment it inherits, and
whether `--bare` is appended to the argv. The helper is the single place that
translates the operator's `auth_mode` choice into subprocess behavior, so
Task 03.0's spawn path calls it once and does not itself branch on auth.

The helper covers all four cases C7 defines:

- **`subscription`** — never `--bare`; if `CLAUDE_CODE_OAUTH_TOKEN` is set, that
  is the credential the subprocess uses (the recommended CI-friendly path);
  otherwise the subprocess relies on a pre-existing `claude login` session in
  the local credential store, verified by subtask 03's health check before the
  first `delegate()`.
- **`api_key`** — behaves exactly as Task 03.0 built it (the host
  `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`); `--bare` **may** be appended
  for reproducibility.
- **`auto`** — no extra logic at all; inherit the ambient environment
  unexamined and let the `claude` binary's own precedence chain resolve the
  credential. Emits no `--bare`.

## File: `claude_code/process.py`

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from aegis_swr.claude_code.config import ClaudeCodeSettings


@dataclass(frozen=True)
class ResolvedCredential:
    """The credential surface derived from a validated ``auth_mode`` (C7).

    Consumed by Task 03.0's subprocess-spawn path to finalise the child
    environment and argv. Carries **no** secret value: ``oauth_token_present``
    is a boolean signal only, never the token itself.

    :ivar mode: The resolving ``auth_mode`` (``"auto"`` / ``"api_key"`` /
        ``"subscription"``), for event/diagnostic labelling.
    :ivar extra_argv: Flags to append to the ``claude`` argv - ``["--bare"]``
        only when bare mode is both requested and eligible, else empty. Never
        contains a credential.
    :ivar env_passthrough: Names of environment variables that must be forwarded
        to the child (e.g. ``CLAUDE_CODE_OAUTH_TOKEN`` in subscription mode).
        The helper forwards **by name**; the value is copied from ``os.environ``
        at spawn time by Task 03.0's env builder and never materialised into a
        log, an event, or this dataclass.
    :ivar relies_on_stored_login: ``True`` in subscription mode when no
        ``CLAUDE_CODE_OAUTH_TOKEN`` is set, so the subprocess depends on a
        stored ``claude login`` session - the case subtask 03's probe must
        verify before the first ``delegate()``.
    """

    mode: str
    extra_argv: tuple[str, ...] = ()
    env_passthrough: tuple[str, ...] = ()
    relies_on_stored_login: bool = False


def resolve_credential(settings: ClaudeCodeSettings) -> ResolvedCredential:
    """Derive the subprocess credential surface from ``settings.auth_mode``.

    Pure and side-effect-free: it reads ``settings`` and probes only for the
    *presence* of ``CLAUDE_CODE_OAUTH_TOKEN`` (never its value). It performs no
    validation that belongs to subtask 01 (which already rejected an ambiguous
    ``subscription`` config at construction) and no liveness check (subtask
    03's probe owns that).

    :param settings: A fully validated :class:`ClaudeCodeSettings`.
    :return: The :class:`ResolvedCredential` Task 03.0's spawn path consumes.
    """
    ...
```

## Behavior matrix

| `auth_mode`    | `--bare`?                    | Credential the subprocess uses                                                                 | `relies_on_stored_login` |
|----------------|------------------------------|------------------------------------------------------------------------------------------------|--------------------------|
| `auto`         | never (helper adds none)     | whatever the `claude` binary's precedence chain resolves, unexamined                           | `False`                  |
| `api_key`      | eligible (if bare requested) | host `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` (Task 03.0 behaviour, unchanged)             | `False`                  |
| `subscription` | **never** (excluded, C7)     | `CLAUDE_CODE_OAUTH_TOKEN` if set, else a stored `claude login` session in the credential store | `True` iff token unset   |

## Implementation notes

- **The helper forwards credentials by name, never by value.** It returns the
  *names* of env vars to pass through; Task 03.0's env builder copies the values
  from `os.environ` into the child environment at spawn. No credential value is
  ever placed in `ResolvedCredential`, logged, or put in an event — this keeps
  the secret off every Aegis-owned surface (C13).
- **`auto` is a genuine no-op.** In `auto` mode the helper returns
  `ResolvedCredential(mode="auto")` with empty `extra_argv` and empty
  `env_passthrough`: the child simply inherits the parent environment and
  `claude` decides. This is exactly Task 03.0's existing behavior, so the
  Task 03.0 acceptance tests continue to pass with the helper in the path.
- **`subscription` never emits `--bare`** regardless of any bare toggle —
  subtask 01 already rejected the `subscription` + bare combination at
  construction, so by the time the helper runs, the combination is impossible;
  the helper nonetheless unconditionally omits `--bare` in this branch as a
  defense-in-depth invariant (belt and braces on the C7 rule).
- **`CLAUDE_CODE_OAUTH_TOKEN` precedence within subscription mode.** When the
  token is set, forward it (`env_passthrough = ("CLAUDE_CODE_OAUTH_TOKEN",)`)
  and set `relies_on_stored_login=False`; the token is the credential Claude
  Code will use (precedence rank 5, and — because subtask 01 guaranteed ranks
  2-3 are absent — the winning credential). When it is unset,
  `relies_on_stored_login=True` and the child depends on the stored login
  session (rank 7); no env passthrough is needed because the session lives in
  the OS credential store / credentials file, not in an env var.
- **This helper adds no `os.environ` reads to composition/tool logic beyond a
  presence check.** The only environment access is
  `bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))` for the presence signal,
  treated with the same empty==absent semantics as subtask 01. Everything else
  is derived from `settings`.
- **`api_key` bare eligibility** follows whatever Task 03.0 established for its
  bare toggle; the helper only *permits* `--bare` here, it does not force it.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `ResolvedCredential` is `frozen=True` and carries **no** secret field — only names, flags, and the mode label.
- The helper is pure/deterministic given `settings` + the OAuth-token presence bit; it opens no connection and spawns no process (that is Task 03.0's spawn and subtask 03's probe).
- Task text (C6 argv-safety) is out of scope here and unchanged — the helper only touches credential argv flags (`--bare`) and env passthrough, never the task payload, which Task 03.0 continues to pass via the stdin or temp file.
- No credential value in any return field, log line, or exception (C13); `SensitiveFilter` covers `process.py`'s logger.

## Success criteria

- [ ] `resolve_credential(ClaudeCodeSettings(auth_mode="auto"))` returns `extra_argv == ()` and `env_passthrough == ()` — a true no-op preserving Task 03.0 behavior.
- [ ] `resolve_credential(ClaudeCodeSettings(auth_mode="subscription"))` with `CLAUDE_CODE_OAUTH_TOKEN` set returns `env_passthrough == ("CLAUDE_CODE_OAUTH_TOKEN",)`, `relies_on_stored_login is False`, and `--bare` **not** in `extra_argv`.
- [ ] `resolve_credential(ClaudeCodeSettings(auth_mode="subscription"))` with `CLAUDE_CODE_OAUTH_TOKEN` unset returns `relies_on_stored_login is True`, empty `env_passthrough`, and `--bare` **not** in `extra_argv`.
- [ ] `resolve_credential(ClaudeCodeSettings(auth_mode="api_key"))` permits `--bare` in `extra_argv` when a bare invocation is requested, and never forwards `CLAUDE_CODE_OAUTH_TOKEN`.
- [ ] No `ResolvedCredential` instance, log line, or exception emitted by the helper contains any credential value (asserted by inspecting fields and a captured `SensitiveFilter` log).
- [ ] `--bare` is absent from `extra_argv` in **every** `subscription`-mode resolution (C7).
- [ ] `ruff check src/ tests/` - clean; no `Any` in return types.
