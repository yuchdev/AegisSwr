# 01 - `auth_mode` field + subscription-mode rejection validator

**Parent task:** 04.0 Claude Code Subscription/Login Authentication
**State:** ⬜ Not started
**Depends on:** Task 02.0 (`ClaudeCodeSettings` exists), Task 03.0 (the
subprocess invocation path this mode governs)
**Blocks:** 02 (credential-resolution helper reads `auth_mode`), 03 (auth-probe
distinguishes its runtime error from this subtask's config error)

## Objective

Extend the existing `ClaudeCodeSettings` class (Task 02.0,
`claude_code/config.py`) **additively** with a single new field, `auth_mode`,
and the two construction-time invariants C7 mandates for it:

1. a **subscription-mode rejection validator** that raises
   `ClaudeCodeConfigError` when `auth_mode="subscription"` and an
   `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is present in the environment, 
   the subprocess will inherit; and
2. the **`--bare` exclusion rule** — subscription mode may never produce a
   `--bare` invocation, so a `bare`-mode request combined with
   `auth_mode="subscription"` is rejected at construction.

No existing field, default, or validator of `ClaudeCodeSettings` changes. When
`auth_mode` is left at its `auto` default the class behaves exactly as Task 02.0
shipped it — this is the behavioral-freeze guarantee for the default path.

## File: `claude_code/config.py`

**New field** (env var → field name → type → default):

| Env var                 | Field       | Type                                       | Default  |
|-------------------------|-------------|--------------------------------------------|----------|
| `CLAUDE_CODE_AUTH_MODE` | `auth_mode` | `Literal["auto","api_key","subscription"]` | `"auto"` |

```python
from __future__ import annotations

import os
from typing import Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings

# ClaudeCodeConfigError is forward-declared in Task 02.0's config.py and made
# canonical in Task 05.0's exceptions.py (same forward-declaration discipline
# as OpenClaude). This subtask raises it; it does not redefine it.
from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError

# Env vars that outrank a subscription credential per the C7 precedence chain
# (ranks 2-3). Their mere presence defeats an explicit subscription choice.
_OUTRANKING_ENV_VARS: tuple[str, ...] = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


class ClaudeCodeSettings(BaseSettings):
    """Environment-sourced configuration for the Claude Code backend.

    Task 02.0 defines the full field set (binary path, allowlist, permission
    mode, ``max_turns``, timeouts, mandatory disposable ``scratch_cwd``, the
    ``CLAUDE_CODE_ENABLED`` presence signal). This subtask adds only
    ``auth_mode`` and its cross-cutting validators (C7).

    :ivar auth_mode: Which credential surface the one-shot ``claude`` subprocess
        must use. ``"auto"`` (default) defers entirely to the ``claude``
        binary's own precedence chain and adds no Aegis-side validation.
        ``"api_key"`` uses the host ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN``
        exactly as Task 03.0 built it (``--bare`` eligible). ``"subscription"``
        uses a Claude.ai login (OAuth) and is rejected at construction if an
        API-key credential is present in the inherited environment (it would
        silently outrank the login) or if a ``--bare`` invocation is requested.
    """

    # ... Task 02.0 fields unchanged ...

    auth_mode: Literal["auto", "api_key", "subscription"] = "auto"

    @model_validator(mode="after")
    def _validate_subscription_mode(self) -> "ClaudeCodeSettings":
        """Reject a subscription-mode config that cannot honour the operator's
        explicit choice.

        Only runs meaningfully when ``auth_mode == "subscription"``. Raises
        :class:`ClaudeCodeConfigError` when an outranking API-key credential is
        present in the inherited environment, or when a ``--bare`` invocation is
        requested (bare mode never reads OAuth/login credentials, C7). The
        exception message names **only** the offending env-var/field name -
        never the credential value (C13).

        :return: ``self`` when the configuration is internally consistent.
        :raises ClaudeCodeConfigError: on an ambiguous credential or a
            ``subscription`` + ``--bare`` combination.
        """
        ...
```

## The `--bare` exclusion rule

C7 states bare mode "never reads OAuth/login credentials at all and is
therefore unusable for a login-based deployment," so `--bare` must never be
emitted in subscription mode.

- If Task 03.0 already introduced a bare-mode toggle on `ClaudeCodeSettings`
  (e.g., a `bare: bool` field, `CLAUDE_CODE_BARE`, default `False`, added there
  for the "`--bare` MAY be added for reproducibility" api_key case), this
  subtask **only** adds the cross-field check to `_validate_subscription_mode`:
  `auth_mode="subscription"` with the bare toggle `True` raises
  `ClaudeCodeConfigError(field="auth_mode", reason=...)`.
- If Task 03.0 did **not** add such a toggle (bare is decided purely inside the
  credential-resolution helper), then there is no field to reject at
  construction and this subtask's `--bare` responsibility is discharged
  entirely in subtask 02 (the helper simply never appends `--bare` when
  `auth_mode="subscription"`). Subtask 01 still documents the invariant so the
  rule has a single home.

Settle which of the two applies against Task 03.0's shipped `config.py`; do not
introduce a duplicate bare toggle if one already exists.

## Implementation notes

- **Presence test semantics (C7 / memory: empty-env coercion).** A credential
  counts as "present in the inherited environment" only when it is set **and
  non-empty**. Implement as
  `any(os.environ.get(v) for v in _OUTRANKING_ENV_VARS)` so an unset variable
  and an empty-string variable (`ANTHROPIC_API_KEY=""`, the classic
  unset-CI-secret artifact) are both treated as absent. A stray empty value
  must not trigger a spurious rejection and must not be relied on as a working
  credential either.
- **Why `model_validator(mode="after")` and not `field_validator`.** The rule
  is cross-cutting: it correlates the `auth_mode` field with the ambient
  process environment (and, if present, the bare toggle field). A single
  after-validator keeps all subscription-mode invariants in one place and reads
  `os.environ` exactly once.
- **Reading `os.environ` here is deliberate and bounded.** C1 forbids
  composition/tool code from reading `os.environ`; a settings validator is the
  one place that legitimately inspects the environment, mirroring how every
  Pydantic settings source already does. No other module in this task reads
  these variables.
- **Error unwrapping (C5 convention).** Pydantic wraps a validator's exception
  in a `ValidationError`. Follow the `OpenClaudeSettings` pattern: catch and
  re-raise as the bare typed `ClaudeCodeConfigError` in `__init__` so callers
  always see the backend's own error type, not Pydantic's.
- **No secret in the error.** The rejection message states, e.g.,
  `"auth_mode='subscription' but ANTHROPIC_API_KEY is set in the environment; "
  "it would silently outrank the subscription login (C7 precedence rank 3). "
  "Unset it or use auth_mode='api_key'."` — the **name** of the variable, never
  its value.
- `auth_mode="auto"` and `auth_mode="api_key"` add **no** environment
  inspection and **no** rejection here — the validator returns `self`
  immediately for those two modes.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- Purely **additive** to `ClaudeCodeSettings`: no Task 02.0 field, default, or validator is altered; existing Task 02.0 / Task 03.0 unit tests stay green.
- `ClaudeCodeConfigError` is imported, not redefined; the import path is stable across Task 05.0's canonicalization.
- The rejection message and any log line never contain a credential value (C13); `SensitiveFilter` still covers the config module's logger.
- No `Any` in the field type; `ruff check src/ tests/` - clean.

## Success criteria

- [ ] `ClaudeCodeSettings()` with no `CLAUDE_CODE_AUTH_MODE` set produces `auth_mode == "auto"` and constructs without raising.
- [ ] `ClaudeCodeSettings(auth_mode="subscription")` with neither `ANTHROPIC_API_KEY` nor `ANTHROPIC_AUTH_TOKEN` set constructs without raising.
- [ ] `ClaudeCodeSettings(auth_mode="subscription")` with `ANTHROPIC_API_KEY` set (non-empty) raises `ClaudeCodeConfigError`; the exception message names `ANTHROPIC_API_KEY` but contains **no** part of its value.
- [ ] `ClaudeCodeSettings(auth_mode="subscription")` with `ANTHROPIC_AUTH_TOKEN` set (non-empty) raises `ClaudeCodeConfigError`.
- [ ] `ClaudeCodeSettings(auth_mode="subscription")` with `ANTHROPIC_API_KEY=""` (empty) constructs without raising (empty == absent).
- [ ] `ClaudeCodeSettings(auth_mode="subscription")` combined with a `--bare` request raises `ClaudeCodeConfigError` (whether via a bare toggle field or documented as delegated to subtask 02, per the exclusion-rule note).
- [ ] `ClaudeCodeSettings(auth_mode="api_key")` with `ANTHROPIC_API_KEY` set constructs without raising — the presence check applies only to subscription mode.
- [ ] `ClaudeCodeSettings(auth_mode="bogus")` raises a validation error (`Literal` rejects the value).
- [ ] All Task 02.0 / Task 03.0 config unit tests remain green (additive-only).
- [ ] `ruff check src/ tests/` - clean.
