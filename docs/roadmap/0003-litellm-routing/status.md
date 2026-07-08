# Milestone 0003 - LiteLLM Model Router - Status

Tracks progress against [plan.md](/docs/roadmap/0003-litellm-routing/plan.md).
Updated as each task lands.

## Current status

| Task | Name                    | Status        | Tests |
|------|-------------------------|---------------|-------|
| 01.0 | agents.yaml Schema      | ✅ Complete    | `tests/unit/router/test_config.py` |
| 02.0 | Router Foundation Types | ✅ Complete (subtask 02 `events.py` deferred) | `tests/unit/router/{test_config,test_exceptions}.py` |
| 03.0 | LiteLLM Client          | ⬜ Not started | -     |
| 04.0 | Model Router            | ⬜ Not started | -     |
| 05.0 | Test Suite              | ⬜ Not started | -     |
| 06.0 | Agent Wiring            | ⬜ Not started | -     |
| 07.0 | Documentation & CI      | ⬜ Not started | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** the **configuration/foundation slice (Tasks 01.0 + 02.0)
is implemented** as a dependency of Milestone 0004 — `src/aegis_swr/config/agents.yaml`
(providers block + agent roles), `src/aegis_swr/router/{__init__,config,exceptions}.py`
(`RouterConfig.from_yaml`, frozen config dataclasses, exception hierarchy), and
`tests/unit/router/`. Deliberately **not** built: Task 02.0 subtask 02
(`events.py`/`RouterEvent` — its only consumer is the unbuilt ModelRouter, and
Milestone 0004's events subclass the live `DomainEvent` bus instead), and Tasks
03.0–07.0 (LiteLLM client, ModelRouter, router tests, agent wiring, docs/CI) — none
of which Milestone 0004 requires. The router package carries **no `litellm` /
`anthropic` / `openai` / `deepseek` import** (isolation invariant, enforced by a test).
`agents.yaml` is currently inert config: it is parsed by `RouterConfig.from_yaml` and
tests, but nothing in the running app loads it yet (runtime config remains JSON via
`~/.aegis-swr/config.json`); wiring it in is Task 06.0 (unbuilt, unneeded here).

> **Why this partial slice.** Milestone 0004 (OpenClaude Integration) depends on 0003's
> `agents.yaml` + `RouterConfig.from_yaml` + `enabled_when` config layer for its
> `openclaude_agent` role. Rather than build all of 0003 (much of which duplicates the
> already-existing `AISettings`/`backends.ai` provider selection), only the minimal
> config/parsing slice 0004 actually needs was built. See
> `docs/roadmap/0004-code-intelligence/status.md` (Task 01.0).

## Notes & decisions

- **LiteLLM chosen** as the routing abstraction because it provides a unified
  async interface across 100+ providers with a single pip install, supports
  fallback chains natively, and exposes `completion_cost()` for telemetry.
- **Isolation is non-negotiable.** `litellm` in one file only - enforced by a
  `grep` test in CI. Any drift is a blocker.
- **Self-hosted vLLM** is a first-class provider via LiteLLM's `openai/` prefix
  + custom `base_url`. No separate adapter needed.
- **`--dry-run` NullClient** is required before Task 06.0 lands, so the full
  pipeline can be exercised in CI without API keys.

## Decomposition tree (as built)

The milestone is decomposed into **7 tasks / 32 subtasks** (41 Markdown files
total, including `plan.md` and this `status.md`).

```
docs/roadmap/0003-litellm-routing/
├── plan.md                                   ← milestone spec (tasks, contracts C1–C5)
├── status.md                                 ← this tracker
├── 01.0-agents-yaml-schema/                  ← configuration
│   ├── README.md
│   ├── 01-providers-block.md
│   ├── 02-agent-fields.md
│   └── 03-config-validation.md
├── 02.0-router-foundation/                   ← infrastructure (no litellm dep)
│   ├── README.md
│   ├── 01-config-dataclasses.md
│   ├── 02-events-dataclasses.md
│   ├── 03-exceptions.md
│   └── 04-package-init.md
├── 03.0-litellm-client/                      ← infrastructure (litellm isolation)
│   ├── README.md
│   ├── 01-completion-types.md
│   ├── 02-provider-setup.md
│   ├── 03-async-complete.md
│   └── 04-isolation-boundary.md
├── 04.0-model-router/                        ← infrastructure (orchestration)
│   ├── README.md
│   ├── 01-router-interface.md
│   ├── 02-retry-logic.md
│   ├── 03-fallback-chain.md
│   └── 04-event-emissions.md
├── 05.0-test-suite/                          ← testing
│   ├── README.md
│   ├── 01-test-config.md
│   ├── 02-test-client.md
│   ├── 03-test-router.md
│   ├── 04-mock-providers.md
│   └── 05-integration-tests.md
├── 06.0-agent-wiring/                        ← integration
│   ├── README.md
│   ├── 01-base-agent-router.md
│   ├── 02-agent-constructor-injection.md
│   ├── 03-app-composition-root.md
│   └── 04-dry-run-null-client.md
└── 07.0-documentation/                       ← documentation & milestone closeout
    ├── README.md
    ├── 01-config-reference.md
    ├── 02-router-architecture.md
    ├── 03-readme-and-changelog.md
    ├── 04-ci-configuration.md
    └── 05-milestone-closeout.md
```

## Per-task detail

_Filled in as tasks complete (mirror the 0002 status.md format: Delivered list +
test coverage summary per task)._
