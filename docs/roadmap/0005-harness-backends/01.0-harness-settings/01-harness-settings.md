# 01 - `HarnessSettings` class shape

**Parent task:** 01.0 Harness Settings & Selection Contract
**State:** ✅ Complete
**Depends on:** 03 (`harness/exceptions.py` — for `HarnessConfigError`)
**Blocks:** 02 (this task); 02.0, 06.0, 10.0 (downstream tasks)

## Objective

Create `aegis_swr/harness/__init__.py` and
`aegis_swr/harness/config.py` containing `HarnessSettings` — a Pydantic
`BaseSettings` subclass that composes the `AEGIS_CODE_INTEL_BACKEND` selector
field with one nested per-family settings sub-object, per milestone contract
**C1**. This subtask fixes the *shape*: the selector field, the enum that
constrains it, and the `default_factory` composition of the three backend
settings classes. The C2 selection/ambiguity *resolution* logic (the
`model_validator`, `active_backend`, and `presence_signals`) is added to this
same class by subtask 02.

When no env vars are set, the object must be constructible without error: the
selector resolves to `None` and each nested settings object constructs at its
own defaults (its presence signal absent). A no-config `HarnessSettings()` means
"no backend selected, none auto-selectable" — never a construction crash.

## File: `aegis_swr/harness/config.py`

**Selector field** (env var → field → type → default):

| Env var                    | Field     | Type                       | Default | Notes                                                                                     |
|----------------------------|-----------|----------------------------|---------|-------------------------------------------------------------------------------------------|
| `AEGIS_CODE_INTEL_BACKEND` | `backend` | `Optional[HarnessBackend]` | `None`  | `openclaude` \| `claude_code` \| `openhands`; `None` (or empty string) = auto-select (C2) |

**Nested sub-settings** (composed via `default_factory`, each sources its own
family's env vars — C1/C5):

| Field         | Type                 | Default factory      | Presence signal (C2)     |
|---------------|----------------------|----------------------|--------------------------|
| `openclaude`  | `OpenClaudeSettings` | `OpenClaudeSettings` | `grpc_url is not None`   |
| `claude_code` | `ClaudeCodeSettings` | `ClaudeCodeSettings` | `enabled is True`        |
| `openhands`   | `OpenHandsSettings`  | `OpenHandsSettings`  | `server_url is not None` |

```python
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aegis_swr.harness.exceptions import HarnessConfigError
from aegis_swr.openclaude.config import OpenClaudeSettings

# Forward references (documentation-only; see task README "Forward references").
# ClaudeCodeSettings lands with Task 02.0, OpenHandsSettings with Task 06.0.
# Both MUST mirror OpenClaudeSettings' shape (C5) and expose the presence signal
# named in the table above. Until those tasks land, this import is the single
# named-but-unresolved seam; the selection logic is exercised against a stub.
from aegis_swr.claude_code.config import ClaudeCodeSettings  # Task 02.0
from aegis_swr.openhands.config import OpenHandsSettings      # Task 06.0


class HarnessBackend(str, Enum):
    """The code-intelligence backend families the harness can select (C1).

    A ``str`` enum so the value round-trips to/from ``AEGIS_CODE_INTEL_BACKEND``
    and serialises as its bare family name (e.g. ``"openclaude"``). The member
    set is the *closed* universe of backends this milestone ships; adding a
    fourth backend is a deliberate, reviewed change to this enum.

    :cvar OPENCLAUDE: The OpenClaude gRPC sidecar (unchanged from 0004).
    :cvar CLAUDE_CODE: The installed ``claude`` CLI, one-shot subprocess (C6).
    :cvar OPENHANDS: The Docker-sandboxed OpenHands sidecar (C8).
    """

    OPENCLAUDE = "openclaude"
    CLAUDE_CODE = "claude_code"
    OPENHANDS = "openhands"


class HarnessSettings(BaseSettings):
    """Neutral selection layer for the code-intelligence harness (C1, C2, C5).

    Composes the ``AEGIS_CODE_INTEL_BACKEND`` selector with one nested settings
    sub-object per backend family. Each nested object sources its own family's
    environment variables (C1); ``HarnessSettings`` itself reads only the
    selector variable and never touches another family's ``os.environ`` keys.
    The single-active-backend selection and ambiguity resolution (C2) are added
    to this class by subtask 02.

    :ivar backend: The explicitly selected backend family, or ``None`` to
        auto-select from presence signals (C2). Sourced from
        ``AEGIS_CODE_INTEL_BACKEND``; an empty/whitespace value is treated as
        unset (``None``), not as an invalid selector.
    :ivar openclaude: OpenClaude settings (unchanged from 0004); presence signal
        ``grpc_url is not None``.
    :ivar claude_code: Claude Code settings (Task 02.0); presence signal
        ``enabled is True`` (``CLAUDE_CODE_ENABLED``).
    :ivar openhands: OpenHands settings (Task 06.0); presence signal
        ``server_url is not None`` (``OPENHANDS_SERVER_URL``).
    """

    model_config = SettingsConfigDict(populate_by_name=True)

    backend: Optional[HarnessBackend] = Field(
        default=None, validation_alias="AEGIS_CODE_INTEL_BACKEND"
    )
    openclaude: OpenClaudeSettings = Field(default_factory=OpenClaudeSettings)
    claude_code: ClaudeCodeSettings = Field(default_factory=ClaudeCodeSettings)
    openhands: OpenHandsSettings = Field(default_factory=OpenHandsSettings)

    def __init__(self, **values: Any):
        """Construct the settings, surfacing :class:`HarnessConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field or model
        validator into a ``ValidationError``; this unwraps the first such
        :class:`HarnessConfigError` (the bad-selector case here, the ambiguity
        case added by subtask 02) so callers see the domain error the validators
        actually raised, exactly as :class:`OpenClaudeSettings` does.
        """
        try:
            super().__init__(**values)
        except ValidationError as exc:
            for error in exc.errors():
                ctx = error.get("ctx")
                if ctx is not None and isinstance(ctx.get("error"), HarnessConfigError):
                    raise ctx["error"] from None
            raise

    @field_validator("backend", mode="before")
    @classmethod
    def _coerce_and_validate_selector(cls, v: object) -> object:
        """Treat an empty selector as unset; reject an unrecognised value.

        An unset environment variable or CI secret expands to ``""`` (e.g.
        ``AEGIS_CODE_INTEL_BACKEND: ${{ secrets.MISSING }}``); that must mean
        "auto-select" (``None``), not a construction crash. A non-empty value
        that is not a :class:`HarnessBackend` member raises
        :class:`HarnessConfigError` naming only the offending field and the
        rejected value — never any secret.
        """
        ...
```

## Implementation notes

- **`backend`** is sourced via `validation_alias="AEGIS_CODE_INTEL_BACKEND"`
  rather than an `env_prefix`, because the selector variable shares no common
  prefix with the nested families (`OPENCLAUDE_*`, `CLAUDE_CODE_*`,
  `OPENHANDS_*`). Do **not** set an `env_prefix` on `HarnessSettings` that would
  accidentally capture the nested families' variables.
- **Empty-selector coercion** (`_coerce_and_validate_selector`): mirror the
  `OpenClaudeSettings._validate_grpc_url` treatment of `""` — an empty or
  whitespace-only value coerces to `None` (auto-select), never a validation
  error. A non-empty value not in `HarnessBackend` raises
  `HarnessConfigError(field="backend", reason=...)` naming the rejected value;
  do not let Pydantic's native enum `ValidationError` surface instead (the
  `__init__` unwrap only re-raises `HarnessConfigError`).
- **Nested composition** uses `default_factory=<SettingsClass>` so each family's
  settings object is constructed once, reading its own env, when
  `HarnessSettings()` is instantiated. This is the C5 composition convention:
  sub-settings into `HarnessSettings` via `default_factory`; `HarnessSettings`
  into the top-level `Settings` via `default_factory` **later** (C12, Task 10.0
  — out of scope here).
- **Forward references.** The `claude_code` / `openhands` imports name classes
  delivered by Tasks 02.0 / 06.0 (see the task README). This subtask does not
  block on them; where they are not yet present, the coding agent may compose
  against a minimal stub that exposes the C2 presence signal so the shape and
  subtask-02 resolution can be unit-tested in isolation. The presence-signal
  attribute names (`grpc_url`, `enabled`, `server_url`) are fixed by C2 and must
  not drift.
- **No `os.environ` reads for other families.** `HarnessSettings` reads only
  `AEGIS_CODE_INTEL_BACKEND`. Every presence signal is read off the already-
  constructed nested settings object, never re-derived from the environment.

## Constraints

- No `Any` in field *types* (the `**values: Any` on `__init__` mirrors `OpenClaudeSettings` and is permitted); no new `# type: ignore`.
- `HarnessConfigError` is imported from `harness/exceptions.py` (subtask 03) — not redefined here. `HarnessSettings` never imports `harness/composition.py` (it does not exist yet) and is not imported by `aegis_swr/core/`, `aegis_swr/views/`, or `aegis_swr/code_intel/` (C3).
- This subtask adds **no** selection resolution or ambiguity check — that is subtask 02. Construction of `HarnessSettings()` with any combination of presence signals must not raise here (the ambiguity raise arrives with 02).

## Success criteria

- [ ] `aegis_swr/harness/__init__.py` exists and `aegis_swr/harness/config.py` defines `HarnessBackend` and `HarnessSettings`.
- [ ] `harness/__init__.py` re-exports **only** dependency-free types — the `typing`-only
      `HarnessConfigError` / `HarnessUnavailableError` from subtask 03 — and deliberately does
      **not** re-export `HarnessSettings` (which would pull `pydantic` into the package
      namespace) nor anything from the Task 10.0 composition root. This mirrors
      `openclaude/__init__.py`, which re-exports its payload-free event/exception types while
      explicitly withholding `OpenClaudeTool`/`OpenClaudeProcess`/`OpenClaudeGrpcClient` to keep
      `grpc` out of the namespace (C3).
- [ ] `HarnessSettings()` with no env vars set constructs without raising; `backend is None` and each nested settings object holds its family defaults (`openclaude.grpc_url is None`, `claude_code.enabled is False`, `openhands.server_url is None`).
- [ ] `HarnessSettings(backend="openclaude")` constructs with `backend is HarnessBackend.OPENCLAUDE`.
- [ ] `AEGIS_CODE_INTEL_BACKEND=""` (empty) resolves to `backend is None` (auto-select), not a validation error.
- [ ] `HarnessSettings(backend="not_a_backend")` raises `HarnessConfigError` (not a bare Pydantic `ValidationError`) naming field `"backend"`.
- [ ] Each nested sub-object is sourced from its own family's env vars only — e.g. `OPENCLAUDE_GRPC_URL=localhost:50051` sets `settings.openclaude.grpc_url == "localhost:50051"` and leaves `claude_code` / `openhands` at defaults.
- [ ] `HarnessSettings` reads no environment variable other than `AEGIS_CODE_INTEL_BACKEND` (verified by asserting nested-family values come only through their own settings classes).
- [ ] No import of `HarnessSettings` appears in `aegis_swr/core/`, `aegis_swr/views/`, or `aegis_swr/code_intel/` (C3).
- [ ] `ruff check src/ tests/` - clean; no `Any` in field types.
