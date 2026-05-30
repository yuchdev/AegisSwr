from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    max_debate_rounds: int = 4
    consensus_threshold: float = 0.85
    hitl_confidence_threshold: float = 0.50
    log_window_seconds: int = 30
    user_assumption_token_limit: int = 500
    stack_frames_limit: int = 20


_ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
_OPENAI_DEFAULT_MODEL = "gpt-5.4"
_OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "anthropic"
    model: str = _ANTHROPIC_DEFAULT_MODEL
    temperature: float = 0.2
    max_tokens: int = 4096
    stream: bool = True

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"anthropic", "openai"}
        if v not in allowed:
            raise ValueError(f"provider must be one of {allowed}")
        return v

    @property
    def resolved_model(self) -> str:
        """The model to send, reconciled with ``provider``.

        ``model`` defaults to an Anthropic name. When the provider is switched to
        OpenAI (e.g. ``--ai openai``) without also overriding the model, the
        configured Anthropic name would be rejected by the OpenAI API. This
        substitutes the provider's default model whenever the configured name does
        not belong to the selected provider; an explicit, provider-matching model
        is always respected.
        """
        if self.provider == "openai":
            if self.model.startswith(_OPENAI_MODEL_PREFIXES):
                return self.model
            return _OPENAI_DEFAULT_MODEL
        if self.provider == "anthropic":
            if self.model.startswith("claude"):
                return self.model
            return _ANTHROPIC_DEFAULT_MODEL
        return self.model


class DebugSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    engine: str = "auto"                   # "auto" | "cdb" | "windbg_js"
    timeout_seconds: int = 300
    callback_timeout_seconds: int = 60
    max_faulting_frames: int = 20
    max_other_thread_frames: int = 3
    symbol_cache: str | None = None
    symbol_server_url: str | None = None

    @field_validator("engine")
    @classmethod
    def validate_engine(cls, v: str) -> str:
        allowed = {"auto", "cdb", "windbg_js"}
        if v not in allowed:
            raise ValueError(f"engine must be one of {allowed}")
        return v


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "filesystem"              # filesystem | sqlite | s3 | postgres
    reports_dir: str = "~/.aegis-swr/reports" # filesystem: report JSON files
    objects_dir: str = "~/.aegis-swr/objects" # filesystem: raw binary artifacts
    db_path: str = "~/.aegis-swr/reports.db"  # sqlite: database file
    database_url: str = "postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"
    object_store_url: str = "s3://aegis-raw-inputs"
    object_store_region: str = "us-east-1"
    s3_endpoint_url: str | None = None        # MinIO / custom S3-compatible endpoint
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
    model_config = SettingsConfigDict(extra="ignore")

    provider: str = "file"                  # file | fluent  (elk deferred)
    file_root: str | None = None            # base dir for service→file resolution (file)
    default_severity_levels: list[str] = Field(
        default_factory=lambda: ["FATAL", "CRITICAL", "ERROR", "WARNING"]
    )
    elk_url: str | None = None              # elk (deferred)
    fluent_host: str | None = None          # fluent stub
    fluent_port: int | None = None          # fluent stub
    fluent_tag_prefix: str | None = None    # fluent stub

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"file", "fluent", "elk"}
        if v not in allowed:
            raise ValueError(f"log provider must be one of {allowed}")
        return v


class CodeBackendSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = False                   # false → no CodeBackend; Stage 8 skipped
    provider: str = "git"                   # git | filesystem
    repo_path: str | None = None            # working tree / source root
    window_hours: int = 2                   # default look-back for get_commits_before
    commit_limit: int = 10                  # default max commits returned
    git_timeout_seconds: int = 30           # git subprocess timeout (git provider)

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        allowed = {"git", "filesystem"}
        if v not in allowed:
            raise ValueError(f"code provider must be one of {allowed}")
        return v


class BackendsSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    ai: AISettings = Field(default_factory=AISettings)
    debug: DebugSettings = Field(default_factory=DebugSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    log: LogBackendSettings = Field(default_factory=LogBackendSettings)
    code: CodeBackendSettings = Field(default_factory=CodeBackendSettings)


class SandboxSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    enabled: bool = True
    runtime: str = "docker"
    memory_mb: int = 256
    cpu_limit: float = 0.5
    timeout_seconds: int = 60


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    api_key_header: str = "X-Aegis-API-Key"
    rate_limit_per_minute: int = 10


class AgentWeightEntry(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    os_kernel: float = 0.30
    code_analyst: float = 0.35
    log_historian: float = 0.20
    skeptic: float = 0.15


class AgentWeightsSettings(BaseSettings):
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
        """Return the weight entry for a given FaultClass value string."""
        return getattr(self, fault_class_value, self.unknown)


_YAML_FILE = Path(__file__).parent.parent.parent.parent / "config.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=str(_YAML_FILE),
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
        from pydantic_settings import YamlConfigSettingsSource

        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]
        if _YAML_FILE.exists():
            sources.append(YamlConfigSettingsSource(settings_cls))
        return tuple(sources)

    core: CoreSettings = Field(default_factory=CoreSettings)
    backends: BackendsSettings = Field(default_factory=BackendsSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    api: APISettings = Field(default_factory=APISettings)
    agent_weights: AgentWeightsSettings = Field(default_factory=AgentWeightsSettings)

    def redacted_dump(self) -> dict[str, Any]:
        """Return the settings dict with secret values replaced by '***'."""
        import json

        raw: dict[str, Any] = json.loads(self.model_dump_json())
        _redact_secrets(raw)
        return raw


_SECRET_KEYS = {"api_key", "password", "secret", "token", "database_url"}


def _redact_secrets(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(s in k.lower() for s in _SECRET_KEYS):
                obj[k] = "***"
            else:
                _redact_secrets(v)
    elif isinstance(obj, list):
        for item in obj:
            _redact_secrets(item)
