"""Configuration settings and runtime configuration sources.

This module defines the structured settings used across the Aegis SWR
prototype. Settings are modelled with Pydantic / pydantic-settings as
``BaseSettings`` subclasses so they may be loaded from (in priority order):

- explicit constructor kwargs
- environment variables prefixed with ``AEGIS__`` (nested using ``__``)
- JSON files under the config directory (see ``CONFIG_DIR``)

The file also provides a small custom settings source that reads the
``config.json`` runtime-configuration file under the config directory. A
missing or malformed JSON file is tolerated and simply ignored, leaving the
model defaults intact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional, Self

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from aegis_swr.openclaude.config import OpenClaudeSettings

"""Canonical config directory - the single home of ``config.json`` (this
module's runtime settings). It is the *same* path the CLI reads and writes, and
the single hardcoded location: every other path default
(reports/objects/db/logs/evidence) derives from it, and the effective values
are supplied by ``config.json``.
"""
CONFIG_DIR = Path("~/.aegis-swr").expanduser()

"""Backwards-compatible alias; ``CONFIG_DIR`` is the preferred name."""
DATA_DIR = CONFIG_DIR

"""Runtime settings file (``core`` / ``backends`` / ``sandbox`` / ``api``). It is
the *same* file the CLI uses for the flat ``aegis analyze`` keys; those keys
are not fields of :class:`Settings` and are dropped via ``extra="ignore"``.
"""
CONFIG_JSON = CONFIG_DIR / "config.json"

"""The canonical config-file path, re-exported for the CLI layer so both halves
of the app resolve the *same* file.
"""
DEFAULT_CONFIG_PATH = CONFIG_JSON

"""Keywords for sensitive fields in the runtime settings file."""
_SECRET_KEYS = {"api_key", "password", "secret", "token", "database_url"}


class CoreSettings(BaseSettings):
    """General pipeline tuning and safety thresholds.

    Core application behavior flags and numeric thresholds that control how
    the multi-agent reasoning and analysis pipeline runs. Values here are
    intentionally conservative defaults suitable for local development and can
    be overridden via env vars or the JSON config file.

    Fields
    ------
    max_debate_rounds: int
        Maximum number of iterative debate/consensus rounds performed by the
        agent ensemble during analysis.
    consensus_threshold: float
        Confidence threshold (0..1) required for a consensus decision to be
        accepted without Human-in-the-Loop (HITL) review.
    hitl_confidence_threshold: float
        If a result's confidence is below this value, the system will route the
        case for human review.
    log_window_seconds: int
        Time window (seconds) used when extracting recent log lines for
        contextual evidence.
    user_assumption_token_limit: int
        Soft limit on tokens used to capture user-provided assumptions.
    stack_frames_limit: int
        Maximum number of stack frames to include when serializing a stack
        trace for AI analysis.
    """

    model_config = SettingsConfigDict(extra="ignore")

    max_debate_rounds: int = 4
    consensus_threshold: float = 0.85
    hitl_confidence_threshold: float = 0.50
    log_window_seconds: int = 30
    user_assumption_token_limit: int = 500
    stack_frames_limit: int = 20


_ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
_OPENAI_DEFAULT_MODEL = "gpt-5.4"
_OPENAI_MODEL_PREFIXES = ("gpt-",)

"""Default Bedrock inference profile - Claude Sonnet 4.6 via the APAC
cross-region profile. Direct model IDs (without an ``au.``/``apac.``/``global.``
prefix) require provisioned throughput, so an on-demand profile is the safe
default. See :class:`BedrockSettings`.
"""
_BEDROCK_DEFAULT_MODEL = "au.anthropic.claude-sonnet-4-6"


#: Legacy flat ``backends.ai`` keys that were promoted into the per-provider
#: sub-configs. Detected on load so a stale config produces a loud warning
#: instead of silently losing its tuning (see :meth:`AISettings._warn_legacy`).
_LEGACY_AI_KEYS = ("model", "temperature", "max_tokens")


class ModelOverride(BaseModel):
    """Per-model override of provider-level AI settings.

    Every field is optional; ``None`` means "inherit the provider-level value".
    A single override type serves all providers - when merged onto a concrete
    provider config, keys that are not fields of that provider are ignored, so
    e.g. ``reasoning_effort`` on a Bedrock override is harmlessly dropped. See
    :meth:`ProviderSettingsBase.for_model`.

    :ivar max_tokens: Override the maximum output-token budget.
    :ivar temperature: Override the sampling temperature.
    :ivar thinking_budget_tokens: Override the extended-thinking budget
        (Anthropic / Bedrock).
    :ivar reasoning_effort: Override the reasoning effort (OpenAI).
    :ivar max_completion_tokens: Override the completion-token budget (OpenAI).
    :ivar prompt_caching: Override ephemeral prompt caching (Anthropic).
    :ivar timeout_seconds: Override the per-request timeout (Anthropic / OpenAI).
    :ivar max_retries: Override the SDK retry count (Anthropic / OpenAI).
    :ivar connect_timeout_seconds: Override the connect timeout (Bedrock).
    :ivar read_timeout_seconds: Override the read timeout (Bedrock).
    :ivar max_attempts: Override the botocore retry attempts (Bedrock).
    """

    model_config = ConfigDict(extra="ignore")

    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    thinking_budget_tokens: Optional[int] = None
    reasoning_effort: Optional[str] = None
    max_completion_tokens: Optional[int] = None
    prompt_caching: Optional[bool] = None
    timeout_seconds: Optional[float] = None
    max_retries: Optional[int] = None
    connect_timeout_seconds: Optional[int] = None
    read_timeout_seconds: Optional[int] = None
    max_attempts: Optional[int] = None


class ProviderSettingsBase(BaseModel):
    """Common AI knobs shared by every provider sub-config.

    Concrete providers (:class:`AnthropicSettings`, :class:`OpenAISettings`,
    :class:`BedrockSettings`) extend this with their own capabilities. The
    factory passes the resolved, per-model-merged sub-config (see
    :meth:`for_model`) to the matching backend, so each backend sees a precise
    type rather than the whole :class:`AISettings`.

    :ivar model: Provider model name (Bedrock overrides identity via
        ``model_id``; see :attr:`resolved_model`).
    :ivar max_tokens: Maximum output-token budget for a single response.
    :ivar temperature: Sampling temperature.
    :ivar models: Optional per-model overrides keyed by :attr:`resolved_model`,
        merged over the provider-level defaults by :meth:`for_model`.
    """

    model_config = ConfigDict(extra="ignore")

    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.2
    models: dict[str, ModelOverride] = Field(default_factory=dict)

    @property
    def resolved_model(self) -> str:
        """Return the effective model identity (overridden by Bedrock)."""
        return self.model

    def for_model(self) -> Self:
        """Return this config merged with the override for the active model.

        Looks up :attr:`resolved_model` in :attr:`models`; if an override
        exists, returns a copy with the override's non-``None`` fields applied
        over the provider-level defaults (override wins). Fields that do not
        belong to this provider are ignored. Returns ``self`` unchanged when no
        override matches.
        """
        override = self.models.get(self.resolved_model)
        if override is None:
            return self
        patch = {
            key: value
            for key, value in override.model_dump(exclude_none=True).items()
            if key in type(self).model_fields and key not in ("model", "models")
        }
        return self.model_copy(update=patch)


class AnthropicSettings(ProviderSettingsBase):
    """Anthropic (Claude) provider configuration.

    :ivar thinking_budget_tokens: Extended-thinking budget for free-form
        generation. ``0`` (or any value below the 1024 model minimum) disables
        thinking. Never applied to forced structured output.
    :ivar prompt_caching: When ``True`` (default), the stable system prompt is
        sent with an ephemeral ``cache_control`` block so it is billed at the
        cached rate.
    :ivar timeout_seconds: Per-request timeout passed to the Anthropic SDK.
    :ivar max_retries: SDK retry count (exponential backoff on timeouts / 429 /
        5xx).
    """

    model: str = _ANTHROPIC_DEFAULT_MODEL
    thinking_budget_tokens: int = 0
    prompt_caching: bool = True
    timeout_seconds: float = 600.0
    max_retries: int = 2

    @property
    def resolved_model(self) -> str:
        """Return ``model`` when it looks like a Claude name, else the default."""
        if self.model.startswith("claude"):
            return self.model
        return _ANTHROPIC_DEFAULT_MODEL


class OpenAISettings(ProviderSettingsBase):
    """OpenAI (GPT) provider configuration.

    :ivar reasoning_effort: Reasoning effort (``"low"`` / ``"medium"`` /
        ``"high"``) for reasoning models; ``None`` leaves the SDK default. Sent
        only for reasoning-capable models (``gpt-5`` family).
    :ivar max_completion_tokens: Completion-token budget used for reasoning
        models (which reject ``max_tokens``); shared with internal reasoning
        tokens, so it is generous by default.
    :ivar timeout_seconds: Per-request timeout passed to the OpenAI SDK.
    :ivar max_retries: SDK retry count (exponential backoff on timeouts / 429 /
        5xx).
    """

    model: str = _OPENAI_DEFAULT_MODEL
    reasoning_effort: Optional[str] = None
    max_completion_tokens: int = 16000
    timeout_seconds: float = 300.0
    max_retries: int = 4

    @property
    def resolved_model(self) -> str:
        """Return ``model`` when it looks like a GPT name, else the default."""
        if self.model.startswith(_OPENAI_MODEL_PREFIXES):
            return self.model
        return _OPENAI_DEFAULT_MODEL


class BedrockSettings(ProviderSettingsBase):
    """Amazon Bedrock provider configuration.

    The backend authenticates with a bearer token (``AWS_BEARER_TOKEN_BEDROCK``)
    when one is present, otherwise it falls back to the standard boto3 SigV4
    credential chain (env / shared config / instance role). Credentials are read
    from the environment only - never stored in or logged from this model.

    Bedrock has *two* token budgets: :attr:`max_tokens` (inherited) is the
    absolute maximum output, while :attr:`thinking_budget_tokens` caps the
    reasoning portion within it.

    :ivar region: AWS region hosting the model / inference profile. Overridable
        out of band via ``AWS_DEFAULT_REGION``; this field takes precedence when
        set.
    :ivar model_id: Model ID or cross-region inference profile (e.g.
        ``au.anthropic.claude-sonnet-4-6``). Surfaced as :attr:`resolved_model`;
        the inherited ``model`` field is unused for Bedrock.
    :ivar thinking_budget_tokens: Extended-thinking (reasoning) budget. ``0`` (or
        any value below the 1024 model minimum) disables thinking. Applied only
        to free-form generation - never to forced structured (tool) output,
        which Claude does not permit alongside thinking.
    :ivar connect_timeout_seconds: TCP connect timeout for the bedrock-runtime
        client.
    :ivar read_timeout_seconds: Socket read timeout; reasoning models can be
        slow, so this is generous.
    :ivar max_attempts: botocore retry attempts (standard mode) for throttling /
        5xx.
    :ivar auth_mode: ``"auto"`` uses a bearer token when present and otherwise
        SigV4; ``"bearer"`` forces bearer-token auth; ``"sigv4"`` forces the
        credential chain even when a bearer token is set.
    """

    region: str = "ap-southeast-2"
    model_id: str = _BEDROCK_DEFAULT_MODEL
    thinking_budget_tokens: int = 0
    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 300
    max_attempts: int = 3
    auth_mode: str = "auto"

    @field_validator("auth_mode")
    @classmethod
    def validate_auth_mode(cls, v: str) -> str:
        """Restrict ``auth_mode`` to the supported strategies."""
        allowed = {"auto", "bearer", "sigv4"}
        if v not in allowed:
            raise ValueError(f"auth_mode must be one of {allowed}")
        return v

    @property
    def resolved_model(self) -> str:
        """Return the configured inference-profile ID verbatim."""
        return self.model_id


class AISettings(BaseSettings):
    """AI backend configuration.

    Selects the active ``provider`` and carries one typed sub-config per
    provider (:attr:`anthropic`, :attr:`openai`, :attr:`bedrock`). All three
    blocks coexist, so switching provider is a one-field change that preserves
    every provider's tuning. Each sub-config exposes only the knobs that
    provider actually supports plus an optional per-model override map.
    """

    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "anthropic"
    stream: bool = True

    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    bedrock: BedrockSettings = Field(default_factory=BedrockSettings)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Restrict ``provider`` to a backend that has a sub-config + factory."""
        allowed = {"anthropic", "openai", "bedrock"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}")
        return v

    @model_validator(mode="before")
    @classmethod
    def _warn_legacy(cls, data: Any) -> Any:
        """Warn (once) when a stale flat ``backends.ai`` layout is detected.

        The flat ``model`` / ``temperature`` / ``max_tokens`` keys moved into the
        per-provider sub-configs. They are no longer read (``extra="ignore"``
        drops them); emitting a warning here prevents silent loss of tuning. No
        migration is performed - only key names are logged, never values.
        """
        if isinstance(data, dict):
            stale = [key for key in _LEGACY_AI_KEYS if key in data]
            if stale:
                logger.warning(
                    "Ignoring legacy flat backends.ai keys {}; move them under "
                    "backends.ai.<provider> (e.g. backends.ai.anthropic.max_tokens). "
                    "See docs/config/config.md.",
                    stale,
                )
        return data

    @property
    def active(self) -> ProviderSettingsBase:
        """Return the selected provider's sub-config, merged for its model."""
        sub: ProviderSettingsBase = getattr(self, self.provider)
        return sub.for_model()

    @property
    def resolved_model(self) -> str:
        """Return the effective model identity for the active provider."""
        return self.active.resolved_model


class DebugSettings(BaseSettings):
    """Settings for debug-engine selection and timeouts.

    The debug backends are responsible for extracting crash context from
    .dmp files. These settings choose which engine to prefer and tune timeouts
    and frame limits when walking stacks.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # "auto" | "cdb" | "windbg_js"
    engine: str = "auto"
    timeout_seconds: int = 300
    callback_timeout_seconds: int = 60
    max_faulting_frames: int = 20
    max_other_thread_frames: int = 3
    symbol_cache: Optional[str] = None
    symbol_server_url: Optional[str] = None

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        allowed = {"auto", "cdb", "windbg_js"}
        if v not in allowed:
            raise ValueError(f"engine must be one of {allowed}")
        return v


class StorageSettings(BaseSettings):
    """Storage backend configuration.

    Selects which storage provider is used for reports and binary objects and
    supplies provider-specific defaults for file paths and connection URLs.
    Supported ``provider`` values include: ``filesystem``, ``sqlite``, ``s3``,
    and ``postgres``.
    """

    model_config = SettingsConfigDict(extra="ignore")

    # filesystem | sqlite | s3 | postgres
    provider: str = "filesystem"

    # filesystem: report JSON files
    reports_dir: str = str(CONFIG_DIR / "reports")

    # filesystem: raw binary artifacts
    objects_dir: str = str(CONFIG_DIR / "objects")

    # sqlite: database file
    db_path: str = str(CONFIG_DIR / "db" / "reports.db")

    database_url: str = "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"
    object_store_url: str = "s3://aegis-raw-inputs"
    object_store_region: str = "us-east-1"
    s3_endpoint_url: Optional[str] = None  # MinIO / custom S3-compatible endpoint
    vector_store_url: str = "http://localhost:6333"
    vector_collection: str = "incident_history"

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"filesystem", "sqlite", "s3", "postgres"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}")
        return v


class LogBackendSettings(BaseSettings):
    """Logging backend configuration.

    Provides a small surface for selecting how historical logs are read. The
    default provider is ``file`` which reads logs from local files; a
    lightweight Fluent-forwarder option is also present for test harnesses.
    """

    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "file"  # file | fluent  (elk deferred)
    file_root: Optional[str] = None  # base dir for service→file resolution (file)
    default_severity_levels: list[str] = Field(default_factory=lambda: ["FATAL", "CRITICAL", "ERROR", "WARNING"])
    elk_url: Optional[str] = None  # elk (deferred)
    fluent_host: Optional[str] = None  # fluent stub
    fluent_port: Optional[int] = None  # fluent stub
    fluent_tag_prefix: Optional[str] = None  # fluent stub

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"file", "fluent", "elk"}
        if v not in allowed:
            raise ValueError(f"log provider must be one of {allowed}")
        return v


class CodeBackendSettings(BaseSettings):
    """Configuration for the optional source-code backend.

    When enabled, a CodeBackend can query a repository (git or filesystem)
    to provide recent commits and file contents that help the AI reason about
    code-level causes. Defaults disable this behavior so the core pipeline
    can run without a source tree.
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False  # false → no CodeBackend; Stage 8 skipped
    provider: str = "git"  # git | filesystem
    repo_path: Optional[str] = None  # working tree / source root
    window_hours: int = 2  # default look-back for get_commits_before
    commit_limit: int = 10  # default max commits returned
    git_timeout_seconds: int = 30  # git subprocess timeout (git provider)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"git", "filesystem"}
        if v not in allowed:
            raise ValueError(f"code provider must be one of {allowed}")
        return v


class BackendsSettings(BaseSettings):
    """Container for all backend-specific settings.

    This groups the various backend configuration sections under a single
    namespace; each attribute is itself a Pydantic settings model with its
    own defaults and validation.
    """

    model_config = SettingsConfigDict(extra="ignore")

    ai: AISettings = Field(default_factory=AISettings)
    debug: DebugSettings = Field(default_factory=DebugSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    log: LogBackendSettings = Field(default_factory=LogBackendSettings)
    code: CodeBackendSettings = Field(default_factory=CodeBackendSettings)


class SandboxSettings(BaseSettings):
    """Sandbox execution policy for running untrusted analysis helpers.

    When the analysis pipeline needs to execute helper code (e.g., any code
    instrumented during debugging), the sandbox settings control whether a
    restricted runtime is used and its resource limits.
    """

    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    runtime: str = "docker"
    memory_mb: int = 256
    cpu_limit: float = 0.5
    timeout_seconds: int = 60


class APISettings(BaseSettings):
    """HTTP API server configuration.

    Controls host/port and simple auth/rate-limiting options for the built-in
    HTTP API used by the GUI/CLI to query analysis results.
    """

    model_config = SettingsConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    api_key_header: str = "X-Aegis-API-Key"
    rate_limit_per_minute: int = 10


#: The two runtime panel-selection modes. Declared as a module-level alias
#: (rather than an inline ``Literal[...]`` annotation) so ``UP037`` does not strip
#: the quotes off the string members under ``from __future__ import annotations``.
PanelMode = Literal["auto", "explicit"]


class PanelRuntimeSettings(BaseSettings):
    """Per-invocation runtime panel request (runtime, not ops policy).

    This is the *user's* per-run choice of panel. It lives in ``config.json``
    (under the top-level ``panel`` key), alongside ``core`` / ``backends`` /
    ``sandbox`` / ``api``, and captures "what the user is asking for on this
    run".

    When :attr:`mode` is ``"explicit"`` and :attr:`explicit` is non-empty, those
    specs are passed straight to the orchestrator as its explicit panel; when
    ``"auto"`` (or ``explicit`` is empty) the orchestrator auto-selects the panel.

    :ivar mode: ``"auto"`` (auto-select) or ``"explicit"`` (use :attr:`explicit`).
    :ivar explicit: The per-run agent specs, deserialized into validated
        :class:`~aegis_swr.agents.base.AgentSpec` instances. Stored under an
        ``Any`` element annotation so the concrete ``AgentSpec`` type (which lives
        in ``agents.base``, a module that itself imports :class:`Settings`) need
        not be imported at module-load time; the ``mode="before"`` validator
        performs the lazy import and coercion, and the default empty list never
        triggers it.
    """

    model_config = SettingsConfigDict(extra="ignore")

    mode: PanelMode = "auto"
    explicit: list[Any] = Field(default_factory=list)

    @field_validator("explicit", mode="before")
    @classmethod
    def _coerce_specs(cls, value: Any) -> list[Any]:
        """Coerce raw ``explicit`` entries into validated ``AgentSpec`` objects.

        ``agents.base`` imports :class:`Settings`, so importing ``AgentSpec`` at
        the top of this module would form a circular import. The import is
        therefore deferred to this validator, which only runs when non-default
        ``explicit`` data is supplied (config.json / env / kwargs) - by which
        point both modules are fully loaded.

        :param value: The raw ``explicit`` value (list of dicts or specs).
        :return: A list of validated ``AgentSpec`` instances.
        """
        from aegis_swr.agents.base import AgentSpec

        specs: list[Any] = []
        for item in value or []:
            specs.append(item if isinstance(item, AgentSpec) else AgentSpec.model_validate(item))
        return specs


def _read_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object from the path.

    The function tolerates missing files and malformed JSON. In either case an
    empty dictionary is returned so that callers can merge optional JSON files
    without rising on startup.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


class AegisJsonSettingsSource(PydanticBaseSettingsSource):
    """Settings source backed by ``config.json`` under :data:`DATA_DIR`.

    ``config.json`` supplies the top-level runtime sections
    (``core`` / ``backends`` / ``sandbox`` / ``api`` / ``panel``). A bad or
    missing file never aborts startup - it simply contributes nothing, leaving
    the model defaults in force.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data = dict(_read_json_object(CONFIG_JSON))

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """Return the value for *field_name* from the merged JSON data.

        This method implements the small adapter interface expected by
        pydantic-settings so the JSON data participates in settings
        resolution. The returned triple is ``(value, source_name, should_call)``
        - here we return ``False`` for ``should_call`` because the value is
        already resolved.
        """
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return self._data


class Settings(BaseSettings):
    """Top-level application settings.

    This is the primary settings class consumers should instantiate. It
    aggregates the core, backends, sandbox, api, runtime-panel and openclaude
    sections and wires in the custom JSON settings source so that
    ``config.json`` is read
    automatically. The runtime ``panel`` request (the user's per-run choice) is
    loaded from ``config.json``.

    Consensus weight is *not* configured here: it is an intrinsic property of
    each agent (see :attr:`aegis_swr.agents.base.BaseAgent.default_weight`), so
    there is no agent-weight settings section and no external agent-policy file.
    """

    model_config = SettingsConfigDict(
        env_prefix="AEGIS__",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize the settings source precedence.

        Return an ordered tuple of settings sources. Sources earlier in the
        tuple take precedence over later ones. The ordering implemented here is:

        1. Explicit ``init`` kwargs passed to the Settings constructor
        2. Environment variables prefixed ``AEGIS__``
        3. The ``config.json`` file under ``CONFIG_DIR`` (via
           :class:`AegisJsonSettingsSource`)
        """
        # Precedence (high → low): explicit init kwargs > AEGIS__* env > JSON.
        return init_settings, env_settings, AegisJsonSettingsSource(settings_cls)

    core: CoreSettings = Field(default_factory=CoreSettings)
    backends: BackendsSettings = Field(default_factory=BackendsSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    api: APISettings = Field(default_factory=APISettings)
    panel: PanelRuntimeSettings = Field(default_factory=PanelRuntimeSettings)
    openclaude: OpenClaudeSettings = Field(default_factory=OpenClaudeSettings)

    def redacted_dump(self) -> dict[str, Any]:
        """Return the settings dict with secret values replaced by '***'"""
        import json

        raw: dict[str, Any] = json.loads(self.model_dump_json())
        _redact_secrets(raw)
        return raw


def _redact_secrets(obj: Any) -> None:
    """Recursively redact known secret keys in a mapping or sequence.

    Mutates the provided structure in-place. Any dict key that contains one of
    the substrings in ``_SECRET_KEYS`` (case-insensitive) will have its value
    replaced with the literal string ``"***"``. Lists are traversed
     recursively, so secrets nested inside sequences will also be redacted.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(s in k.lower() for s in _SECRET_KEYS):
                obj[k] = "***"
            else:
                _redact_secrets(v)
    elif isinstance(obj, list):
        for item in obj:
            _redact_secrets(item)
