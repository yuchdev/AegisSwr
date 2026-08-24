# 02 - `permission_mode` & disposable `scratch_cwd`

**Parent task:** 02.0 Claude Code Settings & Config
**State:** ⬜ Not started
**Depends on:** 01 (`ClaudeCodeSettings` class shape)
**Blocks:** 03.0 (the subprocess tool reads both fields to build the invocation)

## Objective

Add the two security-guard fields to the `ClaudeCodeSettings` class defined in
subtask 01: `permission_mode` and a **mandatory disposable** `scratch_cwd`.
Because Claude Code runs with **host OS permissions and no sandbox**, these two
fields plus subtask 01's read-only `allowed_tools` default are — per **C6 item
3** — the *only* guards standing in for the sandbox that this backend lacks.
This subtask therefore carries the two validators that make the no-sandbox
posture safe at settings-construction time:

1. a `permission_mode` validator that **rejects any bypass-permissions value**
   (anything that would cause the tool to emit `--dangerously-skip-permissions`
   in Task 03.0's argv); and
2. a `scratch_cwd` validator enforcing that, **when the backend is enabled**, a
   scratch working directory is set, is creatable/writable, and is **not** the
   repository root — so an untrusted one-shot `claude` process runs in a
   disposable directory rather than over the live source tree.

Both fields are added onto the *same* `config.py` class from subtask 01; this
document shows only the added members.

## File: `aegis_swr/claude_code/config.py` (additions)

**Fields** (env var → field name → type → default):

| Env var                       | Field             | Type             | Default              |
|-------------------------------|-------------------|------------------|----------------------|
| `CLAUDE_CODE_PERMISSION_MODE` | `permission_mode` | `str`            | `"default"`          |
| `CLAUDE_CODE_SCRATCH_CWD`     | `scratch_cwd`     | `Optional[Path]` | `None`               |

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator

# ClaudeCodeConfigError, ClaudeCodeSettings — defined in subtask 01.

#: Claude Code permission modes accepted by ``--permission-mode``. The bypass
#: mode is intentionally absent from the *allowed* set and named separately so
#: the validator can reject it with a precise reason (C6 item 3).
_ALLOWED_PERMISSION_MODES: frozenset[str] = frozenset({"default", "acceptEdits", "plan"})

#: Values that would cause the tool to skip the permission prompt entirely. Any
#: of these — or the raw ``--dangerously-skip-permissions`` flag string — is
#: rejected at settings-validation time.
_BYPASS_PERMISSION_VALUES: frozenset[str] = frozenset(
    {"bypassPermissions", "bypass", "dangerously-skip-permissions", "--dangerously-skip-permissions"}
)


class ClaudeCodeSettings(BaseSettings):  # ← same class as subtask 01; fields added
    # ... subtask 01 fields (binary_path, enabled, allowed_tools, max_turns,
    #     request_timeout_s) elided ...

    permission_mode: str = "default"
    scratch_cwd: Optional[Path] = None

    @field_validator("permission_mode")
    @classmethod
    def _validate_permission_mode(cls, v: str) -> str:
        """Accept only a non-bypassing mode; reject any bypass-permissions value.

        Rejects ``bypassPermissions`` and anything that would produce
        ``--dangerously-skip-permissions`` in the constructed argv (Task 03.0),
        raising :class:`ClaudeCodeConfigError`. The comparison is
        case-insensitive so ``BYPASSPERMISSIONS`` cannot slip through.
        """
        ...

    @field_validator("scratch_cwd", mode="before")
    @classmethod
    def _coerce_scratch_cwd(cls, v: object) -> object:
        """Treat an empty/whitespace-only env value as unset (``None``)."""
        ...

    @model_validator(mode="after")
    def _validate_scratch_cwd_when_enabled(self) -> "ClaudeCodeSettings":
        """Enforce the mandatory disposable scratch cwd only when enabled.

        When ``enabled`` is ``False`` the object stays constructible with
        ``scratch_cwd=None`` (presence-signal-as-falsy default, C5). When
        ``enabled`` is ``True`` the scratch cwd must be set, must be creatable
        and writable, and must not be the repository root. Raises
        :class:`ClaudeCodeConfigError` otherwise.
        """
        ...
```

## Implementation notes

### `permission_mode`

- Valid non-bypassing modes are `{"default", "acceptEdits", "plan"}`. `"plan"`
  is the most conservative (the agent proposes but never acts) and is a sound
  choice for pure read-only forensics; `"default"` is chosen as the shipped
  default to match Claude Code's own default surface while still requiring a
  permission decision for anything write-capable.
- Reject any value in `_BYPASS_PERMISSION_VALUES`, matched **case-insensitively**
  (normalise with `.strip().lower()` before comparison, but compare the
  bypass-set members likewise). Any unrecognised value that is *not* a known
  non-bypassing mode is also rejected with `ClaudeCodeConfigError(field=
  "permission_mode", reason=...)`, so a typo cannot silently degrade to an
  unguarded invocation.
- The rejection is **unconditional** — it does not depend on `enabled`, so an
  operator cannot stage a bypass value "for later". This is the settings-time
  half of the C6 guarantee that no settings value ever produces
  `--dangerously-skip-permissions`; Task 03.0's argv-construction asserts the
  same invariant on the output side (the flag never appears in argv).
- The reason string names only the offending mode value and the allowed set —
  never any payload or credential text (C13).

### `scratch_cwd`

- `mode="before"` coercion: an unset env var or a whitespace-only expansion
  (`CLAUDE_CODE_SCRATCH_CWD: ${{ secrets.MISSING }}` → `""`) is coerced to
  `None`, consistent with the empty-env/secret handling used across the
  codebase — so an unconfigured backend never crashes construction.
- The mandatory/creatable/writable/not-repo-root checks live in an **`after`
  model validator**, not a field validator, because they are conditional on the
  `enabled` field and Pydantic only guarantees cross-field access after all
  fields are populated. When `enabled is False`, return `self` unchanged
  (scratch cwd irrelevant — backend not registered).
- When `enabled is True`:
  - `scratch_cwd is None` → raise `ClaudeCodeConfigError(field="scratch_cwd",
    reason="a disposable scratch working directory is mandatory when the "
    "Claude Code backend is enabled")`.
  - **Creatable/writable:** resolve the path (`Path.expanduser().resolve()`);
    if it does not exist, verify the nearest existing ancestor is a writable
    directory (so Task 03.0 can `mkdir` it per run); if it exists, verify it is
    a directory and writable. Raise `ClaudeCodeConfigError` naming only the
    resolved path on failure. Do **not** create the directory here — settings
    construction has no side effects; directory creation is Task 03.0's
    per-`delegate()` RAII concern (a fresh disposable dir via a context
    manager). This validator only proves the location is *usable*.
  - **Not the repository root:** reject when the resolved `scratch_cwd` equals
    the repository root or is an ancestor of it. The repo root is located by
    walking upward from `Path.cwd()` for a `.git` marker (falling back to
    `Path.cwd()` when no marker is found, and treating that as the root to
    protect). This prevents a one-shot `claude` process — which has host write
    permission if any write tool is ever enabled — from operating directly over
    the live source tree. Raise `ClaudeCodeConfigError(field="scratch_cwd",
    reason="must not be the repository root or an ancestor of it")`.
- "Disposable" is a **usage** contract fulfilled by Task 03.0 (a fresh
  per-`delegate()` subdirectory, cleaned up via a context manager); this task
  only guarantees the *location* is valid, isolated from the repo, and writable.

## Constraints

- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` (C13). `scratch_cwd` is `Optional[Path]`.
- The mandatory-scratch-cwd check must **not** fire when `enabled is False`, so
  `ClaudeCodeSettings()` with no env stays constructible (C5).
- No settings value may ever produce `--dangerously-skip-permissions`; the
  bypass rejection is unconditional and case-insensitive (C6 item 3).
- Settings construction performs **no filesystem side effects** — it may
  `stat`/probe for writability but must not create, move, or delete anything
  (RAII directory lifecycle belongs to Task 03.0).
- No secret, credential, or incident-payload text in any error/warning; error
  reasons name only field names, the resolved path, and the allowed mode set
  (C13).
- These two validators are **auth-mode-agnostic** — they must not reference a
  not-yet-existing `auth_mode` field, preserving Task 04.0's additive extension.

## Success criteria

- [ ] `ClaudeCodeSettings()` (no env, `enabled=False`) constructs with
      `permission_mode="default"` and `scratch_cwd=None`, without raising.
- [ ] `ClaudeCodeSettings(permission_mode="bypassPermissions")` raises
      `ClaudeCodeConfigError`.
- [ ] `ClaudeCodeSettings(permission_mode="--dangerously-skip-permissions")`
      raises `ClaudeCodeConfigError`.
- [ ] `ClaudeCodeSettings(permission_mode="BYPASSPERMISSIONS")` raises
      `ClaudeCodeConfigError` (case-insensitive).
- [ ] `ClaudeCodeSettings(permission_mode="plan")` does not raise.
- [ ] `ClaudeCodeSettings(permission_mode="nonsense")` raises
      `ClaudeCodeConfigError` (unknown, non-bypassing values also rejected).
- [ ] `ClaudeCodeSettings(enabled=True)` with `scratch_cwd` unset raises
      `ClaudeCodeConfigError` (mandatory when enabled).
- [ ] `ClaudeCodeSettings(enabled=True, scratch_cwd=<writable temp dir>)` does
      not raise and does **not** create the directory as a side effect.
- [ ] `ClaudeCodeSettings(enabled=True, scratch_cwd=<repository root>)` raises
      `ClaudeCodeConfigError`.
- [ ] `CLAUDE_CODE_SCRATCH_CWD=""` (empty CI-secret expansion) coerces to
      `None`; with `enabled=False` it does not raise.
- [ ] `ruff check src/ tests/` - clean.
