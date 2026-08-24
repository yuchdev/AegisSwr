"""Environment-sourced configuration for the Claude Code backend.

This module hosts :class:`ClaudeCodeSettings`, a Pydantic ``BaseSettings``
subclass whose fields are sourced entirely from environment variables (milestone
contract **C5**, **C6 item 4**). It mirrors ``OpenClaudeSettings``' proven shape:
a per-family ``env_prefix`` (``CLAUDE_CODE_``), an :class:`EnvSettingsSource`
subclass plus a ``mode="before"`` coercion validator for CSV parsing of
``list[str]`` fields, ``field_validator``s that raise the backend's own typed
config error, and a ``ValidationError``-unwrap in ``__init__``.

Because the Claude Code backend runs with **host OS permissions and no sandbox**,
the ``allowed_tools`` read-only default, the ``permission_mode`` bypass rejection,
and the mandatory disposable ``scratch_cwd`` are the *only* settings-time guards
standing in for the sandbox this backend lacks (C6 item 3).

:class:`ClaudeCodeConfigError` is **forward-declared** here (a same-named
placeholder). Task 05.0 supplies the canonical definition in
``aegis_swr/claude_code/exceptions.py`` and replaces this placeholder with a
re-export alias so ``aegis_swr.claude_code.config.ClaudeCodeConfigError`` keeps
resolving to the same object with no downstream import-path change.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from pydantic import Field, ValidationError, field_validator, model_validator
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

#: Claude Code permission modes accepted by ``--permission-mode``. The bypass
#: mode is intentionally absent from the *allowed* set and named separately so
#: the validator can reject it with a precise reason (C6 item 3).
_ALLOWED_PERMISSION_MODES: frozenset[str] = frozenset({"default", "acceptEdits", "plan"})

#: Values that would cause the tool to skip the permission prompt entirely. Any
#: of these - or the raw ``--dangerously-skip-permissions`` flag string - is
#: rejected at settings-validation time. Compared case-insensitively.
_BYPASS_PERMISSION_VALUES: frozenset[str] = frozenset(
    {
        "bypasspermissions",
        "bypass",
        "dangerously-skip-permissions",
        "--dangerously-skip-permissions",
    }
)


class ClaudeCodeConfigError(ValueError):
    """Raised when :class:`ClaudeCodeSettings` receives an invalid value.

    Forward declaration only. The canonical definition is moved to
    ``aegis_swr/claude_code/exceptions.py`` in Task 05.0; this placeholder is
    then replaced by a re-export alias so
    ``aegis_swr.claude_code.config.ClaudeCodeConfigError`` keeps resolving to the
    same object with **no** downstream import-path change (exactly as
    ``OpenClaudeConfigError`` was handled in Milestone 0004).

    :param field: Name of the offending field.
    :param reason: Human-readable explanation of the violation. Must never
        contain a secret, credential, or incident-payload value (C13).
    :ivar field: The offending field name.
    :ivar reason: The violation explanation.
    """

    def __init__(self, field: str, reason: str):
        """Record the offending *field* and payload-free *reason* on the error."""
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


def _find_repo_root() -> Path:
    """Locate the repository root by walking up from the current directory.

    Walks upward from ``Path.cwd()`` looking for a ``.git`` marker; falls back to
    ``Path.cwd()`` when no marker is found and treats that as the root to
    protect. Used by the ``scratch_cwd`` validator to reject a scratch directory
    that would let a one-shot ``claude`` process operate over the live source
    tree.

    :return: The resolved repository root path.
    """
    start = Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


class _CsvEnvSettingsSource(EnvSettingsSource):
    """Env source that accepts comma-separated values for CSV list fields.

    pydantic-settings v2 JSON-decodes ``list[str]`` fields sourced from the
    environment before field validators run, so a value such as
    ``CLAUDE_CODE_ALLOWED_TOOLS=Read,Grep,Glob`` would raise a ``SettingsError``.
    This source splits such values on commas instead, while leaving all other
    fields to the default decoding. Identical in shape to OpenClaude's
    ``_CsvEnvSettingsSource`` (C5).
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
    """Environment-sourced configuration for the Claude Code (``claude`` CLI) backend.

    Presence signal: ``enabled`` (``CLAUDE_CODE_ENABLED``). Being on ``PATH`` is
    deliberately **not** a signal (plan.md, Backend B) - a host-permission
    backend must never activate silently. With no env vars set the object is
    constructible and ``enabled`` is ``False`` (backend not configured); the
    mandatory-``scratch_cwd`` check only bites when ``enabled`` is ``True`` (C5).

    :ivar binary_path: Binary name or full path to the ``claude`` executable.
        Defaults to the bare command ``"claude"``, resolved via ``PATH``. A
        whitespace-only value (an unset CI secret expanding to ``""``) falls back
        to the default.
    :ivar enabled: Explicit opt-in switch and the backend's presence signal.
        ``False`` means the backend is not registered (C2/C6).
    :ivar allowed_tools: Claude Code tool names passed to ``--allowedTools``.
        Defaults to the read-only set ``["Read", "Grep", "Glob"]``; write-capable
        tools are OFF by default (C6 item 3).
    :ivar max_turns: Upper bound on the agent's turn count for a single
        ``delegate()`` (maps to the CLI's turn cap in Task 03.0). Must be ``>= 1``.
    :ivar request_timeout_s: Per-``delegate()`` subprocess deadline, in seconds.
        Must be a positive integer.
    :ivar permission_mode: Claude Code permission mode. One of ``"default"``,
        ``"acceptEdits"``, ``"plan"``; any bypass-permissions value is rejected
        unconditionally and case-insensitively (C6 item 3).
    :ivar scratch_cwd: Disposable working directory for the one-shot ``claude``
        process. Mandatory when ``enabled`` is ``True``; must be creatable,
        writable, and not the repository root or an ancestor of it.
    """

    model_config = SettingsConfigDict(env_prefix="CLAUDE_CODE_", populate_by_name=True)

    binary_path: str = Field(default="claude", validation_alias="CLAUDE_CODE_BINARY")
    enabled: bool = False
    allowed_tools: list[str] = ["Read", "Grep", "Glob"]
    max_turns: int = 8
    request_timeout_s: int = Field(default=120, validation_alias="CLAUDE_CODE_REQUEST_TIMEOUT")
    permission_mode: str = "default"
    scratch_cwd: Optional[Path] = None

    def __init__(self, **values: Any):
        """Construct the settings, surfacing :class:`ClaudeCodeConfigError` directly.

        Pydantic wraps any ``ValueError`` raised inside a field or model
        validator into a ``ValidationError``; this unwraps the first such
        :class:`ClaudeCodeConfigError` so callers see the domain error the
        validators actually raised (C5). Reused unchanged by Task 04.0's
        ``auth_mode`` validator.

        :param values: Field values forwarded to the ``BaseSettings``
            constructor.
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

    @field_validator("binary_path", mode="before")
    @classmethod
    def _coerce_binary_path(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``binary_path`` as unset (use the default).

        An unset environment variable or CI secret expands to ``""`` (e.g.
        ``CLAUDE_CODE_BINARY: ${{ secrets.MISSING }}``), which must mean "use the
        bare ``claude`` command" rather than crash settings construction or leave
        an empty binary name. Non-empty strings pass through untouched; non-``str``
        values are returned unchanged for the type layer to handle.

        :param v: The raw ``binary_path`` value.
        :return: ``"claude"`` for an empty/whitespace string, else ``v``.
        """
        if isinstance(v, str) and not v.strip():
            return "claude"
        return v

    @field_validator("enabled", mode="before")
    @classmethod
    def _coerce_enabled(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``enabled`` value as the default (``False``).

        An unset environment variable or CI secret expands to ``""`` (e.g.
        ``CLAUDE_CODE_ENABLED: ${{ secrets.MISSING }}``), which pydantic would
        otherwise reject with a raw ``bool_parsing`` error. Because ``enabled`` is
        the contract-C2 presence signal read by ``HarnessSettings`` via
        ``default_factory``, an empty value must fall back to the fail-safe default
        (backend not configured) so a zero-config ``HarnessSettings()`` always
        constructs. An empty value must never resolve to ``True``. Non-empty
        strings and non-``str`` values pass through to pydantic's bool parsing.

        :param v: The raw ``enabled`` value.
        :return: ``False`` for an empty/whitespace string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return False
        return v

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_csv_lists(cls, v: object) -> object:
        """Accept a comma-separated string for ``allowed_tools`` passed in code.

        The env-var path is handled by :class:`_CsvEnvSettingsSource`; this covers
        callers passing a raw string directly to the constructor. Lists pass
        through untouched.

        :param v: The raw ``allowed_tools`` value.
        :return: A split list for a ``str`` input, else ``v`` unchanged.
        """
        return _split_csv(v)

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject unknown Claude Code tool names; warn on write-capable tools.

        :param v: The parsed list of tool names.
        :return: The validated list, unchanged.
        :raises ClaudeCodeConfigError: When any name is not a recognized Claude
            Code tool.
        """
        unknown = [tool for tool in v if tool not in _KNOWN_TOOLS]
        if unknown:
            raise ClaudeCodeConfigError(
                field="allowed_tools",
                reason=f"unknown Claude Code tool name(s): {unknown}",
            )
        write_capable = sorted(_WRITE_CAPABLE_TOOLS.intersection(v))
        if write_capable:
            logger.warning(
                "ClaudeCode allowed_tools grants write-capable tool(s) {}; " "read-only forensic mode is compromised",
                write_capable,
            )
        return v

    @field_validator("max_turns")
    @classmethod
    def _validate_max_turns(cls, v: int) -> int:
        """Enforce ``max_turns >= 1``.

        :param v: The requested maximum turn count.
        :return: The validated value, unchanged.
        :raises ClaudeCodeConfigError: When ``v`` is less than 1.
        """
        if v < 1:
            raise ClaudeCodeConfigError(
                field="max_turns",
                reason="must be a positive integer (>= 1)",
            )
        return v

    @field_validator("request_timeout_s")
    @classmethod
    def _validate_request_timeout(cls, v: int) -> int:
        """Enforce ``request_timeout_s > 0``.

        :param v: The requested per-``delegate()`` deadline in seconds.
        :return: The validated value, unchanged.
        :raises ClaudeCodeConfigError: When ``v`` is not positive.
        """
        if v <= 0:
            raise ClaudeCodeConfigError(
                field="request_timeout_s",
                reason="must be a positive integer",
            )
        return v

    @field_validator("permission_mode")
    @classmethod
    def _validate_permission_mode(cls, v: str) -> str:
        """Accept only a non-bypassing mode; reject any bypass-permissions value.

        Rejects ``bypassPermissions`` and anything that would produce
        ``--dangerously-skip-permissions`` in the constructed argv (Task 03.0),
        as well as any value that is not a known non-bypassing mode. The
        comparison is case-insensitive so ``BYPASSPERMISSIONS`` cannot slip
        through. The rejection is **unconditional** - it does not depend on
        ``enabled`` - so an operator cannot stage a bypass value "for later".

        :param v: The requested permission mode.
        :return: The validated mode, unchanged.
        :raises ClaudeCodeConfigError: When ``v`` is a bypass value or an
            unrecognized mode.
        """
        normalized = v.strip().lower()
        if normalized in _BYPASS_PERMISSION_VALUES:
            raise ClaudeCodeConfigError(
                field="permission_mode",
                reason=(
                    "bypass-permissions values are forbidden; must be one of " f"{sorted(_ALLOWED_PERMISSION_MODES)}"
                ),
            )
        if v not in _ALLOWED_PERMISSION_MODES:
            raise ClaudeCodeConfigError(
                field="permission_mode",
                reason=f"unknown mode '{v}'; must be one of {sorted(_ALLOWED_PERMISSION_MODES)}",
            )
        return v

    @field_validator("scratch_cwd", mode="before")
    @classmethod
    def _coerce_scratch_cwd(cls, v: object) -> object:
        """Treat an empty/whitespace-only env value as unset (``None``).

        An unset env var or a whitespace-only expansion
        (``CLAUDE_CODE_SCRATCH_CWD: ${{ secrets.MISSING }}`` -> ``""``) is coerced
        to ``None`` so an unconfigured backend never crashes construction.

        :param v: The raw ``scratch_cwd`` value.
        :return: ``None`` for an empty/whitespace string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def _validate_scratch_cwd_when_enabled(self) -> ClaudeCodeSettings:
        """Enforce the mandatory disposable scratch cwd only when enabled.

        When ``enabled`` is ``False`` the object stays constructible with
        ``scratch_cwd=None`` (presence-signal-as-falsy default, C5). When
        ``enabled`` is ``True`` the scratch cwd must be set, must be creatable and
        writable, and must not be the repository root or an ancestor of it.
        Performs **no** filesystem side effects: it may ``stat``/probe for
        writability but never creates, moves, or deletes anything (directory
        lifecycle is Task 03.0's per-``delegate()`` RAII concern).

        :return: ``self`` when valid.
        :raises ClaudeCodeConfigError: When the enabled backend has an unset,
            unusable, or repo-root ``scratch_cwd``.
        """
        if not self.enabled:
            return self

        if self.scratch_cwd is None:
            raise ClaudeCodeConfigError(
                field="scratch_cwd",
                reason=(
                    "a disposable scratch working directory is mandatory when the " "Claude Code backend is enabled"
                ),
            )

        resolved = self.scratch_cwd.expanduser().resolve()

        if resolved.exists():
            if not resolved.is_dir():
                raise ClaudeCodeConfigError(
                    field="scratch_cwd",
                    reason="path exists but is not a directory",
                )
            if not os.access(resolved, os.W_OK):
                raise ClaudeCodeConfigError(
                    field="scratch_cwd",
                    reason="directory is not writable",
                )
        else:
            ancestor = next(
                (parent for parent in resolved.parents if parent.exists()),
                None,
            )
            if ancestor is None or not ancestor.is_dir() or not os.access(ancestor, os.W_OK):
                raise ClaudeCodeConfigError(
                    field="scratch_cwd",
                    reason="no writable existing ancestor to create the directory under",
                )

        repo_root = _find_repo_root()
        if repo_root == resolved or repo_root.is_relative_to(resolved):
            raise ClaudeCodeConfigError(
                field="scratch_cwd",
                reason="must not be the repository root or an ancestor of it",
            )

        return self
