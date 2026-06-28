
import pytest
from pydantic import ValidationError

from aegis_swr.config.settings import (
    AISettings,
    AnthropicSettings,
    BedrockSettings,
    ModelOverride,
    OpenAISettings,
    Settings,
)
from aegis_swr.core.fault_codes import FaultClass


def test_default_core_settings(settings: Settings):
    assert settings.core.max_debate_rounds == 4
    assert settings.core.consensus_threshold == 0.85
    assert settings.core.hitl_confidence_threshold == 0.50
    assert settings.core.log_window_seconds == 30
    assert settings.core.user_assumption_token_limit == 500


def test_default_ai_settings(settings: Settings):
    assert settings.backends.ai.provider == "anthropic"
    assert settings.backends.ai.stream is True
    assert settings.backends.ai.anthropic.model == "claude-sonnet-4-6"
    assert settings.backends.ai.anthropic.temperature == 0.2
    # The active sub-config is the one named by `provider`.
    assert settings.backends.ai.active.resolved_model == "claude-sonnet-4-6"


def test_default_anthropic_settings():
    anthropic = AnthropicSettings()
    assert anthropic.model == "claude-sonnet-4-6"
    assert anthropic.max_tokens == 4096
    assert anthropic.thinking_budget_tokens == 0
    assert anthropic.prompt_caching is True
    assert anthropic.timeout_seconds == 600.0
    assert anthropic.max_retries == 2


def test_default_openai_settings():
    openai = OpenAISettings()
    assert openai.model == "gpt-5.4"
    assert openai.reasoning_effort is None
    assert openai.max_completion_tokens == 16000
    assert openai.timeout_seconds == 300.0
    assert openai.max_retries == 4


def test_bedrock_settings_defaults():
    bedrock = BedrockSettings()
    assert bedrock.region == "ap-southeast-2"
    assert bedrock.model_id == "au.anthropic.claude-sonnet-4-6"
    assert bedrock.thinking_budget_tokens == 0
    assert bedrock.connect_timeout_seconds == 10
    assert bedrock.read_timeout_seconds == 300
    assert bedrock.max_attempts == 3
    assert bedrock.auth_mode == "auto"


def test_ai_provider_validator_accepts_bedrock():
    ai = AISettings(provider="bedrock")
    assert ai.provider == "bedrock"
    with pytest.raises(ValidationError):
        AISettings(provider="invalid-provider")


def test_bedrock_auth_mode_validator_rejects_unknown():
    BedrockSettings(auth_mode="sigv4")  # valid
    with pytest.raises(ValidationError):
        BedrockSettings(auth_mode="iam-role")


def test_resolved_model_bedrock_returns_profile_id():
    profile_id = "au.anthropic.claude-opus-4-1"
    ai = AISettings(
        provider="bedrock",
        bedrock=BedrockSettings(model_id=profile_id),
    )
    assert ai.resolved_model == profile_id


def test_bedrock_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AEGIS__BACKENDS__AI__BEDROCK__REGION", "us-west-2")
    settings = Settings()
    assert settings.backends.ai.bedrock.region == "us-west-2"


def test_resolved_model_openai_substitutes_default():
    # provider switched to openai but model left at a non-openai name →
    # the OpenAI default model is substituted.
    ai = AISettings(provider="openai", openai=OpenAISettings(model="claude-sonnet-4-6"))
    assert ai.resolved_model == "gpt-5.4"


def test_resolved_model_openai_respects_explicit():
    ai = AISettings(provider="openai", openai=OpenAISettings(model="gpt-4o"))
    assert ai.resolved_model == "gpt-4o"


def test_resolved_model_anthropic_substitutes_default():
    ai = AISettings(provider="anthropic", anthropic=AnthropicSettings(model="gpt-5.4"))
    assert ai.resolved_model == "claude-sonnet-4-6"


def test_resolved_model_anthropic_respects_explicit():
    ai = AISettings(provider="anthropic", anthropic=AnthropicSettings(model="claude-opus-4-8"))
    assert ai.resolved_model == "claude-opus-4-8"


def test_per_model_override_merges_over_provider_defaults():
    # The active model carries an override; for_model() merges it over the
    # provider-level defaults (override wins, untouched fields inherited).
    anthropic = AnthropicSettings(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking_budget_tokens=0,
        models={
            "claude-opus-4-8": ModelOverride(max_tokens=32000, thinking_budget_tokens=8192),
            "claude-haiku-4-5": ModelOverride(thinking_budget_tokens=0),
        },
    )
    effective = anthropic.for_model()
    assert effective.max_tokens == 32000
    assert effective.thinking_budget_tokens == 8192
    # temperature was not overridden → inherited.
    assert effective.temperature == anthropic.temperature
    # The original provider config is left unmutated.
    assert anthropic.max_tokens == 4096


def test_per_model_override_absent_returns_self():
    openai = OpenAISettings(model="gpt-5.4")
    assert openai.for_model() is openai


def test_per_model_override_ignores_foreign_keys():
    # reasoning_effort is not an Anthropic field; merging it must be a no-op
    # rather than an error.
    anthropic = AnthropicSettings(
        model="claude-opus-4-8",
        models={"claude-opus-4-8": ModelOverride(reasoning_effort="high", max_tokens=8000)},
    )
    effective = anthropic.for_model()
    assert effective.max_tokens == 8000
    assert not hasattr(effective, "reasoning_effort")


def test_bedrock_per_model_override_keys_on_model_id():
    bedrock = BedrockSettings(
        model_id="au.anthropic.claude-opus-4-8",
        thinking_budget_tokens=2048,
        models={"au.anthropic.claude-opus-4-8": ModelOverride(thinking_budget_tokens=8192)},
    )
    assert bedrock.for_model().thinking_budget_tokens == 8192


def test_legacy_flat_keys_emit_warning():
    records: list[str] = []
    from loguru import logger

    sink_id = logger.add(records.append, level="WARNING")
    try:
        AISettings(provider="anthropic", model="claude-opus-4-8", max_tokens=9999)  # type: ignore[call-arg]
    finally:
        logger.remove(sink_id)
    assert any("legacy flat backends.ai" in line for line in records)


def test_default_sandbox_settings(settings: Settings):
    assert settings.sandbox.enabled is True
    assert settings.sandbox.runtime == "docker"
    assert settings.sandbox.memory_mb == 256


def test_agent_weights_for_memory_fault(settings: Settings):
    entry = settings.agent_weights.for_fault_class(
        FaultClass.MEMORY_ACCESS_VIOLATION.value
    )
    assert entry.os_kernel == 0.40
    assert entry.code_analyst == 0.35
    # Weights for this fault class should sum to 1.0
    total = entry.os_kernel + entry.code_analyst + entry.log_historian + entry.skeptic
    assert abs(total - 1.0) < 1e-6


def test_agent_weights_for_unknown_fault(settings: Settings):
    entry = settings.agent_weights.for_fault_class(FaultClass.UNKNOWN.value)
    assert entry.os_kernel == 0.30


def test_redacted_dump_hides_database_url(settings: Settings):
    dumped = settings.redacted_dump()
    db_url = dumped["backends"]["storage"]["database_url"]
    assert db_url == "***"


def test_redacted_dump_keeps_non_secret_values(settings: Settings):
    dumped = settings.redacted_dump()
    assert dumped["core"]["max_debate_rounds"] == 4
    assert dumped["backends"]["ai"]["provider"] == "anthropic"
