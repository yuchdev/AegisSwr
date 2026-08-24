# 01 - `ClaudeCodeSettings` class shape

**Parent task:** 02.0 Claude Code Settings & Config
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02 (this task), 03.0, 05.0 (downstream tasks)

## Objective

Create `aegis_swr/claude_code/__init__.py` (empty, versioned) and
`aegis_swr/claude_code/config.py` containing `ClaudeCodeSettings` — a Pydantic
`BaseSettings` subclass whose fields are sourced entirely from environment
variables per milestone contract **C5** and **C6 item 4**. When no env vars are
 set, the object must be constructible without error and must produce
`enabled=False` (backend not configured); any downstream code that receives
`enabled=False` treats the Claude Code backend as "not registered" without
raising (mirrors OpenClaude's `grpc_url=None` path).

This subtask defines the class scaffolding shared by both subtasks — the CSV env
source, the `__init__` `ValidationError`-unwrap, and the forward-declared
`ClaudeCodeConfigError` — plus the five non-security-guard fields:
`binary_path`, `enabled`, `allowed_tools`, `max_turns`, and `request_timeout_s`.
Subtask 02 adds `permission_mode` and `scratch_cwd` onto the same class.

## File: `aegis_swr/claude_code/config.py`

**Fields** (env var → field name → type → default):

| Env var                       | Field               | Type            | Default                    |
|-------------------------------|---------------------|-----------------|----------------------------|
| `CLAUDE_CODE_BINARY`          | `binary_path`       | `str`           | `"claude"`                 |
| `CLAUDE_CODE_ENABLED`         | `enabled`           | `bool`          | `False` (presence signal)  |
| `CLAUDE_CODE_ALLOWED_TOOLS`   | `allowed_tools`     | `list[str]`     | `["Read","Grep","Glob"]`   |
| `CLAUDE_CODE_MAX_TURNS`       | `max_turns`         | `int`           | `8`                        |
| `CLAUDE_CODE_REQUEST_TIMEOUT` | `request_timeout_s` | `int`           | `120`                      |

> `permission_mode` (`CLAUDE_CODE_PERMISSION_MODE`) and `scratch_cwd`
> (`CLAUDE_CODE_SCRATCH_CWD`) are added by
> [subtask 02](02-permission-mode-scratch-cwd.md) onto this same class.
> `auth_mode` (`CLAUDE_CODE_AUTH_MODE`) is added additively by Task 04.0 (C7);
> it is deliberately absent here (see the parent README's additive-extension
> guarantee).

```python
from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from pydantic import Field, ValidationError, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_CSV_LIST_FIELDS: frozenset[str] = frozenset({"allowed_tools"})

#: Canonical Claude Code tool names accepted in ``allowed_tools`` (same set as
#: OpenClaude's C1 tool vocabulary).
_KNOWN_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "LS",
        "Grep",
        "WebFetch",
        "WebSearch",
        "Agent",
        "Task",
        "TodoRead",
        "TodoWrite",
    }
)
#: Tools that can mutate the host filesystem; default OFF for forensic read-only
#: mode. Permitted by the validator but warned about loudly (C6 item 3).
_WRITE_CAPABLE_TOOLS: frozenset[str] = frozenset({"Write", "Edit"})


class ClaudeCodeConfigError(ValueError):
    """Raised when :class:`ClaudeCodeSettings` receives an invalid value.

    Forward declaration only. The canonical definition is moved to
    ``aegis_swr/claude_code/exceptions.py`` in Task 05.0; this placeholder is
    then replaced by a re-export alias so
    ``aegis_swr.claude_code.config.ClaudeCodeConfigError`` keeps resolving to
    the same object with **no** downstream import-path change (exactly as
    ``OpenClaudeConfigError`` was handled in Milestone 0004).

    :param field: Name of the offending field.
    :param reason: Human-readable explanation of the violation. Must never
        contain a secret, credential, or incident-payload value (C13).
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"ClaudeCodeSettings.{field}: {reason}")


def _split_csv(value: object) -> object:
    """Split a plain comma-separated string into a stripped, non-empty list.

    Lists (and any non-``str`` value) pass through untouched.

    :param value: The raw value from the environment or a direct constructor
        call.
    :return: A ``list[str]`` when ``value`` is a ``str``, else ``value``
        unchanged.
    """
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class _CsvEnvSettingsSource(EnvSettingsSource):
    """Env source that accepts comma-separated values for CSV list fields.

    pydantic-settings v2 JSON-decodes ``list[str]`` fields sourced from the
    environment before field validators run, so a value such as
    ``CLAUDE_CODE_ALLOWED_TOOLS=Read,Grep,Glob`` would raise a
    ``SettingsError``. This source splits such values on commas instead, while
    leaving all other fields to the default decoding. Identical in shape to
    OpenClaude's ``_CsvEnvSettingsSource`` (C5).
    """

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        """Split comma-separated env values for list fields, else defer to the base."""
        if field_name in _CSV_LIST_FIELDS and isinstance(value, str):
            return _split_csv(value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class ClaudeCodeSettings(BaseSettings):
    """Environment-sourced configuration for the Claude Code (`claude` CLI) backend.

    Presence signal: ``enabled`` (``CLAUDE_CODE_ENABLED``). Being on ``PATH`` is
    deliberately **not** a signal (plan.md, Backend B) — a host-permission
    backend must never activate silently.

    :ivar binary_path: Binary name or full path to the ``claude`` executable.
        Defaults to the bare command ``"claude"``, resolved via ``PATH``.
    :ivar enabled: Explicit opt-in switch and the backend's presence signal.
        ``False`` means the backend is not registered (C2/C6).
    :ivar allowed_tools: Claude Code tool names passed to ``--allowedTools``.
        Defaults to the read-only set ``["Read","Grep","Glob"]``; write-capable
        tools are OFF by default (C6 item 3).
    :ivar max_turns: Upper bound on the agent's turn count for a single
        ``delegate()`` (maps to the CLI's turn cap in Task 03.0).
    :ivar request_timeout_s: Per-``delegate()`` subprocess deadline, in seconds.
    """

    model_config = SettingsConfigDict(env_prefix="CLAUDE_CODE_", populate_by_name=True)

    binary_path: str = Field(default="claude", validation_alias="CLAUDE_CODE_BINARY")
    enabled: bool = False
    allowed_tools: list[str] = ["Read", "Grep", "Glob"]
    max_turns: int = 8
    request_timeout_s: int = Field(default=120, validation_alias="CLAUDE_CODE_REQUEST_TIMEOUT")

    def __init__(self, **values: Any):
        """Construct the settings, surfacing :class:`ClaudeCodeConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field validator into a
        ``ValidationError``; this unwraps the first such
        :class:`ClaudeCodeConfigError` so callers see the domain error the
        validators actually raised (C5). Reused unchanged by subtask 02's and
        Task 04.0's validators.
        """
        try:
            super().__init__(**values)
        except ValidationError as exc:
            for error in exc.errors():
                ctx = error.get("ctx")
                if ctx is not None and isinstance(ctx.get("error"), ClaudeCodeConfigError):
                    raise ctx["error"] from None
            raise

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Swap the default env source for one that splits comma-separated lists."""
        return (
            init_settings,
            _CsvEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_csv_lists(cls, v: object) -> object:
        """Accept a comma-separated string for ``allowed_tools`` passed in code.

        The env-var path is handled by :class:`_CsvEnvSettingsSource`; this
        covers callers passing a raw string directly to the constructor.
        """
        return _split_csv(v)

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject unknown Claude Code tool names; warn on write-capable tools."""
        ...

    @field_validator("max_turns")
    @classmethod
    def _validate_max_turns(cls, v: int) -> int:
        """Enforce max_turns >= 1."""
        ...

    @field_validator("request_timeout_s")
    @classmethod
    def _validate_request_timeout(cls, v: int) -> int:
        """Enforce request_timeout_s > 0."""
        ...
```

## Implementation notes

- `binary_path`: no validation beyond type — a bare command name resolved via
  `PATH` or an absolute path both remain valid, exactly like OpenClaude's
  `process_binary`. Existence/executability is a **runtime** concern for
  Task 03.0's spawn path and Task 04.0's auth probe, not a settings-shape
  concern.
- `enabled`: the presence signal. Pydantic's standard bool env-coercion applies
  (`true`/`1`/`yes` → `True`). An unset variable yields the falsy default
  `False`, meaning "backend not configured" — this must never raise (C5). This
  is the field `HarnessSettings` (Task 01.0) reads to detect the Claude Code
  presence signal for C2 selection.
- `allowed_tools`: each entry must be in `_KNOWN_TOOLS`; raise
  `ClaudeCodeConfigError(field="allowed_tools", reason=...)` for any unknown
  name (naming only the offending non-secret tool strings). Write-capable tools
  (`Write`, `Edit`) are permitted but must trigger a single `logger.warning`
  noting forensic read-only mode is compromised — identical discipline to
  `OpenClaudeSettings._validate_allowed_tools`. The default list omits `Bash`
  (unlike OpenClaude) because Claude Code has no separate Bash-allowlist guard
  in this milestone; an operator adding `Bash` widens the host-command surface
  and should do so deliberately.
- `max_turns`: must be `>= 1`. Raise `ClaudeCodeConfigError` otherwise. A larger
  value trades cost/latency for depth; the default `8` mirrors a conservative
  non-interactive budget.
- `request_timeout_s`: must be a positive integer. Raise `ClaudeCodeConfigError`
  otherwise. Unlike OpenClaude there is no separate `connect_timeout_s` to
  compare against (one-shot subprocess, no channel-connect phase), so the
  cross-field check is intentionally absent.
- Env vars are parsed via `env_prefix="CLAUDE_CODE_"`; `binary_path` and
  `request_timeout_s` carry explicit `validation_alias`es because their env
  names (`CLAUDE_CODE_BINARY`, `CLAUDE_CODE_REQUEST_TIMEOUT`) do not follow the
  bare `prefix + field_name` convention — the same technique OpenClaude uses for
  `OPENCLAUDE_BINARY` / `OPENCLAUDE_REQUEST_TIMEOUT`.
- Empty-string coercion: consistent with the codebase memory on empty
  env/secret coercion, any string field whose value is a whitespace-only env
  expansion (an unset CI secret expanding to `""`) is treated as unset, not as a
  malformed value. `binary_path=""` must fall back to the `"claude"` default
  rather than crash construction.

## Constraints

- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` at the top of the file (C13).
- No `Any` in field types (the `Any` import is only for `__init__(**values)` and
  the env-source override signature); `ruff check src/ tests/` - clean.
- `ClaudeCodeConfigError` here is a temporary forward declaration; Task 05.0
  moves the canonical definition to `exceptions.py` and replaces this with a
  re-export alias — no downstream import-path changes when 05.0 lands.
- All validator errors and warnings name only field names and non-secret
  offending values; no credential, token, or incident-payload text (C13).
- No import of `ClaudeCodeSettings` in `aegis_swr/core/`, `aegis_swr/views/`, or
  `aegis_swr/code_intel/` (C3).

## Success criteria

- [ ] `ClaudeCodeSettings()` with no env vars set produces `enabled=False`, `binary_path="claude"`, `allowed_tools=["Read","Grep","Glob"]`, `max_turns=8`, `request_timeout_s=120`, without raising.
- [ ] `CLAUDE_CODE_ENABLED=true` yields `enabled=True`.
- [ ] `CLAUDE_CODE_ALLOWED_TOOLS=Read,Grep` (CSV env) parses to `["Read","Grep"]`.
- [ ] `ClaudeCodeSettings(allowed_tools=["Read","WriteFile"])` raises `ClaudeCodeConfigError` (`WriteFile` is not a recognized tool name).
- [ ] `ClaudeCodeSettings(allowed_tools=["Read","Write"])` does not raise but logs a single warning.
- [ ] `ClaudeCodeSettings(max_turns=0)` raises `ClaudeCodeConfigError`.
- [ ] `ClaudeCodeSettings(request_timeout_s=0)` raises `ClaudeCodeConfigError`.
- [ ] `CLAUDE_CODE_BINARY=""` (empty CI-secret expansion) falls back to `binary_path="claude"` without raising.
- [ ] `ruff check src/ tests/` - clean; `ruff` clean.
