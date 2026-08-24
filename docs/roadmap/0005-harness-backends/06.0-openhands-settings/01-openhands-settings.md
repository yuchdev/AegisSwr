# 01 - `OpenHandsSettings` Pydantic class

**Parent task:** 06.0 OpenHands Settings & Config
**State:** ⬜ Not started
**Depends on:** Task 01.0 (Harness Settings & Selection Contract) — sibling only,
no direct code dependency; this subtask defines a self-contained settings class
that Task 01.0 / 10.0 later composes into `HarnessSettings` via `default_factory`
(C5). It can be authored and unit-tested in isolation before that composition
lands.
**Blocks:** 02 (this task), 07.0, 08.0, 09.0 (downstream tasks)

## Objective

Create `aegis_swr/openhands/__init__.py` (empty, versioned) and
`aegis_swr/openhands/config.py` containing `OpenHandsSettings` - a Pydantic
`BaseSettings` subclass whose fields are sourced entirely from environment
variables per milestone contracts C5 (settings-shape convention) and C8 item 5
(the field list). When no env vars are set the object must be constructible
without error and must produce `server_url=None` (backend not registered). Any
downstream code that receives a `None` `server_url` must treat it as "backend
unavailable" without raising (mirrors OpenClaude's `grpc_url=None` semantics,
0004 C4 / C2).

This subtask defines the **six documented fields** plus the forward declaration
of `OpenHandsConfigError`. The `runtime_mode` field is defined here as a
membership-validated string defaulting to the sandboxed Docker runtime; the
**cross-field enforcement** that a non-sandboxed runtime requires an explicit
override belongs to subtask 02.

## File: `aegis_swr/openhands/config.py`

**Fields** (env var → field name → type → default):

| Env var                     | Field                | Type            | Default                                  |
|-----------------------------|----------------------|-----------------|------------------------------------------|
| `OPENHANDS_SERVER_URL`      | `server_url`         | `Optional[str]` | `None` (the presence signal, C2/C8)      |
| `OPENHANDS_RUNTIME`         | `runtime_mode`       | `str`           | `"docker"` (the sandboxed runtime, C8)   |
| `OPENHANDS_ALLOWED_TOOLS`   | `allowed_tools`      | `list[str]`     | `["read", "grep", "glob", "browse"]` (read-only) |
| `OPENHANDS_CONNECT_TIMEOUT` | `connect_timeout_s`  | `int`           | `10`                                     |
| `OPENHANDS_REQUEST_TIMEOUT` | `request_timeout_s`  | `int`           | `120`                                    |
| `OPENHANDS_AUTO_START`      | `auto_start`         | `bool`          | `False`                                  |

```python
from __future__ import annotations

from typing import Any, Optional

from loguru import logger
from pydantic import Field, ValidationError, ValidationInfo, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_CSV_LIST_FIELDS: frozenset[str] = frozenset({"allowed_tools"})

# Runtime modes. Docker is the sandboxed default; `local` runs on the host with
# no container isolation. `remote` targets an OpenHands-managed remote sandbox.
_SANDBOXED_RUNTIMES: frozenset[str] = frozenset({"docker", "remote"})
_UNSANDBOXED_RUNTIMES: frozenset[str] = frozenset({"local"})
_KNOWN_RUNTIMES: frozenset[str] = _SANDBOXED_RUNTIMES | _UNSANDBOXED_RUNTIMES

# OpenHands action/tool names permitted in the read-only forensic posture.
_KNOWN_TOOLS: frozenset[str] = frozenset(
    {"read", "grep", "glob", "browse", "think", "edit", "write", "run"}
)
_WRITE_CAPABLE_TOOLS: frozenset[str] = frozenset({"edit", "write", "run"})


class OpenHandsConfigError(ValueError):
    """Raised when :class:`OpenHandsSettings` receives an invalid value.

    Formally moved to ``aegis_swr/openhands/exceptions.py`` in Task 09.0. This
    forward declaration is kept here so Task 06.0 can raise without depending on
    09.0; when 09.0 lands, this class is replaced by a re-export alias and the
    import path ``aegis_swr.openhands.config.OpenHandsConfigError`` keeps
    resolving to the same object (mirrors ``OpenClaudeConfigError``).

    :param field: Name of the offending field.
    :param reason: Human-readable explanation of the violation - never the
        offending value, so no ``server_url`` credential or payload text leaks
        into logs or tracebacks (C13).
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"OpenHandsSettings.{field}: {reason}")


def _split_csv(value: object) -> object:
    """Split a plain comma-separated string into a stripped, non-empty list.

    Lists (and any non-``str`` value) pass through untouched.
    """
    ...


class _CsvEnvSettingsSource(EnvSettingsSource):
    """Env source that accepts comma-separated values for CSV list fields.

    pydantic-settings v2 JSON-decodes ``list[str]`` env values before field
    validators run, so ``OPENHANDS_ALLOWED_TOOLS=read,grep,glob`` would raise a
    ``SettingsError``. This source splits such values on commas instead, exactly
    as ``OpenClaudeSettings`` does (C5), leaving all other fields to the default
    decoding.
    """

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        """Split comma-separated env values for list fields, else defer to base."""
        ...


class OpenHandsSettings(BaseSettings):
    """Environment-sourced configuration for the OpenHands backend.

    :ivar server_url: Base REST/WS URL of the OpenHands sidecar (e.g.
        ``http://localhost:3000``). ``None`` means the backend is not registered
        - the presence signal the harness reads to auto-select OpenHands (C2/C8).
    :ivar runtime_mode: OpenHands runtime selector. Defaults to ``"docker"`` -
        the Docker-sandboxed runtime that is this backend's defining security
        property (C8). Selecting a non-sandboxed runtime is gated by subtask 02.
    :ivar allowed_tools: OpenHands action/tool names the runtime is permitted to
        use. Defaults to a read-only forensic set; write-capable tools warn.
    :ivar connect_timeout_s: REST/WS connect timeout, in seconds.
    :ivar request_timeout_s: Per-request stream deadline, in seconds.
    :ivar auto_start: Whether the composition root starts the sidecar itself
        (managed mode) versus health-checking an already-running server
        (external mode). Consumed by ``OpenHandsProcess`` in Task 07.0.
    """

    model_config = SettingsConfigDict(env_prefix="OPENHANDS_", populate_by_name=True)

    server_url: Optional[str] = None
    runtime_mode: str = "docker"
    allowed_tools: list[str] = ["read", "grep", "glob", "browse"]
    connect_timeout_s: int = Field(default=10, validation_alias="OPENHANDS_CONNECT_TIMEOUT")
    request_timeout_s: int = Field(default=120, validation_alias="OPENHANDS_REQUEST_TIMEOUT")
    auto_start: bool = False

    def __init__(self, **values: Any):
        """Construct the settings, surfacing :class:`OpenHandsConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field validator into a
        ``ValidationError``; this unwraps the first such
        :class:`OpenHandsConfigError` so callers see the domain error the
        validators actually raised, exactly as ``OpenClaudeSettings`` does (C5).
        """
        ...

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
        ...

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_csv_lists(cls, v: object) -> object:
        """Accept a comma-separated string for the CSV list field passed in code."""
        ...

    @field_validator("server_url")
    @classmethod
    def _validate_server_url(cls, v: Optional[str]) -> Optional[str]:
        """Require a well-formed ``http(s)://host[:port]`` URL, or treat as unset.

        An empty or whitespace-only value is treated as *unset* (``None``), not
        as a malformed URL - an unset env var or CI secret expands to ``""``
        (e.g. ``OPENHANDS_SERVER_URL: ${{ secrets.MISSING }}``), which must mean
        "OpenHands not configured" rather than crash construction at import time.
        """
        ...

    @field_validator("runtime_mode")
    @classmethod
    def _validate_runtime_mode(cls, v: str) -> str:
        """Reject any runtime name not in ``_KNOWN_RUNTIMES``.

        Sandbox *enforcement* (rejecting a non-Docker runtime without the
        explicit override) is a cross-field concern and lives in subtask 02;
        this validator only checks the value is a recognised runtime name.
        """
        ...

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject unknown OpenHands tool names; warn on write-capable tools."""
        ...

    @field_validator("connect_timeout_s")
    @classmethod
    def _validate_connect_timeout(cls, v: int) -> int:
        """Enforce connect_timeout_s > 0."""
        ...

    @field_validator("request_timeout_s")
    @classmethod
    def _validate_request_timeout(cls, v: int, info: ValidationInfo) -> int:
        """Enforce request_timeout_s > connect_timeout_s and both positive."""
        ...
```

## Implementation notes

- `server_url`: when not `None`/blank, must parse as an `http://` or `https://`
  URL with a non-empty host (the client upgrades to `ws`/`wss` for the event
  stream itself in Task 07.0; the setting carries the base HTTP origin). This is
  the **inverse** of `OpenClaudeSettings.grpc_url`, which requires a *bare*
  host[:port] with no scheme — OpenHands is a REST/WS server, so the scheme is
  meaningful and required. Raise `OpenHandsConfigError(field="server_url",
  reason=...)` on a malformed value; **never** echo the value in the reason
  (it may embed credentials/userinfo). Blank → `None` per the empty-env
  coercion rule.
- `runtime_mode`: must be a member of `_KNOWN_RUNTIMES`. Raise
  `OpenHandsConfigError(field="runtime_mode", reason=...)` for an unknown name.
  The default `"docker"` is sandboxed; the sandbox-vs-override enforcement is
  subtask 02's model-validator, not this field validator.
- `allowed_tools`: each entry must be in `_KNOWN_TOOLS`. Raise
  `OpenHandsConfigError(field="allowed_tools", reason=...)` for any unknown
  name. Write-capable tools (`edit`, `write`, `run`) are permitted by the
  validator but must trigger a single `logger.warning` naming only the offending
  tools - read-only forensic mode is compromised, exactly as
  `OpenClaudeSettings._validate_allowed_tools` warns on `Write`/`Edit` (C5).
- `connect_timeout_s`, `request_timeout_s`: positive integers;
  `request_timeout_s` must be `> connect_timeout_s` (identical rule and error
  shape to `OpenClaudeSettings`).
- Env vars are parsed via `env_prefix="OPENHANDS_"`; `list[str]` fields accept a
  comma-separated string from the environment through `_CsvEnvSettingsSource`
  (so `OPENHANDS_ALLOWED_TOOLS=read,grep,glob`), and the `mode="before"`
  coercion validator covers callers passing a raw string directly to the
  constructor. This is the exact CSV-parsing convention C5 mandates.
- The three helpers/classes shown with `...` bodies (`_split_csv`,
  `_CsvEnvSettingsSource.prepare_field_value`, `__init__`,
  `settings_customise_sources`) are line-for-line analogues of
  `aegis_swr/openclaude/config.py`; hand them to `python-expert` as
  "replicate the OpenClaude pattern with the OpenHands field set", not as
  novel code.

## Constraints

- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` at the top of the file (C13).
- No `Any` in field types; `replace_optional.py --check` clean.
- `OpenHandsConfigError` here is a temporary forward declaration; Task 09.0
  moves the canonical definition to `openhands/exceptions.py` and replaces this
  with a re-export alias — no downstream import-path change when 09.0 lands.
- No secret or payload text in any validator error `reason` or log line — name
  the field, never the value (C13). `server_url` in particular may carry
  userinfo/credentials and must never be echoed.
- No import of the OpenHands client library, `grpc`, or any sibling backend
  package in this file (C3) — this is configuration only.

## Success criteria

- [ ] `OpenHandsSettings()` with no env vars set produces `server_url=None`,
      `runtime_mode="docker"`, `allowed_tools=["read","grep","glob","browse"]`
      and all documented defaults without raising.
- [ ] `OpenHandsSettings(server_url="")` (empty CI-secret expansion) produces
      `server_url=None`, not an error.
- [ ] `OpenHandsSettings(server_url="http://localhost:3000")` does not raise and
      preserves the value.
- [ ] `OpenHandsSettings(server_url="not-a-url")` raises `OpenHandsConfigError`
      whose message does not contain the offending value.
- [ ] `OpenHandsSettings(runtime_mode="podman")` raises `OpenHandsConfigError`
      (unknown runtime name).
- [ ] `OpenHandsSettings(allowed_tools=["read","teleport"])` raises
      `OpenHandsConfigError` because `teleport` is not a recognised tool name.
- [ ] `OpenHandsSettings(allowed_tools=["read","write"])` does not raise but
      logs a single warning naming `write`.
- [ ] `OpenHandsSettings(connect_timeout_s=100, request_timeout_s=10)` raises
      `OpenHandsConfigError`.
- [ ] `OPENHANDS_ALLOWED_TOOLS=read,grep,glob` in the environment yields
      `allowed_tools == ["read","grep","glob"]` (CSV env parsing, C5).
- [ ] `replace_optional.py --check` clean; no `Any` in field types; `ruff` clean.
