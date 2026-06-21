# Task: Integrate LiteLLM Model Router into Aegis SWR

**For:** Claude Opus (Claude Code)  
**Priority:** core infrastructure  
**Scope:** new `aegis/router/` module + `agents.yaml` schema update + full test suite + docs  
**Prerequisite:** UI MVC isolation task (`aegis-swr-ui-isolation-task.md`) must be complete — `aegis/core/` must contain zero terminal imports before this task begins  
**Outcome:** Aegis SWR orchestrates all model calls through an embedded LiteLLM router; adding or swapping a model requires only an `agents.yaml` edit; zero provider SDKs imported outside `aegis/router/`

---

## Background

Aegis SWR is a forensic analysis pipeline that currently references models by name in `agents.yaml` but has no unified routing layer — each agent potentially uses a different SDK. This task replaces that with an embedded LiteLLM router that provides:

- A single async call interface across all providers (Anthropic, DeepSeek, self-hosted vLLM, any future model)
- Declarative fallback chains per agent role
- Retry and timeout policy per agent role
- Cost and latency telemetry emitted as `RouterEvent` events on the existing `EventBus`
- Full provider isolation — only `aegis/router/` knows LiteLLM exists

The self-hosted vLLM endpoint (OpenAI-compatible, at `${VLLM_BASE_URL}/v1`) is a first-class provider alongside cloud providers.

---

## Architecture

```
agents.yaml
    │  (parsed by RouterConfig)
    ▼
aegis/router/
    config.py       ← RouterConfig, AgentConfig, ProviderConfig dataclasses
    client.py       ← LiteLLMClient — single async completion interface
    router.py       ← ModelRouter — resolves role → model, owns retry/fallback
    events.py       ← RouterEvent, RouterError (emitted on EventBus)
    exceptions.py   ← RouterException, AllProvidersExhausted
    │
    ▼ (via EventBus)
aegis/core/
    agents/         ← agents call router.complete(role, messages), never LiteLLM directly
    │
    ▼
aegis/events.py     ← existing neutral event types (AgentUpdate, EvidenceLine, etc.)
```

**Hard boundary:** `aegis/core/` and `aegis/ui/` must never import `litellm` or any provider SDK. All model I/O is mediated through `aegis.router.router.ModelRouter`.

---

## Subtask 1 — `agents.yaml` Schema Extension

**File:** `aegis/config/agents.yaml`

Extend the existing schema with a `providers` top-level block and per-agent `fallback`, `timeout_s`, and `retry` fields.

```yaml
# aegis/config/agents.yaml

providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}

  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1

  self_hosted:
    base_url: ${VLLM_BASE_URL}/v1
    api_key: ${VLLM_API_KEY}          # may be empty string for unauthenticated

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

  adversarial:
    model: deepseek/deepseek-chat
    role: contradiction_finder
    fallback:
      - anthropic/claude-haiku-4-5
    timeout_s: 20
    retry:
      attempts: 2
      backoff_s: 1.0

  synthesis:
    model: anthropic/claude-sonnet-4-6
    role: verdict_compilation
    fallback: []
    timeout_s: 45
    retry:
      attempts: 1
      backoff_s: 2.0

  fast_triage:
    model: self_hosted/local-model     # resolved via providers.self_hosted.base_url
    role: evidence_classifier
    fallback:
      - deepseek/deepseek-chat
    timeout_s: 10
    retry:
      attempts: 3
      backoff_s: 0.5
```

**Acceptance criteria:**

- [ ] Schema is documented in `docs/config-reference.md` (new file, see Subtask 6)
- [ ] All existing fields (`model`, `role`) remain valid without the new optional fields
- [ ] `RouterConfig.from_yaml()` raises `ConfigValidationError` with a clear message if a referenced provider key is missing from `providers`

---

## Subtask 2 — `aegis/router/config.py`

Implement typed dataclasses that parse `agents.yaml` into structured config objects.

```python
# aegis/router/config.py

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os, yaml


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 2
    backoff_s: float = 1.0


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str          # resolved from env, may be empty
    base_url: str | None  # None for providers with a hardcoded URL (Anthropic)


@dataclass(frozen=True)
class AgentConfig:
    role: str
    model: str            # LiteLLM model string, e.g. "anthropic/claude-sonnet-4-6"
    fallback: list[str]   # ordered fallback model strings
    timeout_s: float
    retry: RetryPolicy


@dataclass(frozen=True)
class RouterConfig:
    providers: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]       # keyed by role name

    @classmethod
    def from_yaml(cls, path: Path) -> RouterConfig:
        """Load and validate agents.yaml, resolving ${ENV_VAR} references."""
        ...

    def agent_for_role(self, role: str) -> AgentConfig:
        """Raise KeyError with a helpful message if role is not configured."""
        ...
```

**Acceptance criteria:**

- [ ] `${ENV_VAR}` references in `api_key` and `base_url` are resolved via `os.environ`; missing vars raise `ConfigValidationError` listing all missing names at once (not one at a time)
- [ ] `from_yaml()` is idempotent — calling it twice on the same file returns equal objects
- [ ] All dataclasses are `frozen=True`
- [ ] No LiteLLM import anywhere in this file

---

## Subtask 3 — `aegis/router/client.py`

Thin async wrapper around LiteLLM's completion API. This is the **only** file in the project that imports `litellm`.

```python
# aegis/router/client.py

from __future__ import annotations
import litellm
from dataclasses import dataclass


@dataclass
class CompletionRequest:
    model: str
    messages: list[dict]          # OpenAI message format
    timeout_s: float
    extra_headers: dict = field(default_factory=dict)


@dataclass
class CompletionResponse:
    model_used: str               # actual model that responded (may differ from requested if fallback)
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float | None        # None if LiteLLM cannot determine cost


class LiteLLMClient:
    """
    Async wrapper around litellm.acompletion.
    Handles provider-specific auth configuration.
    Raises RouterException on all errors — never re-raises litellm internals.
    """

    def __init__(self, provider_configs: dict[str, ProviderConfig]) -> None:
        self._configure_providers(provider_configs)

    def _configure_providers(self, providers: dict[str, ProviderConfig]) -> None:
        """
        Set litellm API keys and base URLs for each configured provider.
        Called once at construction; not called again during the object's lifetime.
        """
        ...

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """
        Single model call. Does NOT implement retry or fallback — that is
        ModelRouter's responsibility.
        Raises RouterException wrapping the underlying cause on failure.
        """
        ...
```

**Acceptance criteria:**

- [ ] `litellm` is imported **only** in this file — enforced by a `grep` check in CI (see Subtask 5)
- [ ] `CompletionResponse.cost_usd` is populated using `litellm.completion_cost()` when available, `None` otherwise (no exception raised)
- [ ] `latency_ms` is measured wall-clock from call entry to response receipt
- [ ] All litellm exceptions are caught and re-raised as `RouterException` with the original as `__cause__`

---

## Subtask 4 — `aegis/router/router.py`

The orchestration layer. Resolves agent role → model, executes with retry/fallback, emits `RouterEvent` on the bus.

```python
# aegis/router/router.py

from __future__ import annotations
from aegis.router.config import RouterConfig, AgentConfig
from aegis.router.client import LiteLLMClient, CompletionRequest, CompletionResponse
from aegis.router.events import RouterCallStarted, RouterCallCompleted, RouterCallFailed, RouterFallbackUsed
from aegis.router.exceptions import AllProvidersExhausted
from aegis.event_bus import EventBus


class ModelRouter:
    """
    Public interface for all model calls within Aegis SWR.

    Usage:
        router = ModelRouter.from_config(config, bus)
        response = await router.complete(role="primary_reasoning", messages=[...])
    """

    def __init__(self, config: RouterConfig, client: LiteLLMClient, bus: EventBus) -> None:
        ...

    @classmethod
    def from_config(cls, config: RouterConfig, bus: EventBus) -> ModelRouter:
        """Construct with a LiteLLMClient configured from RouterConfig."""
        ...

    async def complete(
        self,
        role: str,
        messages: list[dict],
        *,
        run_id: str,              # propagated to RouterEvent for correlation
    ) -> CompletionResponse:
        """
        Resolve role → AgentConfig, attempt primary model with retry,
        fall back through AgentConfig.fallback list on failure,
        raise AllProvidersExhausted if all options fail.

        Emits on bus:
          RouterCallStarted   — before each attempt
          RouterCallCompleted — on success
          RouterCallFailed    — on each individual attempt failure
          RouterFallbackUsed  — when moving to next model in fallback chain
        """
        ...
```

**Retry logic:**

```
for attempt in range(agent_config.retry.attempts):
    try:
        response = await client.complete(request)
        emit RouterCallCompleted
        return response
    except RouterException:
        emit RouterCallFailed(attempt=attempt)
        if attempt < max_attempts - 1:
            await asyncio.sleep(backoff_s * (attempt + 1))   # linear backoff
        continue

# primary model exhausted → try fallbacks
for fallback_model in agent_config.fallback:
    emit RouterFallbackUsed(from_model=..., to_model=fallback_model)
    try:
        response = await client.complete(request with fallback_model)
        emit RouterCallCompleted
        return response
    except RouterException:
        emit RouterCallFailed(...)
        continue

raise AllProvidersExhausted(role=role, tried=[primary] + fallbacks)
```

**Acceptance criteria:**

- [ ] `ModelRouter` has no knowledge of LiteLLM internals — it only calls `LiteLLMClient.complete()`
- [ ] `run_id` is attached to every emitted `RouterEvent`
- [ ] Backoff is `asyncio.sleep`, not `time.sleep` — never blocks the event loop
- [ ] `AllProvidersExhausted` includes the full list of models tried and their individual error messages

---

## Subtask 5 — `aegis/router/events.py` and `aegis/router/exceptions.py`

### events.py

Extend the existing `aegis/events.py` event taxonomy with router-specific events. These are emitted on the same `EventBus` as `EvidenceLine`, `AgentUpdate`, etc.

```python
# aegis/router/events.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class RouterCallStarted:
    event_type: ClassVar[str] = "router.call.started"
    run_id: str
    role: str
    model: str
    attempt: int


@dataclass(frozen=True)
class RouterCallCompleted:
    event_type: ClassVar[str] = "router.call.completed"
    run_id: str
    role: str
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float | None


@dataclass(frozen=True)
class RouterCallFailed:
    event_type: ClassVar[str] = "router.call.failed"
    run_id: str
    role: str
    model: str
    attempt: int
    error: str


@dataclass(frozen=True)
class RouterFallbackUsed:
    event_type: ClassVar[str] = "router.fallback.used"
    run_id: str
    role: str
    from_model: str
    to_model: str
    reason: str
```

### exceptions.py

```python
# aegis/router/exceptions.py

class RouterException(Exception):
    """Wraps any provider or network error from LiteLLMClient."""

class ConfigValidationError(Exception):
    """Raised when agents.yaml fails validation."""

class AllProvidersExhausted(RouterException):
    def __init__(self, role: str, tried: list[str], errors: list[str]) -> None:
        self.role = role
        self.tried = tried
        self.errors = errors
        super().__init__(
            f"All providers exhausted for role '{role}'. "
            f"Tried: {tried}. Errors: {errors}"
        )
```

**Acceptance criteria:**

- [ ] All event dataclasses are `frozen=True`
- [ ] All event dataclasses have a `ClassVar[str] event_type` — used by `EventBus` subscribers to filter by type without `isinstance` checks
- [ ] `RouterCallCompleted` is the only event that contains token counts and cost — not duplicated elsewhere

---

## Subtask 6 — Unit Tests

**Location:** `tests/router/`

Use `pytest` + `pytest-asyncio`. All external I/O (LiteLLM, filesystem) is mocked. Tests must pass with no API keys set.

### `tests/router/test_config.py`

```python
# Tests for RouterConfig.from_yaml()

def test_from_yaml_resolves_env_vars(tmp_path, monkeypatch):
    """${ANTHROPIC_API_KEY} is resolved from environment."""

def test_from_yaml_missing_env_var_lists_all_missing(tmp_path):
    """ConfigValidationError message lists all missing vars, not just the first."""

def test_from_yaml_missing_provider_reference_raises(tmp_path):
    """Agent referencing an undefined provider key raises ConfigValidationError."""

def test_from_yaml_is_idempotent(tmp_path, monkeypatch):
    """Calling from_yaml twice returns equal RouterConfig objects."""

def test_agent_for_role_missing_raises_key_error_with_helpful_message():
    """KeyError message includes the requested role and available roles."""

def test_frozen_dataclasses_are_immutable():
    """Attempt to mutate ProviderConfig, AgentConfig, RouterConfig raises FrozenInstanceError."""

def test_optional_fields_have_correct_defaults():
    """agents.yaml entries without fallback/timeout/retry use documented defaults."""
```

### `tests/router/test_client.py`

```python
# Tests for LiteLLMClient — litellm.acompletion is always mocked

@pytest.fixture
def mock_litellm_success(mocker):
    """Returns a mock that simulates a successful litellm.acompletion response."""

@pytest.fixture
def mock_litellm_failure(mocker):
    """Returns a mock that raises litellm.exceptions.APIError."""

async def test_complete_returns_completion_response(mock_litellm_success):
    """Successful call returns CompletionResponse with correct fields populated."""

async def test_complete_measures_latency_ms(mock_litellm_success):
    """latency_ms is positive and approximately correct (within 50ms of actual sleep)."""

async def test_complete_wraps_litellm_exception_as_router_exception(mock_litellm_failure):
    """litellm.APIError is caught and re-raised as RouterException with __cause__ set."""

async def test_complete_populates_cost_usd_when_available(mock_litellm_success, mocker):
    """cost_usd is populated from litellm.completion_cost() when it returns a value."""

async def test_complete_sets_cost_usd_none_when_cost_unavailable(mock_litellm_success, mocker):
    """cost_usd is None (not an exception) when litellm.completion_cost() raises."""

async def test_litellm_is_only_imported_in_client():
    """
    Grep test: assert 'import litellm' appears in client.py and NOWHERE else
    under aegis/.
    """
    import ast, pathlib
    hits = []
    for py in pathlib.Path("aegis").rglob("*.py"):
        if py.name == "client.py" and "router" in str(py):
            continue
        src = py.read_text()
        if "litellm" in src:
            hits.append(str(py))
    assert hits == [], f"litellm imported outside aegis/router/client.py: {hits}"
```

### `tests/router/test_router.py`

```python
# Tests for ModelRouter — LiteLLMClient is always mocked

@pytest.fixture
def mock_client_success(mocker):
    """LiteLLMClient.complete returns a valid CompletionResponse."""

@pytest.fixture
def mock_client_always_fails(mocker):
    """LiteLLMClient.complete always raises RouterException."""

@pytest.fixture
def mock_client_fails_then_succeeds(mocker):
    """LiteLLMClient.complete raises RouterException on first call, succeeds on second."""

@pytest.fixture
def event_bus():
    """Returns a real EventBus with a list-collecting subscriber for assertions."""

async def test_complete_success_emits_started_and_completed(mock_client_success, event_bus):
    """Successful call emits RouterCallStarted then RouterCallCompleted on the bus."""

async def test_complete_success_returns_response(mock_client_success, event_bus):
    """Successful call returns the CompletionResponse from the client."""

async def test_complete_retries_on_failure(mock_client_fails_then_succeeds, event_bus):
    """First failure triggers retry; second attempt succeeds; RouterCallFailed emitted once."""

async def test_complete_fallback_used_when_primary_exhausted(mock_client_always_fails, event_bus):
    """
    When primary model exhausts retries, RouterFallbackUsed is emitted
    and fallback model is attempted.
    """

async def test_complete_raises_all_providers_exhausted(mock_client_always_fails, event_bus):
    """AllProvidersExhausted is raised when all models in primary + fallback chain fail."""

async def test_all_providers_exhausted_includes_full_tried_list(mock_client_always_fails, event_bus):
    """AllProvidersExhausted.tried contains primary + all fallback model names."""

async def test_run_id_propagated_to_all_events(mock_client_success, event_bus):
    """Every RouterEvent emitted for a call carries the same run_id passed to complete()."""

async def test_backoff_is_async_sleep_not_time_sleep(mock_client_fails_then_succeeds, mocker):
    """asyncio.sleep is called for backoff, not time.sleep."""

async def test_unknown_role_raises_key_error(mock_client_success, event_bus):
    """Calling complete() with an unknown role raises KeyError before any model call."""
```

---

## Subtask 7 — Mock Tests (Provider Simulation)

**Location:** `tests/router/mocks/`

Simulate provider behaviour without real API calls, testing the router's response to various provider failure modes.

### `tests/router/mocks/providers.py`

```python
"""
Reusable mock provider factories for testing.
Each returns a coroutine that can be set as the side_effect
of a mocked LiteLLMClient.complete.
"""

def make_timeout_provider(after_s: float = 0.0):
    """Raises asyncio.TimeoutError after the given delay."""

def make_rate_limit_provider(fail_n_times: int = 1):
    """Raises RouterException simulating HTTP 429 for the first N calls, then succeeds."""

def make_context_length_provider():
    """Raises RouterException simulating 'context length exceeded' error."""

def make_slow_provider(latency_ms: float = 500.0):
    """Succeeds but with artificial latency — used to test timeout_s enforcement."""

def make_flaky_provider(failure_rate: float = 0.5, seed: int = 42):
    """Succeeds or fails randomly with a fixed seed for reproducibility."""
```

### `tests/router/mocks/test_provider_scenarios.py`

```python
async def test_timeout_triggers_fallback():
    """Provider timeout causes router to fall back to next model."""

async def test_rate_limit_triggers_retry_then_succeeds():
    """429 on first attempt triggers retry; second attempt succeeds."""

async def test_context_length_does_not_retry():
    """
    Context-length-exceeded errors skip retries and go directly to fallback,
    since retrying the same model with the same input will always fail.
    (Only implement if router distinguishes retriable vs non-retriable errors.)
    """

async def test_all_models_timeout_raises_all_providers_exhausted():
    """When every model in the chain times out, AllProvidersExhausted is raised."""

async def test_slow_provider_respects_timeout_s():
    """A provider slower than timeout_s is cancelled, not waited on."""

async def test_flaky_provider_eventually_succeeds_within_retries():
    """A provider with 50% failure rate succeeds within 2 retry attempts (seeded)."""

async def test_router_events_correct_for_rate_limit_retry_scenario():
    """
    Scenario: 429 → retry → success.
    Expected events: Started, Failed(attempt=0), Started, Completed.
    """
```

---

## Subtask 8 — Integration Tests

**Location:** `tests/integration/test_router_integration.py`

These tests run against **real providers** only when the corresponding API key is set. They are skipped in CI unless the key is present. They verify end-to-end flow from `ModelRouter.complete()` through to a real model response.

```python
import pytest, os

pytestmark = pytest.mark.integration   # run with: pytest -m integration

def has_key(env_var: str) -> bool:
    return bool(os.environ.get(env_var))


@pytest.mark.skipif(not has_key("ANTHROPIC_API_KEY"), reason="No ANTHROPIC_API_KEY")
async def test_anthropic_claude_completes_successfully(router_from_yaml):
    """
    Real call to anthropic/claude-haiku-4-5 (cheapest model, short prompt).
    Verifies CompletionResponse fields are populated and content is non-empty.
    """

@pytest.mark.skipif(not has_key("DEEPSEEK_API_KEY"), reason="No DEEPSEEK_API_KEY")
async def test_deepseek_completes_successfully(router_from_yaml):
    """Real call to deepseek/deepseek-chat with a minimal forensic prompt."""

@pytest.mark.skipif(not has_key("VLLM_BASE_URL"), reason="No VLLM_BASE_URL")
async def test_self_hosted_vllm_completes_successfully(router_from_yaml):
    """Real call to the self-hosted vLLM endpoint at VLLM_BASE_URL."""

@pytest.mark.skipif(
    not has_key("ANTHROPIC_API_KEY") or not has_key("DEEPSEEK_API_KEY"),
    reason="Need both ANTHROPIC_API_KEY and DEEPSEEK_API_KEY"
)
async def test_fallback_to_deepseek_when_anthropic_fails(router_with_bad_anthropic_key):
    """
    Router configured with an invalid Anthropic key falls back to DeepSeek.
    Verifies RouterFallbackUsed is emitted and DeepSeek response is returned.
    """

async def test_router_events_are_emitted_on_real_call(router_from_yaml):
    """
    With any available provider, verifies that RouterCallStarted and
    RouterCallCompleted are emitted on the EventBus with correct run_id.
    """

async def test_all_providers_exhausted_raises_correctly(router_with_all_bad_keys):
    """
    Router configured with invalid keys for all providers raises
    AllProvidersExhausted with all model names in .tried.
    """
```

**`conftest.py` fixtures for integration tests:**

```python
@pytest.fixture
def router_from_yaml(tmp_path):
    """
    Builds a ModelRouter from a minimal agents.yaml using real env vars.
    Uses cheapest available model (claude-haiku-4-5 or deepseek-chat).
    """

@pytest.fixture
def router_with_bad_anthropic_key(tmp_path, monkeypatch):
    """Sets ANTHROPIC_API_KEY to 'invalid-key' so Anthropic calls fail."""

@pytest.fixture
def router_with_all_bad_keys(tmp_path, monkeypatch):
    """Sets all provider API keys to 'invalid-key'."""
```

---

## Subtask 9 — Wire Router into Agent Layer

Update `aegis/core/agents/` to call `ModelRouter.complete()` instead of any direct SDK.

**Target:** every agent that currently makes a model call.

```python
# aegis/core/agents/base_agent.py  — AFTER

from aegis.router.router import ModelRouter
from aegis.router.exceptions import AllProvidersExhausted

class BaseAgent:
    def __init__(self, router: ModelRouter, bus: EventBus) -> None:
        self._router = router
        self._bus = bus

    async def reason(
        self,
        messages: list[dict],
        run_id: str,
    ) -> AgentUpdate:
        try:
            response = await self._router.complete(
                role=self.role,
                messages=messages,
                run_id=run_id,
            )
        except AllProvidersExhausted as exc:
            # emit a PipelineError event and propagate
            self._bus.publish(PipelineError(
                run_id=run_id,
                stage=self.role,
                error=str(exc),
            ))
            raise
        return self._parse_response(response)
```

**Acceptance criteria:**

- [ ] No `import anthropic`, `import openai`, `import deepseek` in `aegis/core/agents/`
- [ ] `BaseAgent.__init__` receives `ModelRouter` via constructor injection — no global state
- [ ] `AllProvidersExhausted` results in a `PipelineError` event on the bus before propagating

---

## Subtask 10 — Update `app.py` Wiring

`app.py` is the composition root. It must construct `RouterConfig → LiteLLMClient → ModelRouter` and inject `ModelRouter` into agents.

```python
# aegis/app.py  — relevant section

from aegis.router.config import RouterConfig
from aegis.router.router import ModelRouter

def build_pipeline(config_dir: Path, bus: EventBus) -> Pipeline:
    router_config = RouterConfig.from_yaml(config_dir / "agents.yaml")
    router = ModelRouter.from_config(router_config, bus)

    hypothesis_agent = HypothesisAgent(router=router, bus=bus)
    adversarial_agent = AdversarialAgent(router=router, bus=bus)
    synthesis_agent   = SynthesisAgent(router=router, bus=bus)

    return Pipeline(
        agents=[hypothesis_agent, adversarial_agent, synthesis_agent],
        bus=bus,
    )
```

**Acceptance criteria:**

- [ ] `RouterConfig` is instantiated once at startup, not per-call
- [ ] `ModelRouter` is shared across all agents — one instance, not one per agent
- [ ] `--dry-run` CLI flag bypasses `LiteLLMClient` entirely (inject a `NullClient` that returns a fixed `CompletionResponse`) — useful for CI and UI testing

---

## Subtask 11 — Documentation

### `docs/config-reference.md` (new file)

Full reference for `agents.yaml` and `sources.yaml`. Sections:

- `providers` block: all supported keys, env var resolution rules, which fields are optional
- `agents` block: `model` string format (LiteLLM notation), `fallback` list, `timeout_s` units, `retry` subfields and defaults
- Model string examples: `anthropic/claude-sonnet-4-6`, `deepseek/deepseek-chat`, `self_hosted/my-model`
- Adding a new provider: step-by-step (add to `providers`, reference in agent, no code changes required)
- Adding a new agent role: step-by-step (add to `agents.yaml`, implement `BaseAgent` subclass)

### `docs/router-architecture.md` (new file)

- Architecture diagram (ASCII) showing `agents.yaml → RouterConfig → ModelRouter → LiteLLMClient → provider`
- Event flow: which `RouterEvent` types are emitted at each stage
- Boundary contract: what `aegis/core/` is and is not allowed to import
- Fallback and retry semantics: how `attempts` and `backoff_s` interact, when fallback is triggered
- How to add a new event subscriber to observe routing telemetry

### `README.md` (update existing)

Add a **Model Configuration** section linking to `docs/config-reference.md`. Update the quick-start to include `agents.yaml` setup and the required env vars per provider.

### `CHANGELOG.md` (update)

Add entry under `[Unreleased]`:

```markdown
### Added
- LiteLLM model router (`aegis/router/`) providing unified async completion
  interface across Anthropic, DeepSeek, and self-hosted vLLM providers
- Declarative fallback chains and retry policy per agent role in `agents.yaml`
- Router telemetry events (`RouterCallStarted`, `RouterCallCompleted`,
  `RouterCallFailed`, `RouterFallbackUsed`) emitted on the existing EventBus
- `--dry-run` CLI flag for pipeline testing without model calls
- Integration test suite (skipped unless API keys present in environment)
```

---

## File Map After This Task

```
aegis/
├── app.py                          ← updated: router construction + injection
├── config/
│   └── agents.yaml                 ← updated: providers block + fallback/timeout/retry fields
├── core/
│   └── agents/
│       ├── base_agent.py           ← updated: uses ModelRouter, no provider SDKs
│       ├── hypothesis_agent.py     ← updated: constructor injection
│       ├── adversarial_agent.py    ← updated: constructor injection
│       └── synthesis_agent.py      ← updated: constructor injection
└── router/                         ← NEW MODULE
    ├── __init__.py
    ├── config.py
    ├── client.py                   ← ONLY file that imports litellm
    ├── router.py
    ├── events.py
    └── exceptions.py

tests/
└── router/                         ← NEW
    ├── __init__.py
    ├── conftest.py
    ├── test_config.py
    ├── test_client.py
    ├── test_router.py
    └── mocks/
        ├── __init__.py
        ├── providers.py
        └── test_provider_scenarios.py

tests/integration/                  ← NEW
    ├── __init__.py
    ├── conftest.py
    └── test_router_integration.py

docs/
    ├── config-reference.md         ← NEW
    └── router-architecture.md      ← NEW
```

---

## CI Requirements

Add to the CI pipeline (`.github/workflows/` or equivalent):

```yaml
- name: Unit tests (no API keys required)
  run: pytest tests/router/ -v --tb=short

- name: Lint: litellm isolation check
  run: pytest tests/router/test_client.py::test_litellm_is_only_imported_in_client -v

- name: Integration tests (skipped if no keys)
  run: pytest -m integration tests/integration/ -v --tb=short
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    VLLM_BASE_URL: ${{ secrets.VLLM_BASE_URL }}
```

---

## Global Acceptance Criteria

- [ ] `import litellm` appears in exactly one file: `aegis/router/client.py` (enforced by grep test)
- [ ] `aegis/core/` contains no imports of `litellm`, `anthropic`, `openai`, or `deepseek`
- [ ] All unit tests pass with `ANTHROPIC_API_KEY=""` (no network calls in unit tests)
- [ ] Integration tests are skipped (not failed) when API keys are absent
- [ ] `python -m aegis.app --dry-run` completes successfully with no API keys set
- [ ] Adding a new model in `agents.yaml` requires zero Python changes
- [ ] `RouterConfig.from_yaml()` called with the existing `agents.yaml` does not raise
- [ ] All new public classes and functions have docstrings
- [ ] All new files have type annotations (`from __future__ import annotations` + full hints)

---

## Notes for Opus

- Implement subtasks in dependency order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11
- Subtasks 6, 7, 8 can be implemented incrementally alongside their corresponding source subtasks (write tests as you implement, not after)
- The `self_hosted` provider uses LiteLLM's `openai/` prefix with a custom `base_url` — model string in YAML is `self_hosted/<name>`, resolved to `openai/<name>` by `LiteLLMClient._configure_providers()` using the `base_url` from `ProviderConfig`
- Do not implement cost-optimized routing (choosing cheapest model per call) in this task — that is a future enhancement; this task delivers reliable routing with explicit fallback only
- The `--dry-run` `NullClient` should return a `CompletionResponse` with `content="[dry-run]"`, zero tokens, zero cost, and 0ms latency
