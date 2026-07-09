"""Environment-sourced configuration for the OpenClaude integration.

This module hosts :class:`OpenClaudeSettings`, a Pydantic ``BaseSettings``
subclass whose fields are sourced entirely from environment variables
(milestone contract C1). :class:`OpenClaudeConfigError` is re-exported from
``aegis_swr.openclaude.exceptions`` (its canonical home as of Task 05.0) so
existing imports of ``aegis_swr.openclaude.config.OpenClaudeConfigError``
continue to resolve to the same object.
"""

from __future__ import annotations

import re
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

from aegis_swr.openclaude.exceptions import OpenClaudeConfigError

_CSV_LIST_FIELDS: frozenset[str] = frozenset({"allowed_tools", "bash_allowlist"})

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
_WRITE_CAPABLE_TOOLS: frozenset[str] = frozenset({"Write", "Edit"})
_GRPC_URL_PATTERN = r"^[a-zA-Z0-9.\-]+(:[0-9]+)?\Z"
_BASH_ALLOWLIST_WARN: frozenset[str] = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "ksh",
        "fish",
        "python",
        "python3",
        "node",
        "ruby",
        "perl",
        "curl",
        "wget",
        "rm",
        "mv",
        "dd",
        "chmod",
        "chown",
        "eval",
        "env",
        "xargs",
    }
)
# find/cat are spec defaults; their arg-level enforcement (find -exec/-delete,
# cat target restriction) is deferred to Task 04.0's Bash gate - see status.md
# security follow-up.


def _split_csv(value: object) -> object:
    """Split a plain comma-separated string into a stripped, non-empty list.

    Lists (and any non-``str`` value) pass through untouched.
    """
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class _CsvEnvSettingsSource(EnvSettingsSource):
    """Env source that accepts comma-separated values for CSV list fields.

    pydantic-settings v2 JSON-decodes ``list[str]`` fields sourced from the
    environment before field validators run, so a value such as
    ``OPENCLAUDE_ALLOWED_TOOLS=Read,Grep,Glob,Bash`` would raise a
    ``SettingsError``. This source splits such values on commas instead, while
    leaving all other fields to the default decoding.
    """

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        if field_name in _CSV_LIST_FIELDS and isinstance(value, str):
            return _split_csv(value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class OpenClaudeSettings(BaseSettings):
    """Environment-sourced configuration for the OpenClaude integration.

    :ivar grpc_url: Host[:port] of the OpenClaude gRPC sidecar. ``None`` means
        the backend is not registered (C4).
    :ivar allowed_tools: Claude Code tool names OpenClaude is permitted to use.
    :ivar bash_allowlist: Binary names OpenClaude's ``Bash`` tool may invoke.
    :ivar max_response_tokens: Hard cap on streamed response length.
    :ivar connect_timeout_s: gRPC channel connect timeout, in seconds.
    :ivar request_timeout_s: Per-request stream deadline, in seconds.
    :ivar auto_start: Whether ``app.py`` starts the sidecar process itself.
    :ivar process_binary: Binary name or full path to the OpenClaude
        executable. Defaults to the bare command ``"openclaude"``, resolved
        via ``PATH`` - the global npm install places it there. Override with a
        full path for a non-standard install location.
    :ivar use_tls: Select a TLS gRPC channel in Task 02.0 when true; insecure
        otherwise. Defaults to insecure for a locally co-located sidecar.
    """

    model_config = SettingsConfigDict(env_prefix="OPENCLAUDE_", populate_by_name=True)

    grpc_url: Optional[str] = None
    allowed_tools: list[str] = ["Read", "Grep", "Glob", "Bash"]
    bash_allowlist: list[str] = ["gtags", "global", "semgrep", "rg", "find", "cat"]
    max_response_tokens: int = Field(default=4096, validation_alias="OPENCLAUDE_MAX_TOKENS")
    connect_timeout_s: int = Field(default=10, validation_alias="OPENCLAUDE_CONNECT_TIMEOUT")
    request_timeout_s: int = Field(default=120, validation_alias="OPENCLAUDE_REQUEST_TIMEOUT")
    auto_start: bool = False
    process_binary: str = Field(default="openclaude", validation_alias="OPENCLAUDE_BINARY")
    use_tls: bool = False

    def __init__(self, **values: Any) -> None:
        """Construct the settings, surfacing :class:`OpenClaudeConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field validator into a
        ``ValidationError``; this unwraps the first such
        :class:`OpenClaudeConfigError` so callers see the domain error the
        validators actually raised, per the milestone contract.
        """
        try:
            super().__init__(**values)
        except ValidationError as exc:
            for error in exc.errors():
                ctx = error.get("ctx")
                if ctx is not None and isinstance(ctx.get("error"), OpenClaudeConfigError):
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

    @field_validator("allowed_tools", "bash_allowlist", mode="before")
    @classmethod
    def _coerce_csv_lists(cls, v: object) -> object:
        """Accept a comma-separated string for a CSV list field passed in code.

        The env-var path is handled by :class:`_CsvEnvSettingsSource`; this
        covers callers passing a raw string directly to the constructor. Lists
        pass through untouched.
        """
        return _split_csv(v)

    @field_validator("grpc_url")
    @classmethod
    def _validate_grpc_url(cls, v: Optional[str]) -> Optional[str]:
        """Reject scheme-prefixed URLs; only bare host[:port] is accepted."""
        if v is None:
            return v

        if v.startswith(("http://", "https://")):
            raise OpenClaudeConfigError(
                field="grpc_url",
                reason="URL must not carry a scheme; use bare host[:port]",
            )
        if re.match(_GRPC_URL_PATTERN, v) is None:
            raise OpenClaudeConfigError(
                field="grpc_url",
                reason="value must match host[:port] (letters, digits, '.', '-')",
            )
        return v

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject unknown Claude Code tool names; warn on Write/Edit."""
        unknown = [tool for tool in v if tool not in _KNOWN_TOOLS]
        if unknown:
            raise OpenClaudeConfigError(
                field="allowed_tools",
                reason=f"unknown Claude Code tool name(s): {unknown}",
            )
        write_capable = sorted(_WRITE_CAPABLE_TOOLS.intersection(v))
        if write_capable:
            logger.warning(
                "OpenClaude allowed_tools grants write-capable tool(s) {}; read-only forensic mode is compromised",
                write_capable,
            )
        return v

    @field_validator("bash_allowlist")
    @classmethod
    def _validate_bash_allowlist(cls, v: list[str]) -> list[str]:
        """Warn (never reject) when the allowlist names a dangerous binary.

        Defense-in-depth only: unlike ``allowed_tools`` this must not reject, so
        the spec's default set stays valid. Emits a single ``logger.warning``
        naming just the offending binaries - never any payload or secret.
        """
        dangerous = sorted(_BASH_ALLOWLIST_WARN.intersection(v))
        if dangerous:
            logger.warning(
                "OpenClaude bash_allowlist grants dangerous binary/-ies {}; "
                "arbitrary command execution surface is widened",
                dangerous,
            )
        return v

    @field_validator("max_response_tokens")
    @classmethod
    def _validate_max_response_tokens(cls, v: int) -> int:
        """Enforce the [256, 65536] range."""
        if not 256 <= v <= 65536:
            raise OpenClaudeConfigError(
                field="max_response_tokens",
                reason="must be within [256, 65536]",
            )
        return v

    @field_validator("connect_timeout_s")
    @classmethod
    def _validate_connect_timeout(cls, v: int) -> int:
        """Enforce connect_timeout_s > 0."""
        if v <= 0:
            raise OpenClaudeConfigError(
                field="connect_timeout_s",
                reason="must be a positive integer",
            )
        return v

    @field_validator("request_timeout_s")
    @classmethod
    def _validate_request_timeout(cls, v: int, info: ValidationInfo) -> int:
        """Enforce request_timeout_s > connect_timeout_s and both positive."""
        if v <= 0:
            raise OpenClaudeConfigError(
                field="request_timeout_s",
                reason="must be a positive integer",
            )
        connect_timeout_s = info.data.get("connect_timeout_s")
        if connect_timeout_s is not None and v <= connect_timeout_s:
            raise OpenClaudeConfigError(
                field="request_timeout_s",
                reason=f"must be greater than connect_timeout_s ({connect_timeout_s})",
            )
        return v
