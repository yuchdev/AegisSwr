from __future__ import annotations

"""Configuration settings and runtime configuration sources.

This module defines the structured settings used across the Aegis SWR
prototype. Settings are modelled with Pydantic / pydantic-settings as
``BaseSettings`` subclasses so they may be loaded from (in priority order):

- explicit constructor kwargs
- environment variables prefixed with ``AEGIS__`` (nested using ``__``)
- JSON files under the config directory (see ``CONFIG_DIR``)

The file also provides a small custom settings source that merges two JSON
files: ``config.json`` (runtime configuration sections) and ``agents.json``
(agent-weight matrix). Missing or malformed JSON files are tolerated and
simply ignored, leaving the model defaults intact.
"""

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

"""Canonical config directory - the single home of both ``config.json`` (this
module's runtime settings) and ``agents.json`` (the weight matrix). It is the
*same* path the CLI reads and writes, and the single hardcoded location: every
other path default (reports/objects/db/logs/evidence) derives from it, and the
effective values are supplied by ``config.json``.
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

"""Per-fault-class agent weight matrix, mounted under the ``agent_weights`` key."""
AGENTS_JSON = CONFIG_DIR / "agents.json"

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


class BedrockSettings(BaseSettings):
    """Amazon Bedrock backend configuration.

    Provider-specific knobs for :class:`~aegis_swr.backends.ai.aws_bedrock_provider.AwsBedrockBackend`.
    The backend authenticates with a bearer token (``AWS_BEARER_TOKEN_BEDROCK``)
    when one is present, otherwise it falls back to the standard boto3 SigV4
    credential chain (env / shared config / instance role). Credentials are read
    from the environment only - never stored in or logged from this model.

    Fields
    ------
    region: str
        AWS region hosting the model / inference profile. Overridable out of
        band via ``AWS_DEFAULT_REGION``; this field takes precedence when set.
    model_id: str
        Model ID or cross-region inference profile (e.g.
        ``au.anthropic.claude-sonnet-4-6``). This is the value surfaced as
        :attr:`AISettings.resolved_model` when the provider is ``bedrock``.
    thinking_budget_tokens: int
        Extended-thinking budget. ``0`` disables thinking; values below the
        model minimum (1024) are treated as disabled. Thinking is only applied
        to free-form generation - never to forced structured (tool) output,
        which Claude does not permit alongside thinking.
    connect_timeout_seconds: int
        TCP connect timeout for the bedrock-runtime client.
    read_timeout_seconds: int
        Socket read timeout; reasoning models can be slow, so this is generous.
    max_attempts: int
        botocore retry attempts (standard mode) for throttling / 5xx.
    """

    model_config = SettingsConfigDict(extra="ignore")

    region: str = "ap-southeast-2"
    model_id: str = _BEDROCK_DEFAULT_MODEL
    thinking_budget_tokens: int = 0
    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 300
    max_attempts: int = 3


class AISettings(BaseSettings):
    """AI backend configuration.

    Controls which AI provider and model are used and common model-level
    parameters. The ``resolved_model`` property reconciles the configured
    model string with the selected provider, returning a provider-appropriate
    model name even when the user left the model value at the other provider's
    default.
    """

    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "anthropic"
    model: str = _ANTHROPIC_DEFAULT_MODEL
    temperature: float = 0.2
    max_tokens: int = 4096
    stream: bool = True

    #: Provider-specific Amazon Bedrock settings (region, inference profile,
    #: thinking budget, timeouts). Only consulted when ``provider == "bedrock"``.
    bedrock: BedrockSettings = Field(default_factory=BedrockSettings)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"anthropic", "openai", "bedrock"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}")
        return v

    @property
    def resolved_model(self) -> str:
        """Return a provider-correct model name.

        If the configured ``model`` string does not look like one belonging to
        the chosen ``provider``, a sensible default for that provider is
        returned. This avoids accidental API rejections when switching providers
        but keeping the other provider's default model name.

        For ``bedrock`` the model identity lives in the dedicated
        :attr:`bedrock.model_id` (an inference-profile ID, which has a very
        different shape from a bare ``claude``/``gpt`` name), so that value is
        returned verbatim and the top-level ``model`` field is ignored.
        """
        if self.provider == "openai":
            if self.model.startswith(_OPENAI_MODEL_PREFIXES):
                return self.model
            return _OPENAI_DEFAULT_MODEL
        if self.provider == "anthropic":
            if self.model.startswith("claude"):
                return self.model
            return _ANTHROPIC_DEFAULT_MODEL
        if self.provider == "bedrock":
            return self.bedrock.model_id
        return self.model


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
    default_severity_levels: list[str] = Field(
        default_factory=lambda: ["FATAL", "CRITICAL", "ERROR", "WARNING"]
    )
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


class AgentWeightEntry(BaseSettings):
    """A per-agent weight vector used when combining agent opinions.

    Each entry contains normalized weights (floats) assigned to the logical
    agents that participate in the ensemble. These weights are used during
    consensus and scoring to bias the influence of different agent roles.
    """

    model_config = SettingsConfigDict(extra="ignore")

    os_kernel: float = 0.30
    code_analyst: float = 0.35
    log_historian: float = 0.20
    skeptic: float = 0.15


class AgentWeightsSettings(BaseSettings):
    """Per-fault-class agent weight matrix.

    Provides default AgentWeightEntry objects for known fault classes and an
    ``unknown`` fallback. The :meth:`for_fault_class` helper returns the
    appropriate weight vector for a string-valued FaultClass.
    """

    model_config = SettingsConfigDict(extra="ignore")

    memory_access_violation: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.40, code_analyst=0.35, log_historian=0.15, skeptic=0.10
        )
    )
    null_pointer_dereference: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.40, code_analyst=0.35, log_historian=0.15, skeptic=0.10
        )
    )
    use_after_free: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.35, code_analyst=0.40, log_historian=0.15, skeptic=0.10
        )
    )
    stack_overflow: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.45, code_analyst=0.30, log_historian=0.10, skeptic=0.15
        )
    )
    integer_divide_by_zero: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.35, code_analyst=0.40, log_historian=0.10, skeptic=0.15
        )
    )
    deadlock: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.35, code_analyst=0.30, log_historian=0.20, skeptic=0.15
        )
    )
    assertion_failure: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.25, code_analyst=0.45, log_historian=0.15, skeptic=0.15
        )
    )
    resource_exhaustion: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.35, code_analyst=0.25, log_historian=0.30, skeptic=0.10
        )
    )
    unhandled_exception: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.30, code_analyst=0.35, log_historian=0.20, skeptic=0.15
        )
    )
    unknown: AgentWeightEntry = Field(
        default_factory=lambda: AgentWeightEntry(
            os_kernel=0.30, code_analyst=0.35, log_historian=0.20, skeptic=0.15
        )
    )

    def for_fault_class(self, fault_class_value: str) -> AgentWeightEntry:
        """Return the weight entry for a given FaultClass value string.

        If the provided string does not match a known attribute, the ``unknown``
        fallback entry is returned. This method accepts the FaultClass value
        directly (for convenience when deserializing external inputs).
        """
        return getattr(self, fault_class_value, self.unknown)


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
    """Settings source backed by the two JSON files under :data:`DATA_DIR`.

    ``config.json`` supplies the top-level runtime sections; ``agents.json``
    supplies the weight matrix and is mounted under the ``agent_weights`` key.
    A bad or missing file never aborts startup - it simply contributes nothing,
    leaving the dataclass defaults in force.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        data = dict(_read_json_object(CONFIG_JSON))
        agents = _read_json_object(AGENTS_JSON)
        if agents:
            data["agent_weights"] = agents
        self._data = data

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
    aggregates the core, backends, sandbox, api and agent-weight sections and
    wires in the custom JSON settings source so that ``config.json`` and
    ``agents.json`` are read automatically.
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
        3. JSON files under ``CONFIG_DIR`` (``config.json`` and
           ``agents.json`` merged by :class:`AegisJsonSettingsSource`)
        """
        # Precedence (high → low): explicit init kwargs > AEGIS__* env > JSON.
        return init_settings, env_settings, AegisJsonSettingsSource(settings_cls)

    core: CoreSettings = Field(default_factory=CoreSettings)
    backends: BackendsSettings = Field(default_factory=BackendsSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    api: APISettings = Field(default_factory=APISettings)
    agent_weights: AgentWeightsSettings = Field(default_factory=AgentWeightsSettings)

    def redacted_dump(self) -> dict[str, Any]:
        """Return the settings dict with secret values replaced by '***'"""
        import json

        raw: dict[str, Any] = json.loads(self.model_dump_json())
        _redact_secrets(raw)
        return raw


def _redact_secrets(obj: Any):
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
