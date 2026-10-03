# Milestone 0007 — Harness as the Sole LLM Gateway — Status

Tracks progress against [plan.md](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md).
Updated as each task lands. Implements [ADR 0006](/docs/adr/0006-harness-as-sole-llm-gateway.md)
(Proposed — this roadmap drafts the implementation plan for review alongside it;
no `src/` code is written until the ADR is Accepted).

## Current status

| Task | Name                                           | Status        | Tests |
|------|------------------------------------------------|---------------|-------|
| 01.0 | Router Reframing & Milestone 0003 Retirement   | ⬜ Not started | -     |
| 02.0 | Direct-Provider Removal & `ScriptedAIBackend`  | ⬜ Not started | -     |
| 03.0 | Harness Session Adapter & Factory              | ⬜ Not started | -     |
| 04.0 | Panel Rewiring onto Per-Role Sessions          | ⬜ Not started | -     |
| 05.0 | Aegis MCP Tool Surface (redaction chokepoint)  | ⬜ Not started | -     |
| 06.0 | Trust-Tier Harness Selection                   | ⬜ Not started | -     |
| 07.0 | Staged Autonomy Scaffolding (Stage 0/1)        | ⬜ Not started | -     |
| 08.0 | Test Suite — Unit                              | ⬜ Not started | -     |
| 09.0 | Test Suite — Integration                       | ⬜ Not started | -     |
| 10.0 | Documentation & CI                             | ⬜ Not started | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** **not started** (opened 2026-10-03). This milestone is a
full task → subtask decomposition of ADR 0006's single-process reasoning-substrate
change (points A–E). ADR 0006 is **Proposed**: these specs are the implementation
roadmap drafted for review alongside it. No `src/` or `tests/` code is written in
this planning pass; hand implementation to `python-expert` and tests to
`testing-expert` once the ADR is Accepted.

## Notes & decisions

- **Depends on Milestone 0005 (complete).** This milestone extends — does not
  supersede — the `harness/` selection layer, the `CodeIntelBackend` ABC, and the
  three backend packages. `code_intel/backend.py`, `agent.py`, and `budget.py`
  stay backend-agnostic and untouched; `CodeResult.token_estimate` keeps its name
  and `int` type (C10).
- **Supersedes Milestone 0003's dispatch tasks.** ADR 0006 §A.3 makes LiteLLM
  dispatch permanently dead. Task 01.0 marks Milestone 0003 Tasks 03.0–07.0
  "Superseded by ADR 0006 / Milestone 0007" in that milestone's `status.md`
  (mirroring how Milestone 0004 recorded the earlier code-intelligence-layer
  design as superseded). Milestone 0003's Tasks 01.0–02.0 (the `agents.yaml` /
  `RouterConfig` config slice) are **not** obsolete — they survive, repurposed as
  the role → harness-session binding table (C3).
- **Independent of Milestone 0006.** Task 10.0 adds a one/two-sentence amendment
  note to Milestone 0006's `plan.md` Task 05.0 (point telemetry at the per-role
  harness-session `*.completed`/adapter-completion events this milestone
  introduces, not the never-built `RouterCallCompleted`). Milestone 0006's scope
  is otherwise untouched; the two milestones are independent.
- **Out of scope:** the multi-instance mastermind/worker network
  ([ADR 0007](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md)) and
  Stage 2/3 autonomy *execution* (Stage 2 gets an extension-point stub only;
  Stage 3 is a separate future ADR).

## Open items flagged during decomposition

These are genuine planning-level ambiguities surfaced from ADR 0006, recorded
here (not silently guessed past). Each is called out inline in the owning
subtask spec and should be settled with the user / `security-auditor` before the
owning task is implemented:

1. **Session statefulness vs per-turn re-delegation (Task 03.0).** ADR §B.5
   specifies `AIAPIBackend.generate(system_prompt, messages, ...)` fulfilled by a
   harness session, but a `CodeIntelBackend.delegate(task, ctx)` is one-shot. Whether
   a role's `HarnessSession` is a long-lived stateful session carried across debate
   rounds, or re-delegated per turn with the growing `messages` list folded into
   each task string, is **not specified** by the ADR and materially affects token
   cost and context handling. Task 03.0 subtask 01 proposes per-turn re-delegation
   with the bounded-summary + prior-turn digest folded into the task (cheapest,
   most auditable), and flags the alternative for confirmation.
2. **MCP authorization model (Task 05.0).** ADR §C.7 requires the tool surface be
   "authorization-checked" but does not specify the authz scheme (caller identity,
   token issuance, scope). Task 05.0 subtask 05 proposes a per-session capability
   token minted by the composition root and flags the concrete scheme for the
   `security-auditor` gate; a durable cross-process token scheme is deferred to
   ADR 0007's worker-token design.
3. **Trust-tier selector env-var naming (Task 06.0).** ADR §D.8 says
   `AEGIS_CODE_INTEL_BACKEND` alone is "no longer sufficient" and must be
   "complemented by a tier-aware selector (named in task breakdown below)" but the
   ADR does not actually name it. Task 06.0 subtask 01 proposes
   `AEGIS_PAYLOAD_TIER_BACKEND` + `AEGIS_TRUSTED_TIER_BACKEND`, retaining
   `AEGIS_CODE_INTEL_BACKEND` as a backward-compatible alias for the trusted-source
   tier, and flags the naming for confirmation.
4. **`analyze_incident` recursion risk (Task 05.0).** ADR §C.6 lists
   `analyze_incident` among the MCP tools (the Topology-C inversion), but in this
   single-process ADR the panel *is* the analysis. Whether `analyze_incident` is
   exposed in-process (risking a session → analyze_incident → panel-of-sessions
   regress) or only to an external orchestrator is **unclear**. Task 05.0 subtask
   04 proposes gating `analyze_incident` behind an explicit "external-orchestrator"
   opt-in and rejecting re-entrant invocation, and flags it for the security gate.

## Decomposition tree (as planned)

The milestone is decomposed to the **full subtask level**: 10 tasks, each with a
`README.md` (scope, linked subtask table, contracts touched, constraints) and its
numbered subtask spec files (44 total). 56 roadmap Markdown files including this
`status.md` and `plan.md`.

```
docs/roadmap/0007-harness-sole-llm-gateway/
├── plan.md                                        ← milestone spec (tasks, contracts C1–C13)
├── status.md                                      ← this tracker
├── 01.0-router-reframing-0003-retirement/  (4)    ← configuration
├── 02.0-provider-removal-scripted-backend/ (4)    ← infrastructure
├── 03.0-harness-session-adapter-factory/   (4)    ← infrastructure
├── 04.0-panel-rewiring-per-role-sessions/  (4)    ← integration
├── 05.0-aegis-mcp-tool-surface/            (5)    ← infrastructure (security gate)
├── 06.0-trust-tier-harness-selection/      (4)    ← configuration
├── 07.0-staged-autonomy-scaffolding/       (4)    ← infrastructure
├── 08.0-test-suite-unit/                   (6)    ← testing (unit)
├── 09.0-test-suite-integration/            (4)    ← testing (integration)
└── 10.0-documentation-ci/                  (5)    ← documentation & milestone closeout
```

## Per-task detail

_Filled in as tasks complete (mirror the 0004 status.md format: Delivered list +
key decisions + test coverage per task)._
