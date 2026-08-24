# Milestone 0003 - LiteLLM Model Router

**Package:** `aegis-swr` | **Module root:** `aegis/router/`
**Depends on:** Milestone 0002 (forensic agents; `aegis/core/agents/` in its final state)

This milestone replaces ad-hoc per-agent provider SDK imports with a **single
unified routing layer** backed by [LiteLLM](https://github.com/BerriAI/litellm).
After this milestone, adding or swapping a model requires only an `agents.yaml`
edit - **zero Python changes**.

> **Prerequisite:** `aegis/core/` must contain zero direct provider imports
> (`anthropic`, `openai`, `deepseek`) before this milestone begins.

---

## Background

Aegis SWR currently references models by name in `agents.yaml` but has no
unified routing layer - each agent potentially uses a different SDK directly.
This milestone introduces an embedded LiteLLM router that provides:

- A single async call interface across all providers (Anthropic, DeepSeek,
  self-hosted vLLM, any future model)
- Declarative fallback chains per agent role
- Retry and timeout policy per agent role
- Cost and latency telemetry emitted as `RouterEvent` events on the existing
  `EventBus`
- Full provider isolation - only `aegis/router/client.py` knows LiteLLM exists

The self-hosted vLLM endpoint (OpenAI-compatible, at `${VLLM_BASE_URL}/v1`) is
a first-class provider alongside cloud providers.

---

## Architecture

```
agents.yaml
    │  (parsed by RouterConfig)
    ▼
aegis/router/
    config.py       ← RouterConfig, AgentConfig, ProviderConfig, RetryPolicy
    client.py       ← LiteLLMClient – single async completion interface
    router.py       ← ModelRouter – resolves role → model, owns retry/fallback
    events.py       ← RouterCallStarted/Completed/Failed/FallbackUsed
    exceptions.py   ← RouterException, ConfigValidationError, AllProvidersExhausted
    │
    ▼ (via EventBus)
aegis/core/
    agents/         ← agents call router.complete(role, messages), never LiteLLM
```

**Hard boundary:** `aegis/core/` and `aegis/ui/` must never import `litellm`
or any provider SDK. All model I/O is mediated through
`aegis.router.router.ModelRouter`. This is enforced by a `grep` test in CI.

---

## Tasks

| Task | Name                    | Category       | Output                                                                    |
|------|-------------------------|----------------|---------------------------------------------------------------------------|
| 01.0 | agents.yaml Schema      | configuration  | `providers` block + `fallback`/`timeout_s`/`retry` per-agent fields       |
| 02.0 | Router Foundation Types | infrastructure | `config.py`, `events.py`, `exceptions.py` - typed, no litellm dependency  |
| 03.0 | LiteLLM Client          | infrastructure | `client.py` - the only file in the project that imports `litellm`         |
| 04.0 | Model Router            | infrastructure | `router.py` - retry/fallback orchestration, EventBus emissions            |
| 05.0 | Test Suite              | testing        | Unit, mock-provider, and integration tests under `tests/router/`          |
| 06.0 | Agent Wiring            | integration    | `BaseAgent` + all concrete agents use `ModelRouter`; `app.py` composition |
| 07.0 | Documentation & CI      | documentation  | Config reference, architecture doc, CI pipeline additions                 |

Tasks 01.0 → 02.0 → 03.0 → 04.0 are sequential foundations. Task 05.0 (tests)
is written **incrementally alongside** 02.0–04.0. Task 06.0 depends on 04.0.
Task 07.0 closes the milestone.

---

## Shared contracts (authoritative)

These contracts are defined once here; the per-task READMEs reference them.

### C1 - Provider strings

| Provider key    | LiteLLM prefix     | Auth                                    |
|-----------------|--------------------|-----------------------------------------|
| `anthropic`     | `anthropic/`       | `ANTHROPIC_API_KEY` env var             |
| `deepseek`      | `deepseek/`        | `DEEPSEEK_API_KEY` env var + base URL   |
| `self_hosted`   | `openai/` (alias)  | `VLLM_API_KEY` env + `VLLM_BASE_URL`/v1 |

The `self_hosted` provider uses LiteLLM's `openai/` prefix with a custom
`base_url`. A YAML model string of `self_hosted/<name>` is resolved to
`openai/<name>` by `LiteLLMClient._configure_providers()`.

### C2 - Module isolation boundary

- `import litellm` appears in **exactly one file**: `aegis/router/client.py`.
- `aegis/core/` contains **no** imports of `litellm`, `anthropic`, `openai`,
  or `deepseek` - enforced by a `grep` check baked into the CI pipeline and
  replicated as a pytest test in `tests/router/test_client.py`.

### C3 - RouterEvent taxonomy

All four event types are `frozen=True` dataclasses with a `ClassVar[str]
event_type` sentinel. They are emitted on the existing `EventBus` (same bus
as `EvidenceLine`, `AgentUpdate`, etc.). Only `RouterCallCompleted` carries
token counts and cost - never duplicated across events.

| Class                  | `event_type`                  | When emitted                        |
|------------------------|-------------------------------|-------------------------------------|
| `RouterCallStarted`    | `router.call.started`         | Before each attempt                 |
| `RouterCallCompleted`  | `router.call.completed`       | On success                          |
| `RouterCallFailed`     | `router.call.failed`          | On each individual attempt failure  |
| `RouterFallbackUsed`   | `router.fallback.used`        | When moving to next model in chain  |

### C4 - Retry / fallback semantics

1. Attempt primary model up to `retry.attempts` times with `asyncio.sleep`
   linear backoff (`backoff_s * attempt`). Never `time.sleep`.
2. On exhaustion, iterate `AgentConfig.fallback` list in order (no per-fallback
   retry - one attempt each).
3. If all fail, raise `AllProvidersExhausted(role, tried, errors)`.
4. Non-retriable errors (e.g. context-length-exceeded) skip remaining retries
   and go directly to fallback.

### C5 - Cross-cutting conventions (inherited from 0001/0002)

- `Optional[T]` from `typing`, never `T | None` (including in subscripts).
- `from __future__ import annotations` in every new file.
- `ruff` must stay clean.
- Every new public class/function has a docstring (RST style).
- No direct provider SDKs in `aegis/core/` or `aegis/ui/`.
- `--dry-run` injects a `NullClient` (content `"[dry-run]"`, zero tokens/cost,
  0 ms latency) - useful for CI and UI testing without API keys.

---

## Dependency graph

```
Task 01.0 (agents.yaml Schema)
   │
   └──► Task 02.0 (Router Foundation Types)   ← config, events, exceptions
              │
              ├──► Task 03.0 (LiteLLM Client)  ← client.py (only litellm file)
              │         │
              │         └──► Task 04.0 (Model Router) ← orchestration layer
              │                    │
              └──────────────────── └──► Task 05.0 (Test Suite)   ← incremental
                                          │
                             Task 04.0 ───┘
                                    │
                                    └──► Task 06.0 (Agent Wiring) ← base_agent + app.py
                                                │
                                    Tasks 02–06 ┴──► Task 07.0 (Docs & CI)
```

**Minimum viable:** 01.0 → 02.0 → 03.0 → 04.0 → 05.0 (unit + mock) → 06.0.
**Full milestone:** all seven tasks including integration tests and docs.

---

## File map (target state after milestone)

```
aegis/
├── app.py                          ← updated: router construction + injection
├── config/
│   └── agents.yaml                 ← updated: providers block + fallback/timeout/retry
├── core/
│   └── agents/
│       ├── base_agent.py           ← updated: uses ModelRouter, no provider SDKs
│       ├── hypothesis_agent.py     ← updated: constructor injection
│       ├── adversarial_agent.py    ← updated: constructor injection
│       └── synthesis_agent.py     ← updated: constructor injection
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

tests/integration/
    ├── conftest.py
    └── test_router_integration.py  ← NEW (skipped without API keys)

docs/
    ├── config-reference.md         ← NEW
    └── router-architecture.md      ← NEW
```

---

## Global acceptance criteria

- [ ] `import litellm` appears in exactly one file: `aegis/router/client.py`
- [ ] `aegis/core/` contains no imports of `litellm`, `anthropic`, `openai`,
      or `deepseek`
- [ ] All unit tests pass with `ANTHROPIC_API_KEY=""` (no network calls)
- [ ] Integration tests are **skipped** (not failed) when API keys are absent
- [ ] `python -m aegis.app --dry-run` completes with no API keys set
- [ ] Adding a new model in `agents.yaml` requires zero Python changes
- [ ] `RouterConfig.from_yaml()` on the existing `agents.yaml` does not raise
- [ ] All new public classes and functions have docstrings
- [ ] `ruff check src/ tests/` - clean
