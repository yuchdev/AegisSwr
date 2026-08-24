"""Environment-sourced configuration for the OpenHands backend.

This module hosts :class:`OpenHandsSettings`, a Pydantic ``BaseSettings``
subclass whose fields are sourced entirely from environment variables (milestone
contracts C5 and C8). It mirrors the proven shape of
:class:`aegis_swr.openclaude.config.OpenClaudeSettings`: a per-family
``env_prefix``, CSV env parsing for ``list[str]`` fields, typed config-error
``field_validator``s unwrapped from Pydantic's ``ValidationError`` in
``__init__``, and presence-signal-as-``None``-default so an absent variable means
"backend not configured" rather than a construction crash.

:class:`OpenHandsConfigError` is **forward-declared here** so Task 06.0 can raise
without depending on Task 09.0. When Task 09.0 lands
``aegis_swr/openhands/exceptions.py``, this class is replaced by a re-export
alias and the import path ``aegis_swr.openhands.config.OpenHandsConfigError``
keeps resolving to the same object with no downstream change - exactly the
forward-declaration discipline ``aegis_swr/openclaude/config.py`` used for
``OpenClaudeConfigError``.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlsplit

from loguru import logger
from pydantic import Field, ValidationError, ValidationInfo, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

_CSV_LIST_FIELDS: frozenset[str] = frozenset({"allowed_tools"})

# Runtime modes. Docker is the sandboxed default; ``local`` runs on the host with
# no container isolation. ``remote`` targets an OpenHands-managed remote sandbox.
_SANDBOXED_RUNTIMES: frozenset[str] = frozenset({"docker", "remote"})
_UNSANDBOXED_RUNTIMES: frozenset[str] = frozenset({"local"})
_KNOWN_RUNTIMES: frozenset[str] = _SANDBOXED_RUNTIMES | _UNSANDBOXED_RUNTIMES

# OpenHands action/tool names permitted in the read-only forensic posture.
_KNOWN_TOOLS: frozenset[str] = frozenset({"read", "grep", "glob", "browse", "think", "edit", "write", "run"})
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
    :ivar field: The offending field name.
    :ivar reason: The payload-free violation explanation.
    """

    def __init__(self, field: str, reason: str):
        """Record the offending *field* and payload-free *reason* on the error."""
        self.field = field
        self.reason = reason
        super().__init__(f"OpenHandsSettings.{field}: {reason}")


def _split_csv(value: object) -> object:
    """Split a plain comma-separated string into a stripped, non-empty list.

    Lists (and any non-``str`` value) pass through untouched.

    :param value: The raw field value, either a comma-separated string or an
        already-decoded list.
    :return: A list of trimmed, non-empty tokens when *value* is a string;
        otherwise *value* unchanged.
    """
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


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
        """Split comma-separated env values for list fields, else defer to base.

        :param field_name: Name of the field being sourced.
        :param field: Pydantic field metadata.
        :param value: Raw environment value.
        :param value_is_complex: Whether pydantic considers the value complex.
        :return: A split list for CSV fields, otherwise the base decoding.
        """
        if field_name in _CSV_LIST_FIELDS and isinstance(value, str):
            return _split_csv(value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class OpenHandsSettings(BaseSettings):
    """Environment-sourced configuration for the OpenHands backend.

    :ivar server_url: Base REST/WS URL of the OpenHands sidecar (e.g.
        ``http://localhost:3000``). ``None`` means the backend is not registered
        - the presence signal the harness reads to auto-select OpenHands (C2/C8).
    :ivar runtime_mode: OpenHands runtime selector. Defaults to ``"docker"`` -
        the Docker-sandboxed runtime that is this backend's defining security
        property (C8). Selecting a non-sandboxed runtime is gated by the
        sandbox-enforcement model-validator.
    :ivar allowed_tools: OpenHands action/tool names the runtime is permitted to
        use. Defaults to a read-only forensic set; write-capable tools warn.
    :ivar connect_timeout_s: REST/WS connect timeout, in seconds.
    :ivar request_timeout_s: Per-request stream deadline, in seconds.
    :ivar auto_start: Whether the composition root starts the sidecar itself
        (managed mode) versus health-checking an already-running server
        (external mode). Consumed by ``OpenHandsProcess`` in Task 07.0.
    :ivar allow_unsandboxed_runtime: Explicit opt-out of the Docker sandbox.
        When ``False`` (default), selecting a non-sandboxed :attr:`runtime_mode`
        raises :class:`OpenHandsConfigError`; when ``True`` it is permitted but a
        loud warning is emitted and an ADR is required per milestone policy (C8).
    """

    model_config = SettingsConfigDict(env_prefix="OPENHANDS_", populate_by_name=True)

    server_url: Optional[str] = None
    runtime_mode: str = Field(default="docker", validation_alias="OPENHANDS_RUNTIME")
    allowed_tools: list[str] = ["read", "grep", "glob", "browse"]
    connect_timeout_s: int = Field(default=10, validation_alias="OPENHANDS_CONNECT_TIMEOUT")
    request_timeout_s: int = Field(default=120, validation_alias="OPENHANDS_REQUEST_TIMEOUT")
    auto_start: bool = False
    allow_unsandboxed_runtime: bool = Field(default=False, validation_alias="OPENHANDS_ALLOW_UNSANDBOXED")

    def __init__(self, **values: Any):
        """Construct the settings, surfacing :class:`OpenHandsConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field or model
        validator into a ``ValidationError``; this unwraps the first such
        :class:`OpenHandsConfigError` so callers see the domain error the
        validators actually raised, exactly as ``OpenClaudeSettings`` does (C5).

        :param values: Field values passed directly to the constructor.
        """
        try:
            super().__init__(**values)
        except ValidationError as exc:
            for error in exc.errors():
                ctx = error.get("ctx")
                if ctx is not None and isinstance(ctx.get("error"), OpenHandsConfigError):
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
        """Swap the default env source for one that splits comma-separated lists.

        :param settings_cls: The settings class being configured.
        :param init_settings: Source for values passed to ``__init__``.
        :param env_settings: The default environment source (replaced here).
        :param dotenv_settings: Source for ``.env`` files.
        :param file_secret_settings: Source for file-based secrets.
        :return: The ordered source tuple with the CSV-aware env source.
        """
        return (
            init_settings,
            _CsvEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator("auto_start", "allow_unsandboxed_runtime", mode="before")
    @classmethod
    def _coerce_bool_flags(cls, v: object) -> object:
        """Treat an empty/whitespace-only bool value as the field default (``False``).

        An unset environment variable or CI secret expands to ``""`` (e.g.
        ``OPENHANDS_AUTO_START: ${{ secrets.MISSING }}``), which pydantic would
        otherwise reject with a raw ``bool_parsing`` error at construction. An
        empty value therefore falls back to the fail-safe default (``False``): the
        sidecar is not auto-started and, critically, ``allow_unsandboxed_runtime``
        is never flipped permissive by a blank value. Non-empty strings and
        non-``str`` values pass through to pydantic's bool parsing.

        :param v: The raw flag value.
        :return: ``False`` for an empty/whitespace string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return False
        return v

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_csv_lists(cls, v: object) -> object:
        """Accept a comma-separated string for the CSV list field passed in code.

        The env-var path is handled by :class:`_CsvEnvSettingsSource`; this
        covers callers passing a raw string directly to the constructor. Lists
        pass through untouched.

        :param v: The raw ``allowed_tools`` value.
        :return: A split list when *v* is a string, else *v* unchanged.
        """
        return _split_csv(v)

    @field_validator("server_url")
    @classmethod
    def _validate_server_url(cls, v: Optional[str]) -> Optional[str]:
        """Require a well-formed ``http(s)://host[:port]`` URL, or treat as unset.

        An empty or whitespace-only value is treated as *unset* (``None``), not
        as a malformed URL - an unset env var or CI secret expands to ``""``
        (e.g. ``OPENHANDS_SERVER_URL: ${{ secrets.MISSING }}``), which must mean
        "OpenHands not configured" rather than crash construction at import time.

        This is the **inverse** of ``OpenClaudeSettings.grpc_url``: OpenHands is a
        REST/WS server, so an ``http``/``https`` scheme with a non-empty host is
        required. The offending value is never echoed - it may carry
        credentials/userinfo (C13).

        :param v: The raw ``server_url`` value.
        :return: The validated URL, or ``None`` when unset/blank.
        :raises OpenHandsConfigError: when *v* is a non-empty, malformed URL.
        """
        if v is None:
            return v
        if not v.strip():
            return None

        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise OpenHandsConfigError(
                field="server_url",
                reason="value must be an http(s)://host[:port] URL",
            )
        return v

    @field_validator("runtime_mode")
    @classmethod
    def _validate_runtime_mode(cls, v: str) -> str:
        """Reject any runtime name not in ``_KNOWN_RUNTIMES``.

        Sandbox *enforcement* (rejecting a non-Docker runtime without the
        explicit override) is a cross-field concern handled by
        :meth:`_enforce_sandbox_default`; this validator only checks the value is
        a recognised runtime name.

        :param v: The raw ``runtime_mode`` value.
        :return: The validated runtime name.
        :raises OpenHandsConfigError: when *v* is not a known runtime name.
        """
        if v not in _KNOWN_RUNTIMES:
            raise OpenHandsConfigError(
                field="runtime_mode",
                reason=f"unknown runtime name; expected one of {sorted(_KNOWN_RUNTIMES)}",
            )
        return v

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject unknown OpenHands tool names; warn on write-capable tools.

        :param v: The list of requested tool names.
        :return: The validated tool list.
        :raises OpenHandsConfigError: when any name is not in ``_KNOWN_TOOLS``.
        """
        unknown = [tool for tool in v if tool not in _KNOWN_TOOLS]
        if unknown:
            raise OpenHandsConfigError(
                field="allowed_tools",
                reason=f"unknown OpenHands tool name(s): {unknown}",
            )
        write_capable = sorted(_WRITE_CAPABLE_TOOLS.intersection(v))
        if write_capable:
            logger.warning(
                "OpenHands allowed_tools grants write-capable tool(s) {}; " "read-only forensic mode is compromised",
                write_capable,
            )
        return v

    @field_validator("connect_timeout_s")
    @classmethod
    def _validate_connect_timeout(cls, v: int) -> int:
        """Enforce ``connect_timeout_s > 0``.

        :param v: The raw connect-timeout value.
        :return: The validated connect timeout.
        :raises OpenHandsConfigError: when *v* is not a positive integer.
        """
        if v <= 0:
            raise OpenHandsConfigError(
                field="connect_timeout_s",
                reason="must be a positive integer",
            )
        return v

    @field_validator("request_timeout_s")
    @classmethod
    def _validate_request_timeout(cls, v: int, info: ValidationInfo) -> int:
        """Enforce ``request_timeout_s > connect_timeout_s`` and both positive.

        :param v: The raw request-timeout value.
        :param info: Validation context carrying prior field values.
        :return: The validated request timeout.
        :raises OpenHandsConfigError: when *v* is non-positive or not strictly
            greater than ``connect_timeout_s``.
        """
        if v <= 0:
            raise OpenHandsConfigError(
                field="request_timeout_s",
                reason="must be a positive integer",
            )
        connect_timeout_s = info.data.get("connect_timeout_s")
        if connect_timeout_s is not None and v <= connect_timeout_s:
            raise OpenHandsConfigError(
                field="request_timeout_s",
                reason=f"must be greater than connect_timeout_s ({connect_timeout_s})",
            )
        return v

    @model_validator(mode="after")
    def _enforce_sandbox_default(self) -> OpenHandsSettings:
        """Reject a non-sandboxed runtime unless explicitly overridden.

        Docker sandboxing is a design requirement of the OpenHands backend (C8):
        Aegis SWR treats every incident payload as hostile, so the runtime that
        executes navigation tools must be sandboxed by default. A non-sandboxed
        :attr:`runtime_mode` therefore raises :class:`OpenHandsConfigError`
        unless :attr:`allow_unsandboxed_runtime` is explicitly ``True``, in which
        case a loud warning is emitted instead. The reason/warning name only the
        field and the override env var - never any ``server_url`` or payload
        text (C13).

        :return: the validated settings instance.
        :raises OpenHandsConfigError: when :attr:`runtime_mode` is a non-sandboxed
            runtime and :attr:`allow_unsandboxed_runtime` is ``False``.
        """
        if self.runtime_mode in _SANDBOXED_RUNTIMES:
            return self

        if not self.allow_unsandboxed_runtime:
            raise OpenHandsConfigError(
                field="runtime_mode",
                reason=(
                    "selects a non-sandboxed runtime; the Docker sandbox is a "
                    "design requirement (C8). Set OPENHANDS_ALLOW_UNSANDBOXED=true "
                    "and record an ADR to opt out"
                ),
            )

        logger.warning(
            "OpenHands runtime_mode selects a NON-SANDBOXED runtime with "
            "OPENHANDS_ALLOW_UNSANDBOXED enabled; the Docker sandbox is DISABLED "
            "and hostile incident payloads run without container isolation. An ADR "
            "recording this decision is required per milestone policy (C8)."
        )
        return self
