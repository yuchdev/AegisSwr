"""Unit tests for :mod:`aegis_swr.router.config` validation contract.

Covers roadmap 0003 rules R1-R4, the documented optional-field defaults, and
the strict provider-client isolation invariant. No test performs network I/O.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import pytest

import aegis_swr.router as router_pkg
from aegis_swr.router.config import (
    AgentConfig,
    ProviderConfig,
    RetryPolicy,
    RouterConfig,
)
from aegis_swr.router.exceptions import ConfigValidationError

# Path to the real shipped config, used to assert the committed file is valid.
REAL_AGENTS_YAML = Path(__file__).resolve().parents[3] / "src" / "aegis_swr" / "config" / "agents.yaml"

_FULL_YAML = textwrap.dedent(
    """
    providers:
      anthropic:
        api_key: ${ANTHROPIC_API_KEY}
      deepseek:
        api_key: ${DEEPSEEK_API_KEY}
        base_url: https://api.deepseek.com/v1
      self_hosted:
        base_url: ${VLLM_BASE_URL}/v1
        api_key: ${VLLM_API_KEY}

    agents:
      hypothesis:
        model: anthropic/claude-sonnet-4-6
        role: primary_reasoning
        fallback:
          - deepseek/deepseek-chat
        timeout_s: 30
        retry:
          attempts: 2
          backoff_s: 1.5
      synthesis:
        model: anthropic/claude-sonnet-4-6
        role: verdict_compilation
    """
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write ``content`` to a temp ``agents.yaml`` and return its path.

    :param tmp_path: Pytest-provided temporary directory.
    :param content: YAML document body to write.
    :return: Path to the written file.
    """
    path = tmp_path / "agents.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _set_all_env(monkeypatch: pytest.MonkeyPatch):
    """Set every env var referenced by ``_FULL_YAML`` to a valid value.

    :param monkeypatch: Pytest monkeypatch fixture.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("VLLM_API_KEY", "")
    # Ensure the OpenClaude-gated role is omitted unless a test opts in.
    monkeypatch.delenv("OPENCLAUDE_GRPC_URL", raising=False)


# --------------------------------------------------------------------------- #
# Normal case
# --------------------------------------------------------------------------- #
def test_from_yaml_resolves_env_and_builds_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: a fully-resolvable config parses into structured objects.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a fully-resolvable config parses into structured objects.
    """
    _set_all_env(monkeypatch)
    path = _write_yaml(tmp_path, _FULL_YAML)

    config = RouterConfig.from_yaml(path)

    assert config.providers["anthropic"].api_key == "sk-ant-test"
    assert config.providers["anthropic"].base_url is None
    assert config.providers["deepseek"].base_url == "https://api.deepseek.com/v1"
    assert config.providers["self_hosted"].base_url == "http://localhost:8000/v1"
    assert set(config.agents) == {"primary_reasoning", "verdict_compilation"}


def test_real_agents_yaml_is_valid(monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: the committed src config loads cleanly with env vars present.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the committed src config loads cleanly with env vars present.
    """
    _set_all_env(monkeypatch)

    config = RouterConfig.from_yaml(REAL_AGENTS_YAML)

    assert set(config.providers) == {"anthropic", "deepseek", "self_hosted"}
    assert set(config.agents) == {
        "primary_reasoning",
        "contradiction_finder",
        "verdict_compilation",
        "evidence_classifier",
    }


# --------------------------------------------------------------------------- #
# enabled_when gating (0004 subtask 03)
# --------------------------------------------------------------------------- #
def test_enabled_when_unset_omits_gated_role(monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: with OPENCLAUDE_GRPC_URL unset, openclaude_agent is silently omitted.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: with OPENCLAUDE_GRPC_URL unset, openclaude_agent is silently omitted.
    """
    _set_all_env(monkeypatch)
    monkeypatch.delenv("OPENCLAUDE_GRPC_URL", raising=False)

    # Must not raise even though openclaude_agent's provider is not in providers.
    config = RouterConfig.from_yaml(REAL_AGENTS_YAML)

    assert "openclaude_agent" not in config.agents


def test_enabled_when_set_includes_gated_role(monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: with OPENCLAUDE_GRPC_URL set, openclaude_agent is present with its provider.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: with OPENCLAUDE_GRPC_URL set, openclaude_agent is present with its provider.
    """
    _set_all_env(monkeypatch)
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    config = RouterConfig.from_yaml(REAL_AGENTS_YAML)

    assert "openclaude_agent" in config.agents
    agent = config.agents["openclaude_agent"]
    assert agent.provider == "openclaude"
    assert agent.model is None


def test_enabled_when_empty_string_omits_gated_role(monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: an empty OPENCLAUDE_GRPC_URL is treated as absent (role omitted).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an empty OPENCLAUDE_GRPC_URL is treated as absent (role omitted).
    """
    _set_all_env(monkeypatch)
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "")

    config = RouterConfig.from_yaml(REAL_AGENTS_YAML)

    assert "openclaude_agent" not in config.agents


def test_existing_roles_keep_prefix_inference_and_provider_none(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] router config: regression: the four 0003 roles keep provider=None and prefix inference.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: regression: the four 0003 roles keep provider=None and prefix inference.
    """
    _set_all_env(monkeypatch)
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", "localhost:50051")

    config = RouterConfig.from_yaml(REAL_AGENTS_YAML)

    for role in (
        "primary_reasoning",
        "contradiction_finder",
        "verdict_compilation",
        "evidence_classifier",
    ):
        assert config.agents[role].provider is None
        assert config.agents[role].enabled_when is None


def test_r2_still_fires_for_role_without_explicit_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: r2 still validates prefix inference for roles lacking explicit provider.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: r2 still validates prefix inference for roles lacking explicit provider.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    yaml_body = """
    providers:
      deepseek:
        api_key: ${DEEPSEEK_API_KEY}
        base_url: https://api.deepseek.com/v1

    agents:
      hypothesis:
        model: bogus/model
        role: primary_reasoning
    """
    path = _write_yaml(tmp_path, yaml_body)

    with pytest.raises(ConfigValidationError) as exc_info:
        RouterConfig.from_yaml(path)

    assert "unknown provider 'bogus'" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# R1 - missing environment variables (aggregated)
# --------------------------------------------------------------------------- #
def test_r1_missing_env_vars_are_all_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: every unset ${VAR} is reported together in one message (R1).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: every unset ${VAR} is reported together in one message (R1).
    """
    # Set some, leave others unset.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    path = _write_yaml(tmp_path, _FULL_YAML)

    with pytest.raises(ConfigValidationError) as exc_info:
        RouterConfig.from_yaml(path)

    message = str(exc_info.value)
    assert message.startswith("Missing environment variables: ")
    assert "ANTHROPIC_API_KEY" in message
    assert "VLLM_API_KEY" in message
    # Present vars must not be reported.
    assert "DEEPSEEK_API_KEY" not in message
    assert "VLLM_BASE_URL" not in message


def test_r1_empty_string_api_key_is_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: an env var set to '' is a valid (unauthenticated) credential.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an env var set to '' is a valid (unauthenticated) credential.
    """
    _set_all_env(monkeypatch)
    monkeypatch.setenv("VLLM_API_KEY", "")
    path = _write_yaml(tmp_path, _FULL_YAML)

    config = RouterConfig.from_yaml(path)

    assert config.providers["self_hosted"].api_key == ""


def test_null_api_key_coerces_to_empty_string(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: a present-but-null ``api_key:`` becomes '' (not the literal 'None').

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a present-but-null ``api_key:`` becomes '' (not the literal 'None').
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    yaml_body = """
    providers:
      deepseek:
        api_key: ${DEEPSEEK_API_KEY}
        base_url: https://api.deepseek.com/v1
      self_hosted:
        api_key: ~
        base_url: http://localhost:8000/v1

    agents:
      hypothesis:
        model: deepseek/deepseek-chat
        role: primary_reasoning
    """
    path = _write_yaml(tmp_path, yaml_body)

    config = RouterConfig.from_yaml(path)

    assert config.providers["self_hosted"].api_key == ""


# --------------------------------------------------------------------------- #
# R2 - undefined provider reference
# --------------------------------------------------------------------------- #
def test_r2_undefined_provider_reference_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: an agent model prefix with no provider entry raises (R2).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an agent model prefix with no provider entry raises (R2).
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    yaml_body = """
    providers:
      deepseek:
        api_key: ${DEEPSEEK_API_KEY}
        base_url: https://api.deepseek.com/v1

    agents:
      hypothesis:
        model: anthropic/claude-sonnet-4-6
        role: primary_reasoning
    """
    path = _write_yaml(tmp_path, yaml_body)

    with pytest.raises(ConfigValidationError) as exc_info:
        RouterConfig.from_yaml(path)

    message = str(exc_info.value)
    assert "Agent 'primary_reasoning'" in message
    assert "unknown provider 'anthropic'" in message
    assert "Defined providers: deepseek" in message


def test_r2_all_unknown_provider_references_are_aggregated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: two agents referencing unknown providers surface in one error naming both.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: two agents referencing unknown providers surface in one error naming both.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    yaml_body = """
    providers:
      deepseek:
        api_key: ${DEEPSEEK_API_KEY}
        base_url: https://api.deepseek.com/v1

    agents:
      hypothesis:
        model: anthropic/claude-sonnet-4-6
        role: primary_reasoning
      synthesis:
        model: openai/gpt-4o
        role: verdict_compilation
    """
    path = _write_yaml(tmp_path, yaml_body)

    with pytest.raises(ConfigValidationError) as exc_info:
        RouterConfig.from_yaml(path)

    message = str(exc_info.value)
    assert "Agent 'primary_reasoning'" in message
    assert "unknown provider 'anthropic'" in message
    assert "Agent 'verdict_compilation'" in message
    assert "unknown provider 'openai'" in message


def test_r2_null_model_without_explicit_provider_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: a role with ``model: ~`` and no ``provider:`` fails gracefully (not AttributeError).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a role with ``model: ~`` and no ``provider:`` fails gracefully (not AttributeError).
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    yaml_body = """
    providers:
      deepseek:
        api_key: ${DEEPSEEK_API_KEY}
        base_url: https://api.deepseek.com/v1

    agents:
      broken:
        model: ~
        role: primary_reasoning
    """
    path = _write_yaml(tmp_path, yaml_body)

    with pytest.raises(ConfigValidationError) as exc_info:
        RouterConfig.from_yaml(path)

    message = str(exc_info.value)
    assert "Agent 'primary_reasoning'" in message
    assert "model=null" in message
    assert "no explicit 'provider:' key" in message


# --------------------------------------------------------------------------- #
# R3 - idempotency
# --------------------------------------------------------------------------- #
def test_r3_from_yaml_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: two loads of the same file/env compare equal (frozen contract, R3).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: two loads of the same file/env compare equal (frozen contract, R3).
    """
    _set_all_env(monkeypatch)
    path = _write_yaml(tmp_path, _FULL_YAML)

    first = RouterConfig.from_yaml(path)
    second = RouterConfig.from_yaml(path)

    assert first == second


# --------------------------------------------------------------------------- #
# R4 - unknown role lookup
# --------------------------------------------------------------------------- #
def test_r4_agent_for_role_unknown_raises_keyerror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: unknown role lookup raises KeyError naming requested/available (R4).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: unknown role lookup raises KeyError naming requested/available (R4).
    """
    _set_all_env(monkeypatch)
    config = RouterConfig.from_yaml(_write_yaml(tmp_path, _FULL_YAML))

    with pytest.raises(KeyError) as exc_info:
        config.agent_for_role("nope")

    # KeyError str() wraps the message in quotes; check the inner text.
    message = exc_info.value.args[0]
    assert "Unknown role 'nope'" in message
    assert "primary_reasoning" in message
    assert "verdict_compilation" in message


def test_agent_for_role_returns_matching_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: a known role returns its bound AgentConfig.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a known role returns its bound AgentConfig.
    """
    _set_all_env(monkeypatch)
    config = RouterConfig.from_yaml(_write_yaml(tmp_path, _FULL_YAML))

    agent = config.agent_for_role("primary_reasoning")

    assert agent.model == "anthropic/claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# Defaults when optional fields are omitted
# --------------------------------------------------------------------------- #
def test_optional_fields_have_correct_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: an agent omitting fallback/timeout_s/retry gets documented defaults.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an agent omitting fallback/timeout_s/retry gets documented defaults.
    """
    _set_all_env(monkeypatch)
    config = RouterConfig.from_yaml(_write_yaml(tmp_path, _FULL_YAML))

    synthesis = config.agent_for_role("verdict_compilation")

    assert synthesis.fallback == ()
    assert synthesis.timeout_s == 30.0
    assert synthesis.retry == RetryPolicy(attempts=2, backoff_s=1.0)


def test_fallback_is_stored_as_tuple(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: the fallback list is coerced to a tuple for hashability.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the fallback list is coerced to a tuple for hashability.
    """
    _set_all_env(monkeypatch)
    config = RouterConfig.from_yaml(_write_yaml(tmp_path, _FULL_YAML))

    hypothesis = config.agent_for_role("primary_reasoning")

    assert hypothesis.fallback == ("deepseek/deepseek-chat",)
    assert isinstance(hypothesis.fallback, tuple)
    # Frozen dataclasses must be hashable.
    assert hash(hypothesis) is not None


# --------------------------------------------------------------------------- #
# Frozen / value-object semantics
# --------------------------------------------------------------------------- #
def test_dataclasses_are_frozen():
    """[Unit] router config: config value objects reject mutation (frozen dataclass contract).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: config value objects reject mutation (frozen dataclass contract).
    """
    provider = ProviderConfig(name="anthropic", api_key="x")
    with pytest.raises((AttributeError, TypeError)):
        provider.api_key = "y"  # type: ignore[misc]

    agent = AgentConfig(role="r", model="anthropic/m")
    with pytest.raises((AttributeError, TypeError)):
        agent.model = "z"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Security - resolved api_key must never leak via repr (CLAUDE.md §3)
# --------------------------------------------------------------------------- #
def test_api_key_is_suppressed_in_repr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """[Unit] router config: a resolved api_key secret must not appear in ProviderConfig/RouterConfig repr.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a resolved api_key secret must not appear in ProviderConfig/RouterConfig repr.
    """
    sentinel = "sk-SECRET-SENTINEL-should-not-leak"
    monkeypatch.setenv("ANTHROPIC_API_KEY", sentinel)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ds-test")
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("VLLM_API_KEY", "")
    monkeypatch.delenv("OPENCLAUDE_GRPC_URL", raising=False)
    path = _write_yaml(tmp_path, _FULL_YAML)

    router_config = RouterConfig.from_yaml(path)
    provider_config = router_config.providers["anthropic"]

    # The secret must still be usable via the attribute...
    assert provider_config.api_key == sentinel
    # ...but must never render in either repr.
    assert sentinel not in repr(provider_config)
    assert sentinel not in repr(router_config)


# --------------------------------------------------------------------------- #
# Isolation invariant - no model-client imports in the router package
# --------------------------------------------------------------------------- #
def test_router_package_has_no_model_client_imports():
    """[Unit] router config: no source file in the router package imports a model-client SDK.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no source file in the router package imports a model-client SDK.
    """


    package_dir = Path(router_pkg.__file__).resolve().parent
    forbidden = re.compile(r"^\s*(?:import|from)\s+(litellm|anthropic|openai|deepseek)\b")

    offenders: list[str] = []
    for source in package_dir.rglob("*.py"):
        for line in source.read_text(encoding="utf-8").splitlines():
            if forbidden.match(line):
                offenders.append(f"{source.name}: {line.strip()}")

    assert offenders == []
