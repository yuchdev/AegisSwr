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

:class:`ClaudeCodeConfigError` is re-exported from
``aegis_swr.claude_code.exceptions`` (its canonical home as of Task 05.0) so
existing imports of ``aegis_swr.claude_code.config.ClaudeCodeConfigError``
continue to resolve to the same object with no downstream import-path change.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

from loguru import logger
from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError as ClaudeCodeConfigError

_CSV_LIST_FIELDS: frozenset[str] = frozenset({"allowed_tools"})

#: Authentication-mode vocabulary (C7). Defined as a module-level alias (rather
#: than an inline ``Literal[...]`` annotation) so ``UP037`` does not strip the
#: quotes from its string members - the same idiom as ``PanelMode`` /
#: ``AgentCategory`` elsewhere in the codebase.
AuthMode = Literal["auto", "api_key", "subscription"]

#: Environment variables that outrank a Claude.ai subscription login in the
#: credential precedence chain Claude Code itself applies (C7 ranks 2-3): their
#: mere non-empty presence would silently displace an ``auth_mode="subscription"``
#: choice. Ordered high-to-low so the rejection message names the *first* one it
#: finds. Their **values** are never read - only their presence (C7/C13).
_OUTRANKING_ENV_VARS: tuple[str, ...] = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")

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

#: Field defaults, hoisted to module constants so the fail-safe value an
#: empty/whitespace env var (an unset CI secret expanding to ``""``) falls back to
#: is defined in exactly one place, shared by the field declaration and its
#: ``mode="before"`` empty-value coercer.
_DEFAULT_ALLOWED_TOOLS: tuple[str, ...] = ("Read", "Grep", "Glob")
_DEFAULT_MAX_TURNS: int = 8
_DEFAULT_REQUEST_TIMEOUT_S: int = 120
_DEFAULT_PERMISSION_MODE: str = "default"
_DEFAULT_AUTH_MODE: AuthMode = "auto"


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
        """Split comma-separated env values for list fields, else defer to the base.

        An empty/whitespace-only ``CLAUDE_CODE_ALLOWED_TOOLS`` (an unset CI secret
        expanding to ``""``) coerces to the read-only default set rather than an
        empty list, so it neither crashes construction nor trips the
        empty-allowlist rejection (which would fail OPEN by omitting
        ``--allowedTools`` - see :meth:`ClaudeCodeSettings._validate_allowed_tools`).
        """
        if field_name in _CSV_LIST_FIELDS and isinstance(value, str):
            if not value.strip():
                return list(_DEFAULT_ALLOWED_TOOLS)
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
    :ivar auth_mode: Which credential surface the one-shot ``claude`` subprocess
        must use (C7). ``"auto"`` (the **default**) defers entirely to the
        ``claude`` binary's own precedence chain and adds no Aegis-side
        validation - Task 03.0 behaviour is preserved bit-for-bit. ``"api_key"``
        uses the host ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN`` (``--bare``
        eligible). ``"subscription"`` uses a Claude.ai login (OAuth) and is
        rejected at construction if an API-key credential is present in the
        inherited environment (it would silently outrank the login) or if a
        ``--bare`` invocation is requested. The ``"auto"`` default is a **design
        constraint driven by the open licensing caveat** (C7): ``subscription``
        mode is opt-in only and must not be recommended as the default automation
        path until confirmed with Anthropic (see Task 13.0's setup guide).
    :ivar bare: When ``True`` the credential resolver may append ``--bare`` to the
        ``claude`` argv for reproducibility - permitted only in ``"api_key"`` mode
        (C7). ``--bare`` reads no OAuth/login credential, so combining it with **any
        non-**``api_key`` mode is rejected at construction (fail loud rather than
        silently drop the flag): ``auth_mode="subscription"`` via
        :meth:`_validate_subscription_mode` and the default ``auth_mode="auto"`` via
        :meth:`_validate_bare_requires_api_key`. Defaults to ``False``.
    """

    model_config = SettingsConfigDict(env_prefix="CLAUDE_CODE_", populate_by_name=True)

    binary_path: str = Field(default="claude", validation_alias="CLAUDE_CODE_BINARY")
    enabled: bool = False
    allowed_tools: list[str] = Field(default_factory=lambda: list(_DEFAULT_ALLOWED_TOOLS))
    max_turns: int = _DEFAULT_MAX_TURNS
    request_timeout_s: int = Field(default=_DEFAULT_REQUEST_TIMEOUT_S, validation_alias="CLAUDE_CODE_REQUEST_TIMEOUT")
    permission_mode: str = _DEFAULT_PERMISSION_MODE
    scratch_cwd: Optional[Path] = None
    auth_mode: AuthMode = _DEFAULT_AUTH_MODE
    bare: bool = False

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

    @field_validator("bare", mode="before")
    @classmethod
    def _coerce_bare(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``bare`` value as the default (``False``).

        An unset environment variable or CI secret expands to ``""`` (e.g.
        ``CLAUDE_CODE_BARE: ${{ secrets.MISSING }}``), which pydantic would
        otherwise reject with a raw ``bool_parsing`` error. An empty value must
        fall back to the fail-safe default (``--bare`` off) and must never resolve
        to ``True``. Non-empty strings and non-``str`` values pass through to
        pydantic's bool parsing.

        :param v: The raw ``bare`` value.
        :return: ``False`` for an empty/whitespace string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return False
        return v

    @field_validator("max_turns", mode="before")
    @classmethod
    def _coerce_max_turns(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``max_turns`` value as the default.

        An unset ``CLAUDE_CODE_MAX_TURNS`` expands to ``""``; without this coercer
        pydantic raises a raw ``int_parsing`` ``ValidationError`` that ``__init__``
        does not unwrap, crashing a partially-configured (e.g. CI) construction. A
        blank value falls back to the fail-safe default; a non-empty non-integer
        still fails loud through pydantic's int parsing.

        :param v: The raw ``max_turns`` value.
        :return: The default for a blank string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return _DEFAULT_MAX_TURNS
        return v

    @field_validator("request_timeout_s", mode="before")
    @classmethod
    def _coerce_request_timeout(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``request_timeout_s`` value as the default.

        An unset ``CLAUDE_CODE_REQUEST_TIMEOUT`` expands to ``""``; without this
        coercer pydantic raises a raw ``int_parsing`` ``ValidationError`` that
        ``__init__`` does not unwrap, crashing construction. A blank value falls
        back to the fail-safe default; a non-empty non-integer still fails loud.

        :param v: The raw ``request_timeout_s`` value.
        :return: The default for a blank string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return _DEFAULT_REQUEST_TIMEOUT_S
        return v

    @field_validator("permission_mode", mode="before")
    @classmethod
    def _coerce_permission_mode(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``permission_mode`` value as the default.

        An unset ``CLAUDE_CODE_PERMISSION_MODE`` expands to ``""``; without this
        coercer the ``permission_mode`` validator rejects the blank value as an
        "unknown mode", crashing a partially-configured construction. A blank value
        falls back to the fail-safe non-bypassing default ``"default"``; any
        non-empty value still flows through the bypass/unknown-mode rejection.

        :param v: The raw ``permission_mode`` value.
        :return: ``"default"`` for a blank string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return _DEFAULT_PERMISSION_MODE
        return v

    @field_validator("auth_mode", mode="before")
    @classmethod
    def _coerce_auth_mode(cls, v: object) -> object:
        """Treat an empty/whitespace-only ``auth_mode`` value as the default (``auto``).

        An unset ``CLAUDE_CODE_AUTH_MODE`` expands to ``""`` (e.g.
        ``CLAUDE_CODE_AUTH_MODE: ${{ secrets.MISSING }}``); without this coercer the
        ``Literal`` type raises a raw ``literal_error`` ``ValidationError`` that
        ``__init__`` does not unwrap, crashing a zero-/partial-config construction
        (re-review MEDIUM). A blank value falls back to the licensing-driven default
        ``"auto"`` - which fails **closed** (it never selects ``subscription`` and
        disables no guard). Non-empty strings pass through to the ``Literal`` check.

        :param v: The raw ``auth_mode`` value.
        :return: ``"auto"`` for a blank string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return _DEFAULT_AUTH_MODE
        return v

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_csv_lists(cls, v: object) -> object:
        """Accept a comma-separated string for ``allowed_tools`` passed in code.

        The env-var path is handled by :class:`_CsvEnvSettingsSource`; this covers
        callers passing a raw string directly to the constructor. An
        empty/whitespace-only string (the unset-CI-secret artifact) coerces to the
        read-only default set, mirroring :class:`_CsvEnvSettingsSource`, so a blank
        value falls back to the safe default rather than an empty allowlist. Lists
        (including an explicit empty ``[]``) pass through untouched - an explicit
        empty list is rejected by :meth:`_validate_allowed_tools` (fail closed).

        :param v: The raw ``allowed_tools`` value.
        :return: The default list for a blank string, a split list for a non-empty
            string, else ``v`` unchanged.
        """
        if isinstance(v, str) and not v.strip():
            return list(_DEFAULT_ALLOWED_TOOLS)
        return _split_csv(v)

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, v: list[str]) -> list[str]:
        """Reject an empty or unknown allowlist; warn on write-capable tools.

        An **explicit empty** ``allowed_tools`` is rejected (fail closed): an empty
        list makes :func:`aegis_swr.claude_code.process.build_argv` omit
        ``--allowedTools`` entirely, which grants the ``claude`` CLI *unrestricted*
        tool access - the inverse of the C6.3 read-only guard (fails OPEN). An
        empty allowlist is therefore a construction error, not a silently-permissive
        default. (An empty/whitespace *string* value - the unset-CI-secret artifact -
        is coerced to the read-only default upstream and never reaches this check.)

        :param v: The parsed list of tool names.
        :return: The validated list, unchanged.
        :raises ClaudeCodeConfigError: When the list is empty, or when any name is
            not a recognized Claude Code tool.
        """
        if not v:
            raise ClaudeCodeConfigError(
                field="allowed_tools",
                reason=(
                    "must grant at least one read-only tool; an empty allowlist "
                    "omits --allowedTools and grants the claude CLI unrestricted "
                    "tool access (fails open - the inverse of the read-only guard)"
                ),
            )
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

    @model_validator(mode="after")
    def _validate_subscription_mode(self) -> ClaudeCodeSettings:
        """Reject a ``subscription`` config that cannot honour the operator's choice (C7).

        Runs meaningfully only when ``auth_mode == "subscription"``; for ``"auto"``
        and ``"api_key"`` it inspects **no** environment and returns ``self``
        immediately (the behavioural-freeze guarantee for the default path). In
        subscription mode it enforces the two C7 construction-time invariants:

        * an outranking API-key credential (:data:`_OUTRANKING_ENV_VARS`) must not
          be present in the inherited environment - either would silently outrank
          the subscription login (C7 precedence ranks 2-3) and defeat the explicit
          choice; and
        * ``--bare`` must not be requested (``bare=True``) - bare mode never reads
          OAuth/login credentials at all (C7), so it is unusable for a login-based
          deployment.

        Presence is tested as *set and non-empty* (``os.environ`` read exactly
        once): an unset variable and an empty-string variable
        (``ANTHROPIC_API_KEY=""``, the classic unset-CI-secret artifact) are both
        treated as **absent** so a stray empty value triggers no spurious
        rejection. The exception message names **only** the offending env-var or
        field name - never a credential value (C7/C13).

        :return: ``self`` when the subscription configuration is internally
            consistent (or when ``auth_mode`` is not ``"subscription"``).
        :raises ClaudeCodeConfigError: on an outranking credential present in the
            environment, or a ``subscription`` + ``--bare`` combination.
        """
        if self.auth_mode != "subscription":
            return self

        if self.bare:
            raise ClaudeCodeConfigError(
                field="auth_mode",
                reason=(
                    "auth_mode='subscription' is incompatible with a --bare invocation; "
                    "bare mode never reads OAuth/login credentials (C7). "
                    "Unset bare or use auth_mode='api_key'."
                ),
            )

        present = next((name for name in _OUTRANKING_ENV_VARS if os.environ.get(name, "").strip()), None)
        if present is not None:
            raise ClaudeCodeConfigError(
                field="auth_mode",
                reason=(
                    f"auth_mode='subscription' but {present} is set in the environment; "
                    "it would silently outrank the subscription login (C7 precedence). "
                    "Unset it or use auth_mode='api_key'."
                ),
            )

        return self

    @model_validator(mode="after")
    def _validate_bare_requires_api_key(self) -> ClaudeCodeSettings:
        """Reject ``bare=True`` outside ``api_key`` mode - fail loud, never silent (C7).

        ``--bare`` is documented as permitted **only** in ``api_key`` mode: it reads
        no OAuth/login credential, so it is meaningless in ``subscription`` mode and
        a no-op in ``auto`` mode. Yet under the default ``auth_mode="auto"`` a
        ``bare=True`` request was previously accepted silently and then silently
        dropped by :func:`aegis_swr.claude_code.process.resolve_credential` (which
        appends ``--bare`` only in ``api_key`` mode) - the exact silent-ignore class
        C7 exists to eliminate. This validator makes every non-``api_key`` + ``bare``
        combination a loud construction error, consistent with how this codebase
        treats every other misconfiguration.

        The ``subscription`` + ``bare`` case is also rejected here, but redundantly:
        :meth:`_validate_subscription_mode` runs first and rejects it with a
        subscription-specific message, so this validator's raise is reached only for
        the ``auto`` (and any future non-``api_key``) mode.

        :return: ``self`` when ``bare`` is unset or ``auth_mode`` is ``"api_key"``.
        :raises ClaudeCodeConfigError: When ``bare=True`` and ``auth_mode`` is not
            ``"api_key"``.
        """
        if self.bare and self.auth_mode != "api_key":
            raise ClaudeCodeConfigError(
                field="bare",
                reason=(
                    f"bare=True is permitted only in auth_mode='api_key' (C7); got "
                    f"auth_mode='{self.auth_mode}'. --bare reads no OAuth/login "
                    "credential, so it is meaningless outside api_key mode. Set "
                    "auth_mode='api_key' or unset bare."
                ),
            )
        return self
