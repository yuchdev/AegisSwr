import pytest
from pydantic import ValidationError

from aegis_swr.config.settings import (
    AgentPanelSettings,
    AgentWeightEntry,
    AISettings,
    AnthropicSettings,
    BedrockSettings,
    ModelOverride,
    OpenAISettings,
    Settings,
)
from aegis_swr.core.fault_codes import FaultClass


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
    [Mock] settings: verifies bedrock env override.

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
        AISettings(provider="anthropic", model="claude-opus-4-8", max_tokens=9999)  # type: ignore[call-arg]
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


def test_agent_weights_for_memory_fault(settings: Settings):
    """
    [Unit] settings: verifies agent weights for memory fault.

    Scenario:
        Given test inputs and fixtures for agent weights for memory fault
        When test_agent_weights_for_memory_fault executes the target flow
        Then the expected outcome for agent weights for memory fault is confirmed.

    Boundaries:
        - Focus: agent weights for memory fault
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to agent weights for memory fault
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    entry = settings.agent_weights.for_fault_class(FaultClass.MEMORY_ACCESS_VIOLATION.value)
    assert entry.weights["os_kernel"] == 0.40
    assert entry.weights["code_analyst"] == 0.35
    # Weights for this fault class should sum to 1.0
    total = sum(entry.weights.values())
    assert abs(total - 1.0) < 1e-6


def test_agent_weights_for_unknown_fault(settings: Settings):
    """
    [Unit] settings: verifies agent weights for unknown fault.

    Scenario:
        Given test inputs and fixtures for agent weights for unknown fault
        When test_agent_weights_for_unknown_fault executes the target flow
        Then the expected outcome for agent weights for unknown fault is confirmed.

    Boundaries:
        - Focus: agent weights for unknown fault
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to agent weights for unknown fault
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    entry = settings.agent_weights.for_fault_class(FaultClass.UNKNOWN.value)
    assert entry.weights["os_kernel"] == 0.30


def test_agent_weight_entry_accepts_flat_mapping():
    """
    [Unit] settings: verifies AgentWeightEntry accepts a bare agent-key map.

    Scenario:
        Given an ops-authored flat ``{agent_key: weight}`` mapping (no explicit
        ``weights`` wrapper), when AgentWeightEntry is constructed, then the
        before-validator wraps it so ``.weights`` holds the mapping verbatim.
        An explicit ``{"weights": {...}}`` payload is accepted unchanged.

    Boundaries:
        - Focus: flat-vs-structured payload acceptance
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to the flat-mapping validator
        - Whether ``_accept_flat_mapping`` still wraps bare mappings
        - Recent changes in code paths exercised by settings
    """
    flat = AgentWeightEntry.model_validate({"os_kernel": 0.6, "skeptic": 0.4})
    assert flat.weights == {"os_kernel": 0.6, "skeptic": 0.4}
    structured = AgentWeightEntry(weights={"os_kernel": 0.6, "skeptic": 0.4})
    assert structured.weights == {"os_kernel": 0.6, "skeptic": 0.4}


def test_default_agent_panel_settings(settings: Settings):
    """
    [Unit] settings: verifies default agent panel settings.

    Scenario:
        Given a pristine Settings instance, when the agent_panel section is
        read, then the default candidate pool is the historical four agents and
        the per-fault-class override map is empty.

    Boundaries:
        - Focus: AgentPanelSettings defaults on Settings
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to the default panel
        - Whether Settings still wires the agent_panel field
        - Recent changes in code paths exercised by settings
    """
    assert isinstance(settings.agent_panel, AgentPanelSettings)
    assert settings.agent_panel.default_panel == [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "skeptic",
    ]
    assert settings.agent_panel.per_fault_class == {}


def test_default_panel_runtime_settings(settings: Settings):
    """
    [Unit] settings: verifies the runtime panel section defaults to auto mode.

    Scenario:
        Given a pristine Settings instance, when the runtime ``panel`` section is
        read, then the mode is ``"auto"`` and the explicit spec list is empty -
        so a default run auto-selects its panel.

    Boundaries:
        - Focus: PanelRuntimeSettings defaults wired onto Settings.panel
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Whether Settings still wires the runtime ``panel`` field
        - PanelRuntimeSettings default mode/explicit values
    """
    from aegis_swr.config.settings import PanelRuntimeSettings

    assert isinstance(settings.panel, PanelRuntimeSettings)
    assert settings.panel.mode == "auto"
    assert settings.panel.explicit == []


def test_panel_runtime_settings_coerces_explicit_to_agent_specs():
    """
    [Unit] settings: verifies explicit entries coerce into validated AgentSpecs.

    Scenario:
        Given a runtime panel with explicit dict entries (crossing the config.json
        boundary), when PanelRuntimeSettings is constructed, then each entry is
        coerced into a real AgentSpec carrying the parsed priority/weight.

    Boundaries:
        - Focus: the mode="before" lazy-import validator on ``explicit``
        - Fixtures/params: inline explicit dicts
        - Scope: PanelRuntimeSettings only

    On failure, first check:
        - The lazy ``from aegis_swr.agents.base import AgentSpec`` import
        - That AgentSpec.model_validate is applied per entry
    """
    from aegis_swr.agents.base import AgentSpec
    from aegis_swr.config.settings import PanelRuntimeSettings

    panel = PanelRuntimeSettings(
        mode="explicit",
        explicit=[
            {"agent_key": "os_kernel", "priority": 5},
            {"agent_key": "skeptic", "priority": 3, "weight": 0.2},
        ],
    )
    assert panel.mode == "explicit"
    assert all(isinstance(spec, AgentSpec) for spec in panel.explicit)
    assert panel.explicit[0].agent_key == "os_kernel"
    assert panel.explicit[0].priority == 5
    assert panel.explicit[1].weight == 0.2


def test_panel_runtime_settings_rejects_out_of_range_priority():
    """
    [Unit] settings: verifies an out-of-range explicit priority is rejected.

    Scenario:
        Given an explicit entry with a priority outside 1-5, when the runtime
        panel is constructed, then a ValidationError is raised (the AgentSpec
        range constraint is enforced through the coercion validator).

    Boundaries:
        - Focus: invalid-input path for the ``explicit`` coercion
        - Fixtures/params: inline out-of-range priority
        - Scope: PanelRuntimeSettings only

    On failure, first check:
        - AgentSpec's priority Field(ge=1, le=5) constraint
        - That the before-validator surfaces AgentSpec validation errors
    """
    from aegis_swr.config.settings import PanelRuntimeSettings

    with pytest.raises(ValidationError):
        PanelRuntimeSettings(mode="explicit", explicit=[{"agent_key": "os_kernel", "priority": 9}])


def test_panel_runtime_settings_loaded_from_config_json(monkeypatch: pytest.MonkeyPatch):
    """
    [Unit] settings: verifies the runtime panel loads from config.json.

    Scenario:
        Given a config.json carrying a top-level ``panel`` section, when Settings
        is constructed, then Settings.panel reflects that section with its
        explicit entries coerced into AgentSpec instances.

    Boundaries:
        - Focus: config.json → Settings.panel wiring via the JSON source
        - Fixtures/params: monkeypatched JSON reader
        - Scope: Settings only

    On failure, first check:
        - AegisJsonSettingsSource mounting the ``panel`` config.json section
        - The explicit-coercion validator running on JSON-sourced data
    """
    import aegis_swr.config.settings as settings_module

    payload = {
        "panel": {
            "mode": "explicit",
            "explicit": [{"agent_key": "skeptic", "priority": 4}],
        }
    }

    def _fake_reader(path: object) -> dict:
        return dict(payload) if str(path).endswith("config.json") else {}

    monkeypatch.setattr(settings_module, "_read_json_object", _fake_reader)

    loaded = Settings()
    assert loaded.panel.mode == "explicit"
    assert loaded.panel.explicit[0].agent_key == "skeptic"
    assert loaded.panel.explicit[0].priority == 4


def test_redacted_dump_hides_database_url(settings: Settings):
    """
    [Unit] settings: verifies redacted dump hides database url.

    Scenario:
        Given test inputs and fixtures for redacted dump hides database url
        When test_redacted_dump_hides_database_url executes the target flow
        Then the expected outcome for redacted dump hides database url is confirmed.

    Boundaries:
        - Focus: redacted dump hides database url
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to redacted dump hides database url
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    dumped = settings.redacted_dump()
    db_url = dumped["backends"]["storage"]["database_url"]
    assert db_url == "***"


def test_redacted_dump_keeps_non_secret_values(settings: Settings):
    """
    [Unit] settings: verifies redacted dump keeps non secret values.

    Scenario:
        Given test inputs and fixtures for redacted dump keeps non secret values
        When test_redacted_dump_keeps_non_secret_values executes the target flow
        Then the expected outcome for redacted dump keeps non secret values is confirmed.

    Boundaries:
        - Focus: redacted dump keeps non secret values
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to redacted dump keeps non secret values
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by settings
    """
    dumped = settings.redacted_dump()
    assert dumped["core"]["max_debate_rounds"] == 4
    assert dumped["backends"]["ai"]["provider"] == "anthropic"
