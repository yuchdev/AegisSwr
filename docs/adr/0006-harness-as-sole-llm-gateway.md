# 0006 - Harness as the sole LLM gateway: forensic panel, context exchange, and staged autonomy

> **Status:** Proposed
>
> **Date:** 2026-10-03
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

Milestones 0004 and 0005 built an agentic-harness subsystem ([ADR 0003](/docs/adr/0003-code-intel-composition-root.md),
[ADR 0004](/docs/adr/0004-harness-composition-generalization.md)): a neutral
`harness/` selection layer picking exactly one active `CodeIntelBackend` from
three families — **OpenClaude** (gRPC sidecar, host permissions),
**Claude Code** (one-shot `claude` subprocess, host permissions, real token
accounting), **OpenHands** (REST/WS sidecar, **Docker-sandboxed by default**).
That subsystem was deliberately scoped as a **narrow, read-only code-navigation
helper**: `CodeAgent.investigate()` is called from inside a single forensic
agent's turn (the code-analyst) to navigate the product's own trusted source.

In parallel, and predating that work, Aegis SWR still reaches a model **three
other ways**, and the result is a four-way mess that this ADR exists to collapse:

1. **`backends/ai/{anthropic,openai,aws_bedrock}_provider.py`** — a
   Factory-Strategy family of plain LLM providers behind `AIAPIBackend`
   (`backends/ai/base.py`), each making direct provider API calls with its own
   key, selected by `AISettings.provider` via `create_ai_backend()`. **This is
   what actually drives the entire forensic debate today.**
2. **`backends/ai/claude_cli_provider.py`** (`ClaudeCliBackend`) — a fourth
   provider bolted into that same family that spawns a one-shot `claude` CLI with
   the agentic loop *deliberately disabled* (`--allowedTools ""`), authenticated
   by the operator's local Claude Code login, and which **reaches into
   `aegis_swr.claude_code.process` internals** (`_extract_assistant_text`,
   `_extract_usage`). The same `claude` binary is thus wired in twice, through
   two incompatible abstractions (`ClaudeCliSettings` vs `ClaudeCodeSettings`),
   with two auth stories and two capability postures.
3. **`harness/` + `claude_code/` + `openclaude/` + `openhands/`** — the real
   agentic harness, but used only as the narrow sub-call described above.
4. **`router/`** (`RouterConfig`, `agents.yaml`) — an inert per-role
   provider/model/timeout declaration layer that, per 0005 C11, "is not routed
   through LiteLLM"; today it does nothing but gate validation via `enabled_when`.

The core orchestration makes the coupling concrete. `Orchestrator.__init__`
takes **one** shared `ai_backend: AIAPIBackend` (built once via
`create_ai_backend(settings.ai)`); `agents.panel.resolve_panel(...)` hands that
**same instance to every agent** (`os_kernel`, `code_analyst`, `log_historian`,
`skeptic`/arbiter) before the weighted debate in `core/consensus.py`. So the
whole forensic investigation runs on raw provider API calls, while the real
agentic harness — the thing with tool access, sandboxing, and real token
accounting — is relegated to a side capability.

The user's directive is to **invert this**: Aegis SWR must stop calling
OpenAI/Bedrock/Anthropic/OpenRouter directly and stop holding any model API key.
**Every path to a model must go through one of the three harnesses**, each of
which already owns its own provider-credential story (Claude Code's auth modes
per 0005 C7; OpenClaude's operator OpenAI-compatible endpoint; OpenHands'
LiteLLM-internal config). The harness is promoted from a code-navigation helper
to **the reasoning substrate of the entire forensic panel**, and ultimately the
executor of remediation. This is a large trust escalation over a hostile,
attacker-influenced incident payload (`../CLAUDE.md` §1), so the security and
autonomy posture must be redesigned alongside the wiring.

This ADR covers the single-process reasoning-substrate change (points A–E
below). The separable multi-instance mastermind/worker network subsystem is
specified in its own record, [ADR 0007](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md)
— see *Why two ADRs*.

### Why two ADRs

Points A–E are one coherent subsystem change: they all concern how a **single**
Aegis process reasons through a harness. Point F (inter-instance networking) is a
genuinely new subsystem with no prior ADR, its own transport/threat model, and a
lifecycle independent of this one — a reviewer can accept or reject it without
touching A–E. Splitting keeps each record within the "1–3 page, one decision"
MADR discipline this repo enforces (`adr/README.md`). This ADR is the
reasoning-substrate decision; ADR 0007 is the clustering decision and depends on
it.

## Decision

### A. The harness becomes the sole LLM gateway

1. **Delete the three direct providers from the production path.**
   `backends/ai/{anthropic,openai,aws_bedrock}_provider.py` are removed as
   selectable production backends. Aegis SWR holds **no** model API key. The
   `AIAPIBackend` ABC is **retained as an internal reasoning seam** (so
   `Orchestrator`/`resolve_panel` keep a stable injection type), but its only
   production implementation becomes a thin **harness-backed adapter** (B.2).
   For unit tests, a single deterministic `ScriptedAIBackend` double replaces the
   deleted network providers — tests never reach a real provider and never need a
   key. No `AEGIS_ALLOW_DIRECT_LLM` escape hatch is introduced: a dev back-door
   to a direct provider would re-open exactly the key-holding posture this
   decision removes.

2. **Delete `claude_cli_provider.py`.** Its one legitimate use case — "Claude
   Code as just an LLM, agentic loop stripped" — is re-expressed as a
   **no-tools persona** of the existing `claude_code` backend: a
   `ClaudeCodeTool` invocation with an **empty tool allowlist**
   (`allowed_tools=""`, the posture the provider forced via `--restricted`). This
   removes the duplicate wiring of the `claude` binary and the illegal reach into
   `claude_code.process` internals. `ClaudeCliSettings` is deleted;
   `ClaudeCodeSettings` is the one Claude-Code config surface.

3. **Reframe `router/`, do not delete it.** LiteLLM *dispatch* was never live
   (0005 C11), and with all external-model access now behind harnesses there is
   no Aegis-side model routing left to do. But `agents.yaml` + `RouterConfig`
   survive, **repurposed as the role → harness-session binding table**: for each
   forensic role, which harness family/persona backs it, its tool-allowlist
   tier, and its timeout. The `provider`/`model` fields become **advisory
   metadata** documenting what the backing harness is configured with, never an
   Aegis dispatch instruction; `enabled_when` presence-signal gating is kept
   verbatim. Aegis SWR takes **no** runtime dependency on `litellm`. (OpenHands'
   *internal* LiteLLM config, and an OpenRouter-backed OpenClaude deployment,
   remain entirely the operator's concern inside their respective harness — the
   same black-box contract 0004 established.)

### B. Redelegating the forensic panel onto harness sessions

4. **One harness session per forensic role; arbitration stays deterministic and
   Aegis-side.** `resolve_panel` stops fanning one shared backend to every agent
   and instead injects a **per-role harness session** via a new
   `HarnessSessionFactory` (owned by `harness/`, built at the composition root).
   The multi-agent LangGraph in `core/orchestrator.py`, the per-agent
   `default_weight` (ADR 0002), the `AgentTurn`/event accounting, and the
   **"exactly one ARBITER"** panel invariant are all **unchanged**. Critically,
   `core/consensus.py`'s weighted-vote arbitration **stays a deterministic
   Aegis-side function** that reads **structured** per-agent output (the existing
   Pydantic `Hypothesis`/`SkepticVerdict` models) from each session. Arbitration
   is **never** moved into a harness — a non-deterministic model arbitrating its
   own debate would void the auditable, reproducible consensus the whole design
   exists to provide, and would collapse the independent-agent assumption the
   weights encode.

5. **`AIAPIBackend` → harness adapter.** The per-role injected object implements
   the retained `AIAPIBackend.generate(system_prompt, messages, output_schema)
   -> BaseModel | str` seam but fulfils it by delegating to a harness session
   (pushing the role's system prompt + messages as the task, parsing the
   session's structured result back into `output_schema`). This keeps
   `Orchestrator`/`resolve_panel` structurally intact — the change is *what the
   backend is*, not *how the panel is driven*. Each role's session carries a
   **role-scoped tool allowlist** (D): investigators and the skeptic get
   read-only context tools; only `code_analyst` keeps a code-navigation-tool
   session (its existing `CodeAgent.investigate()` posture).

### C. Context exchange: hybrid push + Aegis-as-MCP-tool-surface

6. **Hybrid, not pure-push and not pure-tool-exposure.** Aegis pushes a
   **bounded, pre-redacted incident summary** into each session's initial
   context, and additionally **exposes itself as an MCP tool surface** (the
   "Topology C" inversion sketched in
   [Milestone 0004 plan.md](/docs/roadmap/0004-code-intelligence/plan.md#topology-c--openclaude-as-the-primary-orchestrator-inverted))
   — `get_similar_incidents`, `get_event_log`, `get_evidence_slice`,
   `analyze_incident` — from which a session **pulls deeper detail on demand**.
   Full-push alone is rejected (crash dumps/log corpora exceed every backend's
   context window and would forward unredacted hostile payload wholesale);
   pure-tool-exposure alone is rejected (round-trip latency and the model not
   knowing what to ask for without a seeded summary). The hybrid mirrors how
   `code_analyst` already seeds a question and lets `CodeAgent.investigate()`
   pull specifics.

7. **The MCP tool surface is the single redaction chokepoint.** No incident byte
   crosses into a harness except through the pushed summary (pre-redacted) or an
   MCP tool response (redacted at the tool boundary, `SensitiveFilter`-covered,
   authorization-checked). "Load similar issues into context memory" (the user's
   phrase → `core/incident_similarity.py`) is served by `get_similar_incidents`
   returning **redacted structured hits** (not raw prior payloads), plus an
   optional bounded push of the top-k summaries into the LangGraph state as
   today. Raw dump/log/stack text is never forwarded unredacted, never logged,
   never persisted unredacted. Standing up this MCP server is a new surface and a
   `security-auditor` gate item.

### D. Security: trust tiers, with sandbox mandatory for payload ingestion

8. **Split the single-active-backend selector into two trust tiers.** 0005's C2
   assumed **one** active backend for **one** narrow read-only role. Promoting
   the harness to ingest raw dump/log content end-to-end breaks that assumption,
   so selection generalises from "one active backend" to **"one active backend
   per trust tier"**:
   - **Payload tier** — any session that ingests raw/attacker-influenced
     incident payload (the investigator roles, `analyze_incident`).
     **MUST be a Docker-sandboxed backend → OpenHands.** Host-permission
     backends (Claude Code, OpenClaude) are **rejected at composition time** for
     this tier. Running a host-permission harness over hostile payload end-to-end
     is not acceptable; the sandbox is the control.
   - **Trusted-source tier** — sessions touching only the product's own
     already-trusted source (code navigation, the current `code_analyst`
     `CodeAgent` use). **May** use a host-permission backend (Claude Code /
     OpenClaude), exactly as today.
   The loud-ambiguity discipline of 0005 C2 (`HarnessConfigError` on an unresolved
   selector) is preserved **per tier**. This is a deliberate, called-out change to
   0005 C2 — see *Consequences → what 0005 conventions change*.

### E. Staged autonomy — from suggesting a fix to performing it

9. **Four opt-in autonomy stages, each gated; HITL and escalation never removed.**
   Default posture is read-only (Stage 0). Each higher stage is a per-deployment
   explicit opt-in, never the default, and each adds exactly one capability tier:

   | Stage | Capability granted | Output | Gate (all cumulative) |
   |-------|--------------------|--------|-----------------------|
   | **0 Analyse** (today) | read-only | `RCAReport` / `HITLRequest` | none beyond baseline |
   | **1 Suggest** | read-only + write-to-sandbox-scratch | RCAReport **+ candidate patch/playbook** (never executed) | human review of the candidate |
   | **2 Execute-validated** | execute **inside the sandbox**, no production credentials, non-production target | validated playbook run + result | playbook passes `/playbook-validate`; `HITLRequest` go/no-go; `incident-analyst` lifecycle review |
   | **3 Autonomous (allowlisted fault-classes only)** | execute for a narrow pre-approved `FaultClass` allowlist (`core/fault_codes.py`), reversible, kill-switch | auto-remediation + audit trail | all of Stage 2, **per fault-class**, + standing HITL escalation + `security-auditor` CRITICAL-blocks-merge for the allowlist |

   Non-negotiable across all stages: the `HITLRequest` escalation path stays
   available at every tier (low consensus confidence still escalates to a human);
   any stage transition is a lifecycle change requiring an `incident-analyst`
   pass; any capability escalation requires a `security-auditor` pass that
   CRITICAL-blocks merge; execution only ever happens inside the sandboxed
   (OpenHands) runtime (D.8). No stage removes a human's ability to intervene.

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| **Keep direct providers as a non-production/offline fallback** (guard behind `AEGIS_ALLOW_DIRECT_LLM`) | Smallest diff; offline dev without a harness installed | Re-opens the exact key-holding posture the user wants removed; a dev flag inevitably leaks to prod; two reasoning paths drift | Contradicts the core directive (Aegis holds no key); a `ScriptedAIBackend` test double covers the offline-test need without a real provider |
| **Keep `claude_cli_provider.py` as a distinct "LLM-only" family** | No panel rewrite for that path | Perpetuates the duplicate `claude` wiring and the illegal reach into `claude_code.process`; two Claude-Code settings/auth stories | The "no agentic loop" case is just an empty-allowlist `claude_code` call; duplication is the mess this ADR removes |
| **One harness session per incident with internal sub-agent fan-out** (harness spawns its own os_kernel-equivalents) | Cheapest shared context; closest to how a Claude Code session uses its own Task tool; natural fit for the Stage-3 "do the fix" endgame | Internal sub-agents are **opaque** to Aegis — loses per-agent `AgentTurn`, weights (ADR 0002), and per-agent events; the deterministic arbiter can't read structured per-agent output; breaks `consensus.py` | Defeats the auditable weighted-consensus contract; deferred to **future scope** once autonomy (Stage 3) and per-agent observability can be reconciled |
| **Single session, all roles as prompted personas** | Cheapest tokens/latency | One model playing skeptic against its own hypotheses is weak adversarial validation; collapses the independent-agent assumption the weights encode | Undermines the whole reason the skeptic/consensus design exists |
| **Move arbitration into the harness** | Lets the model weigh its own debate holistically | Non-deterministic, non-reproducible, unauditable; voids ADR 0002 weights and the "exactly one ARBITER" invariant | Arbitration must stay a deterministic Aegis-side function reading structured output |
| **Pure push** (serialise full `SourceCollection` into context) | Simplest; no MCP server to build | Exceeds every backend's context window on real dumps; forwards unredacted hostile payload wholesale into a harness | Confidentiality + context-limit failure; hybrid bounds both |
| **Pure tool-exposure** (harness pulls everything via MCP, no seed) | Tightest redaction boundary; minimal upfront tokens | Latency of many round-trips; model doesn't know what to ask without a seeded summary; weak first-turn grounding | Hybrid keeps the redaction boundary while seeding a bounded summary |
| **Allow host-permission backends for payload ingestion with a stricter allowlist** | Keeps real-token Claude Code available for the main panel | A tool allowlist does not contain code-exec/escape risk the way a container does; hostile payload end-to-end on host perms is the precise risk 0005 flagged for OpenHands-vs-the-others | Sandbox is the only adequate control for payload-tier ingestion |

## Consequences

### Positive

- **One reasoning substrate.** Every model call goes through the audited
  `harness/` selection surface; Aegis holds no API key; the four-way split
  collapses to a single gateway with a single credential story per backend.
- **The harness becomes first-class.** Real token accounting (Claude Code C9),
  sandboxing (OpenHands), and the loud-ambiguity selection discipline now cover
  the *whole* investigation, not a side call.
- **Consensus stays auditable.** ADR 0002 weights, the one-arbiter invariant, and
  deterministic reproducible arbitration are preserved byte-for-byte in contract.
- **Confidentiality boundary is explicit and singular.** The MCP tool surface +
  pushed-summary redaction is the one chokepoint for payload egress into a model.
- **Autonomy is a ramp, not a leap.** Each stage is opt-in, gated, reversible,
  and never removes human escalation.

### Negative

- **Large deletion + migration.** Removing three providers + `claude_cli_provider`
  re-targets every test and composition path that built `create_ai_backend`. The
  `ScriptedAIBackend` double must cover prior unit coverage.
- **Token/latency cost of per-role sessions.** N harness sessions per incident
  cost more than one shared provider call. Mitigated by the hybrid context model
  (bounded push + on-demand pull) and by role-scoped tool allowlists, but it is a
  real cost regression to measure.
- **OpenHands/Docker becomes effectively mandatory in production.** Payload-tier
  ingestion requires the sandboxed backend, so a host-only deployment can run
  only trusted-source-tier work. Docker-on-Windows (already a 0005 prerequisite)
  is now a hard production dependency, not an option.
- **A new MCP server to build, review, and threat-model.** Net-new attack surface
  that must carry `SensitiveFilter`, authorization, and a `security-auditor` gate.
- **Harness latency now sits on the critical path** of every agent turn, not just
  code navigation.

### What 0005 conventions change (explicit)

- **0005 C2 (single active backend) generalises to single active backend
  *per trust tier*** (payload tier vs trusted-source tier), with the payload tier
  constrained to sandboxed backends. The loud-ambiguity rule is preserved per
  tier; `AEGIS_CODE_INTEL_BACKEND` alone is no longer sufficient to express the
  selection and must be complemented by a tier-aware selector (named in task
  breakdown below). This is the one 0005 contract this ADR deliberately amends.
- **0005 C11 (`agents.yaml` roles are inert routing config)** is *reframed*: the
  roles become the role → harness-session binding table (A.3). `enabled_when`
  gating is unchanged.
- **0004 C5 / 0005 C9 (token accounting through `CodeResult.token_estimate`)** is
  reused unchanged for per-role sessions; the panel's cost accounting now flows
  through the same field.

### Future scope

- **Per-incident single-session fan-out** (the harness spawning its own
  sub-agents) is deferred until per-agent observability and deterministic
  consensus can be reconciled with it — likely the natural Stage-3 topology.
- **Stage 3 autonomous remediation** ships disabled; the fault-class allowlist and
  kill-switch design is a separate future ADR gated by `security-auditor`.
- **Dropping the `AIAPIBackend` seam entirely** (folding the panel directly onto a
  harness-session interface) is possible once no non-harness reasoning path
  remains, but is deferred to avoid widening this change.

## Validation / Rollout

- **Grep/CI gate:** no `import` of `anthropic`, `openai`, or `boto3` (bedrock) in
  `src/aegis_swr/` outside deleted-file history; `create_ai_backend` no longer
  constructs a network provider; no module imports `claude_cli_provider`.
- **No-key boot:** the full `aegis analyze` dry-run path completes with **no**
  `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/AWS creds in the environment (keys live
  only inside the chosen harness, per its own contract).
- **Panel parity:** `resolve_panel` injects a per-role session; the LangGraph,
  weights (ADR 0002), one-arbiter invariant, and deterministic `consensus.py`
  output are unchanged under a `ScriptedAIBackend`-equivalent harness double.
- **Trust-tier enforcement:** composition **rejects** a host-permission backend
  for a payload-tier session (`HarnessConfigError`-equivalent) and accepts only a
  sandboxed one; trusted-source tier still accepts host-permission backends.
- **Redaction:** no raw dump/log/stack text reaches any harness context, log sink,
  MCP tool response, or persisted report unredacted (asserted with a hostile
  fixture payload containing seeded secrets/PII).
- **Autonomy gating:** Stages 1–3 are off by default; each requires its explicit
  opt-in; `HITLRequest` escalation is reachable in every stage; execution occurs
  only inside the sandboxed runtime; `/playbook-validate` precedes any Stage-2+
  run.
- **Coverage:** ≥90% on the new harness adapter and MCP tool surface; 100% branch
  on the trust-tier selection and the autonomy-stage gate.

## Links

- **Extends:** [ADR 0003 - Code intelligence composition root](/docs/adr/0003-code-intel-composition-root.md),
  [ADR 0004 - Harness composition generalisation](/docs/adr/0004-harness-composition-generalization.md)
- **Companion:** [ADR 0007 - Multi-instance mastermind/worker protocol](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md)
- **Milestone history:** [0004 plan.md](/docs/roadmap/0004-code-intelligence/plan.md)
  (Topology C), [0005 plan.md](/docs/roadmap/0005-harness-backends/plan.md)
  (C1–C13, three-backend comparison, selection/ambiguity model)
- **Consensus weight contract:** [ADR 0002](/docs/adr/0002-agent-weight-as-property.md)
- **Follow-up implementation/tests:** see *Validation / Rollout*; hand to
  `python-expert` (adapter, trust-tier selector, MCP surface) and `testing-expert`
  (ScriptedAIBackend double, redaction fixtures, stage-gate tests);
  `security-auditor` gate on the MCP surface and every autonomy escalation;
  `incident-analyst` gate on the autonomy-stage lifecycle.
