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


def test_default_core_settings(settings: Settings):
    """
    [Unit] settings: verifies default core settings.

    Scenario:
        Given test inputs and fixtures for default core settings
        When test_default_core_settings executes the target flow
        Then the expected outcome for default core settings is confirmed.

    Boundaries:
        - Focus: default core settings
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to default core settings
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    assert settings.core.max_debate_rounds == 4
    assert settings.core.consensus_threshold == 0.85
    assert settings.core.hitl_confidence_threshold == 0.50
    assert settings.core.log_window_seconds == 30
    assert settings.core.user_assumption_token_limit == 500


def test_default_ai_settings(settings: Settings):
    """
    [Unit] settings: verifies default ai settings.

    Scenario:
        Given test inputs and fixtures for default ai settings
        When test_default_ai_settings executes the target flow
        Then the expected outcome for default ai settings is confirmed.

    Boundaries:
        - Focus: default ai settings
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to default ai settings
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    assert settings.backends.ai.provider == "anthropic"
    assert settings.backends.ai.stream is True
    assert settings.backends.ai.anthropic.model == "claude-sonnet-4-6"
    assert settings.backends.ai.anthropic.temperature == 0.2
    # The active sub-config is the one named by `provider`.
    assert settings.backends.ai.active.resolved_model == "claude-sonnet-4-6"


def test_default_anthropic_settings():
    """
    [Unit] settings: verifies default anthropic settings.

    Scenario:
        Given test inputs and fixtures for default anthropic settings
        When test_default_anthropic_settings executes the target flow
        Then the expected outcome for default anthropic settings is confirmed.

    Boundaries:
        - Focus: default anthropic settings
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to default anthropic settings
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    anthropic = AnthropicSettings()
    assert anthropic.model == "claude-sonnet-4-6"
    assert anthropic.max_tokens == 4096
    assert anthropic.thinking_budget_tokens == 0
    assert anthropic.prompt_caching is True
    assert anthropic.timeout_seconds == 600.0
    assert anthropic.max_retries == 2


def test_default_openai_settings():
    """
    [Unit] settings: verifies default openai settings.

    Scenario:
        Given test inputs and fixtures for default openai settings
        When test_default_openai_settings executes the target flow
        Then the expected outcome for default openai settings is confirmed.

    Boundaries:
        - Focus: default openai settings
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to default openai settings
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    openai = OpenAISettings()
    assert openai.model == "gpt-5.4"
    assert openai.reasoning_effort is None
    assert openai.max_completion_tokens == 16000
    assert openai.timeout_seconds == 300.0
    assert openai.max_retries == 4


def test_bedrock_settings_defaults():
    """
    [Unit] settings: verifies bedrock settings defaults.

    Scenario:
        Given test inputs and fixtures for bedrock settings defaults
        When test_bedrock_settings_defaults executes the target flow
        Then the expected outcome for bedrock settings defaults is confirmed.

    Boundaries:
        - Focus: bedrock settings defaults
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock settings defaults
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    bedrock = BedrockSettings()
    assert bedrock.region == "ap-southeast-2"
    assert bedrock.model_id == "au.anthropic.claude-sonnet-4-6"
    assert bedrock.thinking_budget_tokens == 0
    assert bedrock.connect_timeout_seconds == 10
    assert bedrock.read_timeout_seconds == 300
    assert bedrock.max_attempts == 3
    assert bedrock.auth_mode == "auto"


def test_ai_provider_validator_accepts_bedrock():
    """
    [Unit] settings: verifies ai provider validator accepts bedrock.

    Scenario:
        Given test inputs and fixtures for ai provider validator accepts bedrock
        When test_ai_provider_validator_accepts_bedrock executes the target flow
        Then the expected outcome for ai provider validator accepts bedrock is confirmed.

    Boundaries:
        - Focus: ai provider validator accepts bedrock
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to ai provider validator accepts bedrock
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    ai = AISettings(provider="bedrock")
    assert ai.provider == "bedrock"
    with pytest.raises(ValidationError):
        AISettings(provider="invalid-provider")


def test_bedrock_auth_mode_validator_rejects_unknown():
    """
    [Unit] settings: verifies bedrock auth mode validator rejects unknown.

    Scenario:
        Given test inputs and fixtures for bedrock auth mode validator rejects unknown
        When test_bedrock_auth_mode_validator_rejects_unknown executes the target flow
        Then the expected outcome for bedrock auth mode validator rejects unknown is confirmed.

    Boundaries:
        - Focus: bedrock auth mode validator rejects unknown
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock auth mode validator rejects unknown
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    BedrockSettings(auth_mode="sigv4")  # valid
    with pytest.raises(ValidationError):
        BedrockSettings(auth_mode="iam-role")


def test_resolved_model_bedrock_returns_profile_id():
    """
    [Unit] settings: verifies resolved model bedrock returns profile id.

    Scenario:
        Given test inputs and fixtures for resolved model bedrock returns profile id
        When test_resolved_model_bedrock_returns_profile_id executes the target flow
        Then the expected outcome for resolved model bedrock returns profile id is confirmed.

    Boundaries:
        - Focus: resolved model bedrock returns profile id
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolved model bedrock returns profile id
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    profile_id = "au.anthropic.claude-opus-4-1"
    ai = AISettings(
        provider="bedrock",
        bedrock=BedrockSettings(model_id=profile_id),
    )
    assert ai.resolved_model == profile_id


def test_bedrock_env_override(monkeypatch: pytest.MonkeyPatch):
    """
    [Unit] settings: verifies bedrock env override.

    Scenario:
        Given test inputs and fixtures for bedrock env override
        When test_bedrock_env_override executes the target flow
        Then the expected outcome for bedrock env override is confirmed.

    Boundaries:
        - Focus: bedrock env override
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock env override
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    monkeypatch.setenv("AEGIS__BACKENDS__AI__BEDROCK__REGION", "us-west-2")
    settings = Settings()
    assert settings.backends.ai.bedrock.region == "us-west-2"


def test_resolved_model_openai_substitutes_default():
    # provider switched to openai but model left at a non-openai name →
    # the OpenAI default model is substituted.
    """
    [Unit] settings: verifies resolved model openai substitutes default.

    Scenario:
        Given test inputs and fixtures for resolved model openai substitutes default
        When test_resolved_model_openai_substitutes_default executes the target flow
        Then the expected outcome for resolved model openai substitutes default is confirmed.

    Boundaries:
        - Focus: resolved model openai substitutes default
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolved model openai substitutes default
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    ai = AISettings(provider="openai", openai=OpenAISettings(model="claude-sonnet-4-6"))
    assert ai.resolved_model == "gpt-5.4"


def test_resolved_model_openai_respects_explicit():
    """
    [Unit] settings: verifies resolved model openai respects explicit.

    Scenario:
        Given test inputs and fixtures for resolved model openai respects explicit
        When test_resolved_model_openai_respects_explicit executes the target flow
        Then the expected outcome for resolved model openai respects explicit is confirmed.

    Boundaries:
        - Focus: resolved model openai respects explicit
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolved model openai respects explicit
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    ai = AISettings(provider="openai", openai=OpenAISettings(model="gpt-4o"))
    assert ai.resolved_model == "gpt-4o"


def test_resolved_model_anthropic_substitutes_default():
    """
    [Unit] settings: verifies resolved model anthropic substitutes default.

    Scenario:
        Given test inputs and fixtures for resolved model anthropic substitutes default
        When test_resolved_model_anthropic_substitutes_default executes the target flow
        Then the expected outcome for resolved model anthropic substitutes default is confirmed.

    Boundaries:
        - Focus: resolved model anthropic substitutes default
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolved model anthropic substitutes default
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    ai = AISettings(provider="anthropic", anthropic=AnthropicSettings(model="gpt-5.4"))
    assert ai.resolved_model == "claude-sonnet-4-6"


def test_resolved_model_anthropic_respects_explicit():
    """
    [Unit] settings: verifies resolved model anthropic respects explicit.

    Scenario:
        Given test inputs and fixtures for resolved model anthropic respects explicit
        When test_resolved_model_anthropic_respects_explicit executes the target flow
        Then the expected outcome for resolved model anthropic respects explicit is confirmed.

    Boundaries:
        - Focus: resolved model anthropic respects explicit
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolved model anthropic respects explicit
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    ai = AISettings(provider="anthropic", anthropic=AnthropicSettings(model="claude-opus-4-8"))
    assert ai.resolved_model == "claude-opus-4-8"


def test_per_model_override_merges_over_provider_defaults():
    # The active model carries an override; for_model() merges it over the
    # provider-level defaults (override wins, untouched fields inherited).
    """
    [Unit] settings: verifies per model override merges over provider defaults.

    Scenario:
        Given test inputs and fixtures for per model override merges over provider defaults
        When test_per_model_override_merges_over_provider_defaults executes the target flow
        Then the expected outcome for per model override merges over provider defaults is confirmed.

    Boundaries:
        - Focus: per model override merges over provider defaults
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to per model override merges over provider defaults
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
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
    """
    [Unit] settings: verifies per model override absent returns self.

    Scenario:
        Given test inputs and fixtures for per model override absent returns self
        When test_per_model_override_absent_returns_self executes the target flow
        Then the expected outcome for per model override absent returns self is confirmed.

    Boundaries:
        - Focus: per model override absent returns self
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to per model override absent returns self
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    openai = OpenAISettings(model="gpt-5.4")
    assert openai.for_model() is openai


def test_per_model_override_ignores_foreign_keys():
    # reasoning_effort is not an Anthropic field; merging it must be a no-op
    # rather than an error.
    """
    [Unit] settings: verifies per model override ignores foreign keys.

    Scenario:
        Given test inputs and fixtures for per model override ignores foreign keys
        When test_per_model_override_ignores_foreign_keys executes the target flow
        Then the expected outcome for per model override ignores foreign keys is confirmed.

    Boundaries:
        - Focus: per model override ignores foreign keys
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to per model override ignores foreign keys
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    anthropic = AnthropicSettings(
        model="claude-opus-4-8",
        models={"claude-opus-4-8": ModelOverride(reasoning_effort="high", max_tokens=8000)},
    )
    effective = anthropic.for_model()
    assert effective.max_tokens == 8000
    assert not hasattr(effective, "reasoning_effort")


def test_bedrock_per_model_override_keys_on_model_id():
    """
    [Unit] settings: verifies bedrock per model override keys on model id.

    Scenario:
        Given test inputs and fixtures for bedrock per model override keys on model id
        When test_bedrock_per_model_override_keys_on_model_id executes the target flow
        Then the expected outcome for bedrock per model override keys on model id is confirmed.

    Boundaries:
        - Focus: bedrock per model override keys on model id
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock per model override keys on model id
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    bedrock = BedrockSettings(
        model_id="au.anthropic.claude-opus-4-8",
        thinking_budget_tokens=2048,
        models={"au.anthropic.claude-opus-4-8": ModelOverride(thinking_budget_tokens=8192)},
    )
    assert bedrock.for_model().thinking_budget_tokens == 8192


def test_legacy_flat_keys_emit_warning():
    """
    [Unit] settings: verifies legacy flat keys emit warning.

    Scenario:
        Given test inputs and fixtures for legacy flat keys emit warning
        When test_legacy_flat_keys_emit_warning executes the target flow
        Then the expected outcome for legacy flat keys emit warning is confirmed.

    Boundaries:
        - Focus: legacy flat keys emit warning
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to legacy flat keys emit warning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    records: list[str] = []
    from loguru import logger

    sink_id = logger.add(records.append, level="WARNING")
    try:
        AISettings(provider="anthropic", model="claude-opus-4-8", max_tokens=9999)
    finally:
        logger.remove(sink_id)
    assert any("legacy flat backends.ai" in line for line in records)


def test_default_sandbox_settings(settings: Settings):
    """
    [Unit] settings: verifies default sandbox settings.

    Scenario:
        Given test inputs and fixtures for default sandbox settings
        When test_default_sandbox_settings executes the target flow
        Then the expected outcome for default sandbox settings is confirmed.

    Boundaries:
        - Focus: default sandbox settings
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to default sandbox settings
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    assert settings.sandbox.enabled is True
    assert settings.sandbox.runtime == "docker"
    assert settings.sandbox.memory_mb == 256


def test_agent_weight_and_panel_sections_are_removed(settings: Settings):
    """
    [Unit] settings: the agent-weight matrix and agent-panel policy sections are gone.

    Scenario:
        Given a pristine Settings instance, when its fields are inspected, then
        there is no ``agent_weights`` and no ``agent_panel`` section - consensus
        weight is now an intrinsic property of each agent, and the candidate
        roster comes from the agent registry, so neither is configured here.

    Boundaries:
        - Focus: absence of the eliminated settings sections
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether Settings re-introduced an agent-weight/agent-panel field
        - Whether the agents.json settings source was re-added
        - Recent changes in code paths exercised by settings
    """
    assert "agent_weights" not in Settings.model_fields
    assert "agent_panel" not in Settings.model_fields
    assert not hasattr(settings, "agent_weights")
    assert not hasattr(settings, "agent_panel")


def test_weight_is_declared_by_each_agent():
    """
    [Unit] settings: each registered agent declares its own consensus weight.

    Scenario:
        Given the registered agent roster, when each agent's ``default_weight``
        class attribute is read, then every agent declares a float and the four
        built-in agents' weights sum to 1.0 - confirming weight is a property of
        the agent rather than external config.

    Boundaries:
        - Focus: weight-as-agent-property invariant
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether a concrete agent is missing its default_weight ClassVar
        - Recent changes in code paths exercised by the agent registry
    """
    from aegis_swr.agents.registry import AGENT_REGISTRY

    weights = {key: cls.default_weight for key, cls in AGENT_REGISTRY.items()}
    assert all(isinstance(w, float) for w in weights.values())
    # The four built-in base agents (the default back-compat panel) sum to 1.0;
    # fault-gated forensic specialists are excluded from that invariant.
    base_weights = {
        key: cls.default_weight
        for key, cls in AGENT_REGISTRY.items()
        if cls.category == "base"
    }
    assert sum(base_weights.values()) == pytest.approx(1.0)
