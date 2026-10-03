# Task 01.0 — Router Reframing & Milestone 0003 Retirement

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §A.3 (reframe `router/`, do not delete it)
**Contracts:** C3 (router reframed as the role → harness-session binding table),
C12, C13 (no `litellm` import retained).

## Scope

This task repurposes the inert `router/` subsystem into the **role →
harness-session binding table** ADR 0006 §A.3 calls for, and formally retires the
five Milestone 0003 tasks that ADR 0006 makes permanently obsolete.

LiteLLM *dispatch* was never live (0005 C11), and with all external-model access
now behind harnesses (C1) there is no Aegis-side model routing left to do. But
`agents.yaml` + `RouterConfig` survive: for each forensic role they now declare
which harness family/persona backs it, its tool-allowlist tier, its trust tier
(C9), and its timeout. The existing `provider`/`model` fields become **advisory
metadata** documenting what the backing harness is configured with — never an
Aegis dispatch instruction. `enabled_when` presence-signal gating is kept
**verbatim** (0005 C11). Aegis SWR takes **no** runtime dependency on `litellm`;
the `router/` package continues to carry no `litellm`/`anthropic`/`openai` import
(the 0003 isolation invariant).

This task also discharges **cross-milestone conflict 1**: Milestone 0003's Tasks
03.0 (LiteLLM Client), 04.0 (Model Router), 05.0 (Test Suite), 06.0 (Agent
Wiring), 07.0 (Documentation) exist to build the dispatch path ADR 0006 declares
dead. They are marked "Superseded by ADR 0006 / Milestone 0007" in
[0003 status.md](/docs/roadmap/0003-litellm-routing/status.md), mirroring how
Milestone 0004 recorded its earlier design as superseded. Milestone 0003's Tasks
01.0–02.0 (the `agents.yaml` / `RouterConfig` config slice) are **not** obsolete —
they are what this task repurposes.

> This task does **not** build the `HarnessSession`/`HarnessSessionFactory` that
> *consumes* the binding table — that is
> [Task 03.0](/docs/roadmap/0007-harness-sole-llm-gateway/03.0-harness-session-adapter-factory/README.md).
> Task 01.0 defines the binding *data* and its validation only.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [`RouterConfig`/`AgentConfig` binding-table fields](01-router-config-binding-table.md) | ⬜ Not started | 02, 04, 03.0 |
| 02 | [`agents.yaml` role → harness-session rewrite](02-agents-yaml-binding-rewrite.md) | ⬜ Not started | 04, 03.0 |
| 03 | [Retire Milestone 0003 Tasks 03.0–07.0](03-retire-0003-dispatch-tasks.md) | ⬜ Not started | - |
| 04 | [`enabled_when` preservation + binding validation](04-enabled-when-and-validation.md) | ⬜ Not started | 03.0 |

Subtask 01 (schema) and 03 (0003 retirement, a docs-only edit) have no
interdependency and may proceed in parallel. Subtask 02 depends on 01 (it
populates the fields 01 adds); subtask 04 depends on 02 (it validates the YAML 02
writes).

## Contracts touched

- **C3** — the authoritative definition of the binding table lives in this task.
- **C13** — the `router/` package must still carry no `litellm` import; the
  isolation test from Milestone 0003 stays green.

## Key constraints

- `Optional[T]` from `typing`; `from __future__ import annotations`; RST
  docstrings; `ruff` clean (C12).
- A role stanza omitting `enabled_when` must parse unchanged — presence-signal
  gating is kept **verbatim** (0005 C11); this is a non-breaking reframe of the
  *meaning* of fields, not a parser rewrite.
- No field value in any `RouterConfig`/`AgentConfig` validation error may be a
  secret, URL, or payload — only field/role/family names (C12).

## Files created or modified by this task

```
src/aegis_swr/
├── router/
│   └── config.py          ← modified: binding-table fields (harness family/persona, tool tier, trust tier)
└── config/
    └── agents.yaml        ← modified: role → harness-session bindings (subtask 02)

docs/roadmap/0003-litellm-routing/
└── status.md              ← amended: Tasks 03.0–07.0 "Superseded by ADR 0006 / Milestone 0007" (subtask 03)

tests/unit/router/
└── test_config.py         ← extended: binding-field parsing + enabled_when parity (subtask 04)
```
