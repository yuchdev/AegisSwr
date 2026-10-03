# Milestone 0007 — Harness as the Sole LLM Gateway

**Package:** `aegis-swr` | **Module roots:** `aegis_swr/mcp/` (new); extends
`aegis_swr/harness/`, `aegis_swr/backends/ai/`, `aegis_swr/agents/`,
`aegis_swr/core/`, and `aegis_swr/router/` (all existing).
**Depends on:** Milestone 0005 (Harness & multi-backend support), **complete** —
the `CodeIntelBackend` ABC (`code_intel/backend.py`), the neutral `harness/`
selection layer (`HarnessSettings`, `create_code_intel_backend`), and all three
backend packages (`openclaude/`, `claude_code/`, `openhands/`) this milestone
extends.

This milestone implements [ADR 0006 — Harness as the sole LLM gateway](/docs/adr/0006-harness-as-sole-llm-gateway.md).
It **inverts** the reasoning substrate of Aegis SWR: the four-way split by which
the product reaches a model today — direct provider APIs
(`backends/ai/{anthropic,openai,aws_bedrock}_provider.py`), the bolted-on
`claude_cli_provider.py`, the real agentic `harness/`, and the inert
`router/` — collapses to **one gateway**. After this milestone Aegis SWR holds
**no** model API key: every path to a model goes through one of the three
Milestone-0005 harness families, each of which already owns its own
provider-credential story. The harness is promoted from a narrow read-only
code-navigation helper to **the reasoning substrate of the entire forensic
panel**, with the deterministic `consensus.py` arbitration, ADR 0002 weights, and
the one-arbiter invariant preserved byte-for-byte in contract.

Because this is a large trust escalation over a hostile, attacker-influenced
incident payload (`../CLAUDE.md` §1), the security and autonomy posture is
redesigned alongside the wiring: a single MCP redaction chokepoint (C8), a
two-trust-tier harness selector with the sandbox mandatory for payload ingestion
(C9), and a staged, opt-in autonomy ramp that never removes human escalation
(C11).

> **Scope boundary.** This milestone is the **single-process** reasoning-substrate
> change (ADR 0006 points A–E). The separable multi-instance mastermind/worker
> network subsystem ([ADR 0007](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md))
> is **out of scope** here and is not planned for — no `cluster/` package, no
> gRPC control plane, no task distribution. That is a future milestone gated on
> this one.

> **Roadmap vs ADR numbering.** This is roadmap **milestone 0007**; it implements
> **ADR 0006**. Roadmap milestone numbers and ADR numbers are independent
> sequences in this repository (ADR 0004 documents roadmap milestone 0005, not
> 0004). Roadmap milestone number 0006 is already taken by
> [0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md),
> an unrelated tooling/quality pass; this milestone takes the next free number.

---

## Background

Milestone 0005 ([ADR 0004](/docs/adr/0004-harness-composition-generalization.md))
left the codebase with the real agentic harness — `harness/` selecting exactly
one active `CodeIntelBackend` from OpenClaude / Claude Code / OpenHands —
relegated to a **side capability**: `CodeAgent.investigate()` is called from
inside a single forensic agent's turn (the code-analyst) to navigate the
product's own trusted source. Meanwhile the whole forensic debate actually runs
on **raw provider API calls** through `AIAPIBackend`:

- `Orchestrator.__init__` takes **one** shared `ai_backend: AIAPIBackend`
  (`core/orchestrator.py:81`), built once via `create_ai_backend(settings.ai)`
  (`backends/ai/__init__.py:20`).
- `agents.panel.resolve_panel(...)` (`agents/panel.py:39`) hands that **same
  instance to every agent** (`os_kernel`, `code_analyst`, `log_historian`,
  `skeptic`/arbiter) before the weighted debate in `core/consensus.py`.
- `create_ai_backend` dispatches to one of four providers
  (`anthropic` / `openai` / `bedrock` / `claude_cli`), each holding its own key.

ADR 0006's directive: stop calling OpenAI/Bedrock/Anthropic/OpenRouter directly,
hold no model API key, and make **every** model call go through a harness.

### What this milestone deliberately does *not* do

- It does **not** introduce an `AEGIS_ALLOW_DIRECT_LLM` escape hatch. A dev
  back-door to a direct provider would re-open exactly the key-holding posture
  this milestone removes (ADR 0006 §A.1, Alternatives). The `ScriptedAIBackend`
  test double (C2) covers the offline-test need without a real provider.
- It does **not** move arbitration into a harness. `consensus.py` stays a
  deterministic Aegis-side function reading **structured** per-agent Pydantic
  output (ADR 0006 §B.4, C6). A non-deterministic model arbitrating its own
  debate would void the auditable, reproducible consensus the whole design
  exists to provide.
- It does **not** take a runtime dependency on `litellm`. LiteLLM *dispatch* was
  never live (0005 C11); with all external-model access behind harnesses there is
  no Aegis-side model routing left to do (C3).
- It does **not** build Stage 2/3 autonomy *execution*. Stage 0 (Analyse) and
  Stage 1 (Suggest) scaffolding ship; Stage 2 gets an extension-point stub only;
  Stage 3 is a separate future ADR (ADR 0006 §E.9, Future scope).
- It does **not** re-configure any harness's model. Each backend's model/auth is
  the operator's concern inside that harness, exactly as 0004/0005 established.

### Two cross-milestone conflicts this milestone resolves

Both are **real, audited** inconsistencies this milestone must close so the
roadmap does not end up self-contradictory:

1. **Milestone 0003's obsolete tasks.**
   [0003 status.md](/docs/roadmap/0003-litellm-routing/status.md) shows Tasks
   03.0 (LiteLLM Client), 04.0 (Model Router), 05.0 (Test Suite), 06.0 (Agent
   Wiring), 07.0 (Documentation) as "Not started" — they exist to build real
   LiteLLM-dispatched routing. ADR 0006 §A.3 declares that path permanently
   dead. **Task 01.0** of this milestone formally retires those five rows
   (status.md marked "Superseded by ADR 0006 / Milestone 0007"), while
   **repurposing** the surviving Tasks 01.0–02.0 slice (`agents.yaml` +
   `RouterConfig`) as the role → harness-session binding table (C3).

2. **Milestone 0006's Task 05.0 depends on a dead event.**
   [0006 plan.md](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
   Task 05.0 proposes subscribing to `RouterCallCompleted` (an event of the
   never-built Model Router). **Task 10.0** of this milestone adds a short
   amendment note to that plan pointing telemetry at the per-role
   harness-session `*.completed`/adapter-completion events this milestone
   introduces instead. Milestone 0006's scope is otherwise untouched — the two
   milestones are independent.

---

## Architecture

```
AEGIS_TRUSTED_TIER_BACKEND   (trusted-source tier selector: openclaude | claude_code | openhands | unset)
AEGIS_PAYLOAD_TIER_BACKEND   (payload tier selector: openhands | unset — sandboxed only)
    │  (the 0005 AEGIS_CODE_INTEL_BACKEND is retained as an alias for the trusted-source tier; C9)
    ▼
aegis_swr/harness/                           ← EXTENDED (0005 selection layer)
    config.py      ← HarnessSettings: now resolves ONE active backend PER TRUST TIER (C9, amends 0005 C2)
    composition.py ← per-tier composition; rejects host-permission backend for the payload tier
    session.py     ← NEW: HarnessSession (per-role session) + HarnessSessionFactory (C4, C5)
    │
    │  (per-role HarnessSession, role-scoped tool allowlist, correct trust tier)
    ▼
aegis_swr/backends/ai/                        ← GUTTED to a single production adapter + a test double
    base.py                 ← _BaseAIBackend: structured-output/retry seam — RETAINED
    harness_adapter.py      ← NEW: HarnessSessionBackend — the ONLY production AIAPIBackend (C1, C4)
    scripted.py             ← NEW: ScriptedAIBackend — deterministic unit-test double (C2)
    anthropic_provider.py   ← DELETED        openai_provider.py     ← DELETED
    aws_bedrock_provider.py ← DELETED        claude_cli_provider.py ← DELETED
    __init__.py             ← create_ai_backend: constructs the harness adapter, never a network provider
    │
    ▼
aegis_swr/agents/panel.py  ← resolve_panel injects a PER-ROLE session (not one shared backend); C6
aegis_swr/core/
    orchestrator.py   ← composition passes the HarnessSessionFactory; LangGraph/AgentTurn UNCHANGED (C6)
    consensus.py      ← UNCHANGED — deterministic weighted vote over structured per-agent output (C6)
    incident_similarity.py ← UNCHANGED source of get_similar_incidents hits (C8)
    autonomy.py       ← NEW: AutonomyStage gate + opt-in flags (Stage 0 default, Stage 1 candidate patch) (C11)
    │
    ▼
aegis_swr/mcp/                                ← NEW: Aegis-as-MCP-tool-surface (the redaction chokepoint; C7, C8)
    server.py       ← MCP server scaffolding + tool registration; SensitiveFilter on every sink
    tools.py        ← get_similar_incidents, get_event_log, get_evidence_slice, analyze_incident
    redaction.py    ← the single redaction + authorization boundary (no unredacted payload byte crosses out)
```

**Hard isolation boundary (extends 0005 C3 / C13):** after this milestone no
module under `src/aegis_swr/` imports `anthropic`, `openai`, or `boto3`
(bedrock), and no module imports `claude_cli_provider`. The sole production
`AIAPIBackend` is the harness adapter; keys live only inside the chosen harness,
per its own contract. Enforced by an extended `grep` CI check (C13, Task 10.0).

**Redaction boundary:** no incident byte crosses into a harness except through
the pushed pre-redacted summary (C7) or an MCP tool response redacted at the
`aegis_swr/mcp/redaction.py` boundary (C8). `SensitiveFilter` covers every new
sink.

---

## Tasks

| Task | Name                                           | Category       | Output                                                                                                                                                                 |
|------|------------------------------------------------|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 01.0 | Router Reframing & Milestone 0003 Retirement   | configuration  | `router/` + `agents.yaml` reframed as the role → harness-session binding table (C3); Milestone 0003 Tasks 03.0–07.0 formally retired in its `status.md` (ADR §A.3)   |
| 02.0 | Direct-Provider Removal & `ScriptedAIBackend`  | infrastructure | Delete the three network providers + `claude_cli_provider.py`; retire `create_ai_backend` network branches; `ScriptedAIBackend` double; no `AEGIS_ALLOW_DIRECT_LLM` (ADR §A.1, A.2; C1, C2, C13) |
| 03.0 | Harness Session Adapter & Factory              | infrastructure | `harness/session.py` (`HarnessSession`, `HarnessSessionFactory`) + `backends/ai/harness_adapter.py` (`HarnessSessionBackend`) (ADR §B.5; C4, C5)                     |
| 04.0 | Panel Rewiring onto Per-Role Sessions          | integration    | `resolve_panel`/`Orchestrator` onto per-role sessions; consensus/weights/one-arbiter parity proof; token lineage (ADR §B.4; C6, C10)                                 |
| 05.0 | Aegis MCP Tool Surface (redaction chokepoint)  | infrastructure | `aegis_swr/mcp/` — four tools wired to `incident_similarity.py`; the single redaction + authz boundary; `security-auditor` gate (ADR §C.6, C.7; C7, C8)              |
| 06.0 | Trust-Tier Harness Selection                   | configuration  | `HarnessSettings` generalised to one active backend **per trust tier**; payload tier → sandboxed mandatory; the deliberate 0005 C2 amendment (ADR §D.8; C9)          |
| 07.0 | Staged Autonomy Scaffolding (Stage 0/1)        | infrastructure | `core/autonomy.py` capability-tier gate; Stage 1 candidate-patch output on `RCAReport`; opt-in flags; Stage 2 extension-point stub (ADR §E.9; C11)                   |
| 08.0 | Test Suite — Unit                              | testing        | Grep/import-ban, no-key boot, panel parity, trust-tier enforcement, redaction, stage-gate suites (ADR Validation/Rollout)                                             |
| 09.0 | Test Suite — Integration                       | testing        | Live per-role harness panel, live MCP round-trip, end-to-end no-key investigation; skipped without presence signals/Docker                                            |
| 10.0 | Documentation & CI                             | documentation  | Config-reference + migration docs; CI gates; `docs/README.md`/roadmap sync; the two cross-milestone amendment notes; milestone closeout                               |

**Sequencing.** 01.0 and 02.0 are the foundation (reframe the binding table;
delete the old reasoning paths and stand up the test double) and can proceed in
parallel. 03.0 depends on 01.0 (binding table) and 02.0 (the retained
`_BaseAIBackend` seam + `ScriptedAIBackend`). 06.0 (trust tiers) depends on 03.0
(sessions are tier-scoped). 04.0 depends on 03.0 and 06.0 (per-role sessions at
the right tier). 05.0 (MCP surface) depends on 02.0 and can proceed alongside
03.0/04.0; it is a `security-auditor` gate item (ADR Links). 07.0 (autonomy)
depends on 04.0 (the panel must produce an `RCAReport` through sessions before a
candidate-patch stage can attach to it) and 06.0 (execution tier = payload tier).
08.0 and 09.0 are written **incrementally alongside** their implementation tasks
(the 0004/0005 convention). 10.0 closes the milestone.

---

## What ADR 0006 changes in the 0005 contracts (explicit)

Mirrors ADR 0006 → *Consequences → what 0005 conventions change*. Carried here so
each task README can reference a single authoritative list.

| 0005 contract | Change in this milestone | Owning task |
|---------------|--------------------------|-------------|
| **0005 C2** (single active backend) | Generalises to **one active backend per trust tier** (payload vs trusted-source), payload tier constrained to sandboxed backends; loud-ambiguity preserved **per tier**. The lone deliberate amendment. | 06.0 (C9) |
| **0005 C11** (`agents.yaml` roles inert routing config) | **Reframed** to the role → harness-session binding table; `enabled_when` gating unchanged. | 01.0 (C3) |
| **0004 C5 / 0005 C9** (token accounting via `CodeResult.token_estimate`) | **Reused unchanged** for per-role sessions; the panel's cost accounting now flows through the same field. | 04.0 (C10) |
| **0005 C3/C13** (module isolation, SensitiveFilter) | **Extended**: adds the no-`anthropic`/`openai`/`boto3`/`claude_cli_provider` import bans and the MCP-server isolation + redaction boundary. | 02.0 / 05.0 (C13, C8) |

---

## Reasoning-path comparison (before → after)

| Path to a model (today) | Status after this milestone | Replacement |
|-------------------------|-----------------------------|-------------|
| `anthropic_provider.py` (direct API, holds `ANTHROPIC_API_KEY`) | **Deleted** | Harness adapter → chosen harness (holds its own creds) |
| `openai_provider.py` (direct API, holds `OPENAI_API_KEY`) | **Deleted** | Harness adapter → chosen harness |
| `aws_bedrock_provider.py` (direct API, holds AWS creds) | **Deleted** | Harness adapter → chosen harness |
| `claude_cli_provider.py` (one-shot `claude`, agentic loop stripped, reaches into `claude_code.process` internals) | **Deleted** | No-tools persona of the `claude_code` backend (`allowed_tools=""`) |
| `router/` (`RouterConfig`, `agents.yaml`; inert, "not routed through LiteLLM") | **Reframed, kept** | Role → harness-session binding table (advisory `provider`/`model`) |
| `harness/` + `code_intel/` (narrow read-only code-nav sub-call) | **Promoted** | The reasoning substrate of the whole panel (per-role sessions) |

---

## Shared contracts (authoritative)

These contracts are defined once here; per-task READMEs reference them by number.
`_BaseAIBackend` / `AIAPIBackend` refer to the shapes actually shipped in
`src/aegis_swr/backends/ai/base.py` and `src/aegis_swr/backends/base.py`.

### C1 — Harness is the sole LLM gateway

Aegis SWR holds **no** model API key. The `AIAPIBackend` ABC
(`backends/base.py:22`) and its `_BaseAIBackend` structured-output/retry seam
(`backends/ai/base.py`) are **retained** as the internal reasoning seam so
`Orchestrator`/`resolve_panel` keep a stable injection type. Its **only
production implementation** becomes `HarnessSessionBackend`
(`backends/ai/harness_adapter.py`, C4). `create_ai_backend`
(`backends/ai/__init__.py`) constructs that adapter and **never** a network
provider. No `AEGIS_ALLOW_DIRECT_LLM` or any other escape hatch is introduced.

### C2 — `ScriptedAIBackend` deterministic double

A single deterministic `ScriptedAIBackend` (`backends/ai/scripted.py`) subclasses
`_BaseAIBackend` (so it inherits the exact `generate()`/token-accounting /
one-retry-correction semantics) and fulfils `_invoke()` from a pre-seeded script
of `(matcher → response)` entries rather than any network call. It is **test-only**
— never selectable in a production composition path — and replaces the unit
coverage the deleted network providers carried. It needs no API key and reaches
no provider. Tests seed it with structured JSON matching each agent's
`output_schema` so the panel's deterministic arbitration can be exercised
end-to-end offline (C6).

### C3 — Router reframed as the role → harness-session binding table (reframes 0005 C11)

`agents.yaml` + `RouterConfig` survive, repurposed. For each forensic role the
stanza now declares **which harness family/persona backs it**, its **tool-allowlist
tier** (`read_only_context` for investigators + skeptic, `code_navigation` for
`code_analyst`), its **trust tier** (`payload` vs `trusted_source`, C9), and its
**timeout**. The `provider`/`model` fields become **advisory metadata** documenting
what the backing harness is configured with — never an Aegis dispatch
instruction. `enabled_when` presence-signal gating is kept **verbatim** (0005 C11).
Aegis SWR takes **no** runtime dependency on `litellm`; the `router/` package
carries no `litellm`/`anthropic`/`openai` import (the 0003 isolation invariant
holds). Milestone 0003's Tasks 03.0–07.0 (LiteLLM client, Model Router, router
tests, agent wiring, docs) are formally retired as superseded.

### C4 — `HarnessSession` + `HarnessSessionBackend` adapter

`HarnessSession` (`harness/session.py`) is a per-role object wrapping a
Milestone-0005 `CodeIntelBackend` plus the role's binding (tool tier, trust tier,
timeout). `HarnessSessionBackend` (`backends/ai/harness_adapter.py`) implements
the retained `AIAPIBackend.generate(system_prompt, messages, output_schema)
-> BaseModel | str` seam but fulfils it by delegating to a `HarnessSession`:

1. It folds `system_prompt` + `messages` into a single bounded **task** string
   (the role's seeded question + the pushed pre-redacted summary, C7) and calls
   the session's `delegate(task, ctx) -> CodeResult`.
2. It parses the session's structured `CodeResult.content` back into
   `output_schema`, **reusing** `_BaseAIBackend`'s one-retry structured-output
   correction path (`backends/ai/base.py:76-91`) verbatim — the adapter supplies
   `_invoke()`; the validation/retry logic is inherited, unchanged.
3. Token usage is taken from `CodeResult.token_estimate` (C10), surfaced through
   the existing `last_usage` accounting so the panel's token tracker is unchanged.

This keeps `Orchestrator`/`resolve_panel` structurally intact — the change is
*what the backend is*, not *how the panel is driven*.

### C5 — `HarnessSessionFactory` (per-role sessions, role-scoped allowlist)

`HarnessSessionFactory` (`harness/session.py`) is owned by `harness/` and built
at the composition root. Given a role's binding (C3) it returns a
`HarnessSessionBackend` bound to a `HarnessSession` carrying a **role-scoped tool
allowlist**: investigators (`os_kernel`, `log_historian`) and the skeptic/arbiter
get a **read-only context** session; `code_analyst` keeps a **code-navigation-tool**
session (its existing `CodeAgent.investigate()` posture). The factory selects the
backend at the role's **trust tier** (C9) — investigator/arbiter payload-reasoning
roles resolve to a payload-tier (sandboxed) session; the `code_analyst`
trusted-source navigation may resolve to a host-permission session. The factory
is the one place a role is bound to a concrete session; it is injected into
`Orchestrator`, not imported by it.

### C6 — Deterministic Aegis-side arbitration invariant (unchanged)

The multi-agent LangGraph (`core/orchestrator.py`), the per-agent `default_weight`
(ADR 0002; `agents/panel.py:resolve_consensus_weights`), the `AgentTurn`/event
accounting, the **exactly-one-ARBITER** panel invariant
(`agents/panel.py:resolve_panel`), and the weighted-vote arbitration in
`core/consensus.py` are **unchanged**. Arbitration stays a deterministic
Aegis-side function reading the **structured** per-agent Pydantic output
(`Hypothesis` / `SkepticVerdict`) from each session. Arbitration is **never**
moved into a harness. Parity is proven under a `ScriptedAIBackend`-equivalent
harness double producing identical structured output (Task 08.0, 04.0).

### C7 — Hybrid context exchange (bounded push + on-demand pull)

Aegis pushes a **bounded, pre-redacted incident summary** into each session's
initial task context, and additionally exposes itself as the MCP tool surface
(C8) from which a session pulls deeper detail on demand. Neither pure-push
(exceeds context windows; forwards unredacted hostile payload wholesale) nor
pure-tool-exposure (round-trip latency; no first-turn grounding) alone is used.
The pushed summary is the `IncidentBrief`/`HistoryAnalysis.as_context()` already
produced in-pipeline, passed through the C8 redaction boundary before it reaches
any session.

### C8 — MCP tool surface is the single redaction chokepoint

`aegis_swr/mcp/` exposes exactly four tools — `get_similar_incidents`,
`get_event_log`, `get_evidence_slice`, `analyze_incident` — as the **only** way an
incident byte crosses into a harness other than the pushed pre-redacted summary.
Every tool response is **redacted at the tool boundary** (`mcp/redaction.py`),
`SensitiveFilter`-covered, and authorization-checked. `get_similar_incidents` is
served by `core/incident_similarity.py` and returns **redacted structured hits**
(`HistoryMatch.as_dict()`-shaped), never raw prior payloads. Raw dump/log/stack
text is never forwarded unredacted, never logged, never persisted unredacted.
Standing up this MCP server is a new surface and a `security-auditor` gate item
(ADR Links). `analyze_incident` is a **payload-tier** tool (C9) and must run only
on a sandboxed backend.

### C9 — Trust-tier harness selection (amends 0005 C2)

0005 C2's "one active backend" generalises to **one active backend per trust
tier**:

- **Payload tier** — any session ingesting raw/attacker-influenced incident
  payload (the investigator/arbiter reasoning roles, `analyze_incident`). **MUST
  be a Docker-sandboxed backend → OpenHands.** Host-permission backends
  (Claude Code, OpenClaude) are **rejected at composition time** for this tier
  (`HarnessConfigError`-equivalent).
- **Trusted-source tier** — sessions touching only the product's own trusted
  source (the `code_analyst` `CodeAgent` use). **May** use a host-permission
  backend, exactly as today.

The loud-ambiguity discipline of 0005 C2 is preserved **per tier**.
`AEGIS_CODE_INTEL_BACKEND` alone is no longer sufficient to express selection; a
tier-aware selector is added (`AEGIS_PAYLOAD_TIER_BACKEND` +
`AEGIS_TRUSTED_TIER_BACKEND`, with `AEGIS_CODE_INTEL_BACKEND` retained as an alias
for the trusted-source tier for backward compatibility — see the naming note in
Task 06.0 subtask 01). `HarnessSettings` resolves each tier independently at
construction time.

### C10 — Token accounting via `CodeResult.token_estimate` (reuses 0004 C5 / 0005 C9)

The panel's per-role cost accounting flows through the unchanged
`CodeResult.token_estimate` field (`int`), surfaced by the adapter (C4) into the
existing `_BaseAIBackend.last_usage` / orchestrator `token_tracker`
(`core/orchestrator.py:_fold_turn`). Claude Code's real `usage` counts and
OpenHands'/OpenClaude's boundary estimates both arrive through that one field, so
`RCAReport.total_input_tokens`/`total_output_tokens` keep their meaning with no
schema change.

### C11 — Staged autonomy gate (four stages; Stage 0 default)

`core/autonomy.py` defines an `AutonomyStage` enum and a per-deployment opt-in
gate. Default posture is **Stage 0 (Analyse)**, read-only, producing
`RCAReport`/`HITLRequest` exactly as today. Each higher stage is a per-deployment
explicit opt-in, never the default, adding exactly one capability tier:

| Stage | Capability | Output | Gate (cumulative) | In this milestone |
|-------|-----------|--------|-------------------|-------------------|
| 0 Analyse | read-only | `RCAReport` / `HITLRequest` | baseline | **built (default)** |
| 1 Suggest | + write-to-sandbox-scratch | RCAReport **+ candidate patch/playbook** (never executed) | human review | **built (opt-in)** |
| 2 Execute-validated | execute in sandbox, non-prod | validated run + result | `/playbook-validate`; `HITLRequest`; `incident-analyst` | **extension-point stub only** |
| 3 Autonomous (allowlisted `FaultClass`) | execute for a narrow pre-approved `FaultClass` allowlist | auto-remediation + audit | all of Stage 2 + standing HITL + `security-auditor` CRITICAL-blocks-merge | **future ADR; not built** |

Non-negotiable across all stages: `HITLRequest` escalation stays reachable at
every tier; any stage transition is an `incident-analyst` lifecycle change; any
capability escalation requires a `security-auditor` pass that CRITICAL-blocks
merge; execution only ever happens inside the sandboxed (OpenHands) runtime (C9).
No stage removes a human's ability to intervene. Stage 1's candidate patch is a
new optional field on `RCAReport` carrying the proposed patch/playbook text and a
`never_executed` marker; Stage 2's stub is a documented hook where
`/playbook-validate` will attach, with **no execution path wired**.

### C12 — Cross-cutting conventions (inherited verbatim from 0001–0005)

- `Optional[T]` from `typing`, never `T | None` (including subscripts /
  `Annotated[...]`).
- `from __future__ import annotations` in every new file.
- `ruff` (E,F,I,UP,B,SIM; line length 100) clean; `ruff format` is the formatter.
- Every new public class/function has an RST-style docstring
  (`:param:`/`:ivar:`/`:return:`).
- Loguru with `SensitiveFilter` on **every** sink; no raw incident payload text
  (dump/log/stack), no secret/credential, and no unredacted model prompt/response
  ever reaches a log sink or exception message.
- `asyncio.sleep` for backoff — never `time.sleep`.
- No bare `except:`; every external call (harness session, MCP transport) has a
  timeout and a defined failure path; RAII via context managers for every
  subprocess/socket/file resource.

### C13 — Module isolation & import bans (extends 0005 C3/C13)

- No module under `src/aegis_swr/` imports `anthropic`, `openai`, or `boto3`
  (bedrock); no module imports `aegis_swr.backends.ai.claude_cli_provider`
  (deleted). Grep-enforced (Task 10.0), with a self-test proving the guard turns
  red on a re-introduced import.
- `create_ai_backend` constructs only the harness adapter (C1); it branches on no
  provider name.
- `aegis_swr/mcp/` is the only package exposing Aegis capabilities as MCP tools;
  `core/`, `views/`, and `code_intel/` import no `mcp` server module. The MCP
  redaction boundary (`mcp/redaction.py`) is the sole egress path for incident
  content into a tool response.
- The `router/` package continues to carry no `litellm` import (0003 invariant).

---

## Dependency graph

```
Task 01.0 (Router Reframing + 0003 Retirement)      Task 02.0 (Provider Removal + ScriptedAIBackend)
        │  (role → harness-session binding table)            │  (retained _BaseAIBackend seam + double)
        └───────────────────────┬────────────────────────────┘
                                ▼
                 Task 03.0 (Harness Session Adapter & Factory)
                                │
                ┌───────────────┴───────────────┐
                ▼                                ▼
     Task 06.0 (Trust-Tier Selection)   Task 05.0 (Aegis MCP Tool Surface) ← security-auditor gate
                │                                │
                ▼                                │
     Task 04.0 (Panel Rewiring) ◄───────────────┘  (per-role sessions at the right tier; hybrid context)
                │
                ▼
     Task 07.0 (Staged Autonomy Scaffolding: Stage 0/1)
                │
     Tasks 01–07 ┤
                 ├──► Task 08.0 (Unit Tests)        ← incremental
                 ├──► Task 09.0 (Integration Tests) ← incremental
                 └──► Task 10.0 (Docs & CI + cross-milestone amendments)
```

**Minimum viable:** 01.0 → 02.0 → 03.0 → 04.0 → 08.0 (unit) — a no-key panel
driven by per-role harness sessions with deterministic consensus preserved, the
`ScriptedAIBackend` double covering offline tests, trusted-source tier only.
**Full milestone:** all ten tasks including trust tiers, the MCP redaction
surface, Stage 0/1 autonomy, integration tests, and documentation.

---

## File map (target state after milestone)

```
src/aegis_swr/
├── config/
│   ├── settings.py          ← updated: AISettings loses provider-key fields; trust-tier selectors added (C9)
│   └── agents.yaml          ← reframed: role → harness-session binding table (C3)
├── router/
│   └── config.py            ← reframed: binding-table fields (harness family/persona, tool tier, trust tier); enabled_when kept
├── backends/
│   ├── base.py              ← UNCHANGED (AIAPIBackend ABC retained as the seam; C1)
│   └── ai/
│       ├── __init__.py      ← create_ai_backend builds the harness adapter only (C1, C13)
│       ├── base.py          ← UNCHANGED (_BaseAIBackend structured-output/retry seam; C2, C4)
│       ├── harness_adapter.py ← NEW: HarnessSessionBackend — the sole production AIAPIBackend (C4)
│       ├── scripted.py      ← NEW: ScriptedAIBackend — deterministic unit-test double (C2)
│       ├── anthropic_provider.py    ← DELETED (C13)
│       ├── openai_provider.py       ← DELETED (C13)
│       ├── aws_bedrock_provider.py  ← DELETED (C13)
│       └── claude_cli_provider.py   ← DELETED (re-expressed as no-tools claude_code persona; C13)
├── harness/
│   ├── config.py            ← updated: one active backend per trust tier (C9; amends 0005 C2)
│   ├── composition.py       ← updated: per-tier composition; payload tier rejects host-permission
│   └── session.py           ← NEW: HarnessSession + HarnessSessionFactory (C4, C5)
├── agents/
│   └── panel.py             ← updated: resolve_panel injects a per-role session (C6)
├── core/
│   ├── orchestrator.py      ← updated: composition passes HarnessSessionFactory; graph UNCHANGED (C6)
│   ├── consensus.py         ← UNCHANGED (C6)
│   ├── incident_similarity.py ← UNCHANGED (feeds get_similar_incidents; C8)
│   ├── schemas.py           ← updated: optional candidate-patch field on RCAReport (Stage 1; C11)
│   └── autonomy.py          ← NEW: AutonomyStage gate + opt-in flags (C11)
└── mcp/                      ← NEW PACKAGE (the redaction chokepoint; C7, C8)
    ├── __init__.py
    ├── server.py            ← MCP server scaffolding + tool registration; SensitiveFilter
    ├── tools.py             ← get_similar_incidents / get_event_log / get_evidence_slice / analyze_incident
    └── redaction.py         ← the single redaction + authorization boundary

tests/
├── unit/
│   ├── backends/ai/         ← test_harness_adapter.py, test_scripted.py, test_import_bans.py (C13)
│   ├── harness/             ← test_session.py, test_trust_tier.py (C9), test_composition_tier.py
│   ├── agents/              ← test_panel_parity.py (C6)
│   ├── mcp/                 ← test_tools.py, test_redaction.py (C8)
│   ├── core/                ← test_autonomy.py (C11)
│   └── test_no_key_boot.py  ← dry-run analyze with no API keys set
└── integration/
    └── harness_gateway/     ← live per-role panel (OpenHands), live MCP round-trip, e2e no-key; skipped without signals/Docker

docs/
├── config/
│   ├── harness-selection.md        ← updated: the two trust tiers + per-tier selection truth table (C9)
│   ├── harness-gateway.md          ← NEW: the sole-gateway posture, no-key boot, the role→session binding table (C1, C3)
│   ├── mcp-tool-surface.md         ← NEW: the four tools, redaction boundary, authz (C8)
│   └── autonomy-stages.md          ← NEW: the four-stage ramp, opt-in flags, gates (C11)
└── security/
    └── 2026-10-DD-aegis-mcp-tool-surface.md  ← NEW: security-auditor threat model (C8)

docs/roadmap/0003-litellm-routing/status.md   ← amended: Tasks 03.0–07.0 "Superseded by ADR 0006 / Milestone 0007" (Task 01.0)
docs/roadmap/0006-improvements-and-optimizations/plan.md ← amended: Task 05.0 telemetry note (Task 10.0)
docs/roadmap/README.md                        ← updated: Milestones table row + footnote
docs/README.md                                ← updated: roadmap table row
```

---

## Global acceptance criteria

- [ ] **Grep/CI:** no `import anthropic`, `import openai`, or `import boto3`
      anywhere in `src/aegis_swr/`; no module imports `claude_cli_provider`;
      `create_ai_backend` constructs no network provider (C1, C13).
- [ ] **No-key boot:** the full `aegis analyze` dry-run path completes with **no**
      `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/AWS creds in the environment; keys live
      only inside the chosen harness (ADR Validation).
- [ ] `anthropic_provider.py`, `openai_provider.py`, `aws_bedrock_provider.py`,
      and `claude_cli_provider.py` are deleted; `ClaudeCliSettings` is removed;
      the "LLM-only Claude Code" case is a no-tools (`allowed_tools=""`)
      `claude_code` persona (C13, Task 02.0).
- [ ] The retained `AIAPIBackend` ABC and `_BaseAIBackend` seam are unchanged;
      the sole production implementation is `HarnessSessionBackend` (C1, C4).
- [ ] `ScriptedAIBackend` is test-only, reaches no provider, needs no key, and
      covers the prior network-provider unit coverage (C2).
- [ ] **Panel parity:** `resolve_panel` injects a per-role session; the LangGraph,
      ADR 0002 weights, the one-arbiter invariant, and deterministic
      `consensus.py` output are unchanged under a harness double (C6).
- [ ] **Trust-tier enforcement:** composition **rejects** a host-permission
      backend for a payload-tier session and accepts only a sandboxed one;
      trusted-source tier still accepts host-permission backends; loud-ambiguity
      preserved per tier (C9).
- [ ] **Redaction:** no raw dump/log/stack text reaches any harness context, log
      sink, MCP tool response, or persisted report unredacted — asserted with a
      hostile fixture payload carrying seeded secrets/PII (C7, C8).
- [ ] The four MCP tools are the only incident-content egress into a harness other
      than the pushed pre-redacted summary; `get_similar_incidents` returns
      redacted structured hits from `incident_similarity.py`, never raw priors (C8).
- [ ] **Autonomy gating:** Stages 1–3 are off by default; each requires explicit
      opt-in; `HITLRequest` escalation is reachable in every stage; execution
      occurs only inside the sandboxed runtime; `/playbook-validate` precedes any
      Stage-2+ run (stub only — no execution path is wired) (C11).
- [ ] `agents.yaml`/`RouterConfig` are reframed as the role → harness-session
      binding table; `enabled_when` gating is unchanged; no `litellm` import (C3).
- [ ] Milestone 0003's `status.md` marks Tasks 03.0–07.0 "Superseded by ADR 0006 /
      Milestone 0007"; Milestone 0006's `plan.md` Task 05.0 carries the dead-event
      amendment note (Tasks 01.0, 10.0).
- [ ] Token accounting flows through `CodeResult.token_estimate` into the existing
      `token_tracker`; `RCAReport` token totals keep their meaning (C10).
- [ ] No raw incident payload, secret, or unredacted model prompt/response reaches
      any log sink; `SensitiveFilter` covers every new sink (C12).
- [ ] All new public classes/functions have RST docstrings; `Optional[T]` not
      `T | None`; `from __future__ import annotations` present (C12).
- [ ] `ruff` clean; coverage ≥90% on the harness adapter and the MCP tool surface;
      100% branch on the trust-tier selection and the autonomy-stage gate (ADR
      Coverage).
