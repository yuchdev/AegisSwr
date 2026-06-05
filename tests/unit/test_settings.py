
from aegis_swr.config.settings import AISettings, Settings
from aegis_swr.core.fault_codes import FaultClass


def test_default_core_settings(settings: Settings):
    assert settings.core.max_debate_rounds == 4
    assert settings.core.consensus_threshold == 0.85
    assert settings.core.hitl_confidence_threshold == 0.50
    assert settings.core.log_window_seconds == 30
    assert settings.core.user_assumption_token_limit == 500


def test_default_ai_settings(settings: Settings):
    assert settings.backends.ai.provider == "anthropic"
    assert settings.backends.ai.model == "claude-sonnet-4-6"
    assert settings.backends.ai.temperature == 0.2


def test_resolved_model_openai_substitutes_default():
    # provider switched to openai but model left at the anthropic default →
    # the OpenAI default model is substituted.
    ai = AISettings(provider="openai", model="claude-sonnet-4-6")
    assert ai.resolved_model == "gpt-5.4"


def test_resolved_model_openai_respects_explicit():
    ai = AISettings(provider="openai", model="gpt-4o")
    assert ai.resolved_model == "gpt-4o"


def test_resolved_model_anthropic_substitutes_default():
    ai = AISettings(provider="anthropic", model="gpt-5.4")
    assert ai.resolved_model == "claude-sonnet-4-6"


def test_resolved_model_anthropic_respects_explicit():
    ai = AISettings(provider="anthropic", model="claude-opus-4-8")
    assert ai.resolved_model == "claude-opus-4-8"


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
