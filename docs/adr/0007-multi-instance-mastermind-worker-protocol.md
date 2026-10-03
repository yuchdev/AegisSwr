# 0007 - Multi-instance mastermind/worker protocol for distributed incident analysis

> **Status:** Proposed
>
> **Date:** 2026-10-03
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

[ADR 0006](/docs/adr/0006-harness-as-sole-llm-gateway.md) makes the agentic
harness the sole reasoning substrate of a **single** Aegis SWR process: one
process ingests an incident, drives a per-role harness panel to a deterministic
consensus, and emits an `RCAReport`/`HITLRequest`. The user additionally wants to
**distribute** this across machines: one central **mastermind** instance that
receives and queues incoming incidents and redistributes analysis tasks to
multiple **worker** instances, each sandboxed and owning its own harness-backed
panel (a worker might run `openhands` only).

This is **new ground**. There is no existing ADR for inter-instance networking,
and it must be built as a **new subsystem, not an extension of `harness/`.**
`harness/` selects a backend *inside one process*; nothing in it concerns
process-to-process trust, task distribution, or result aggregation. Conflating
the two would pull network/transport concerns into the one package 0004/0005
deliberately kept as a pure in-process selection surface.

The design must respect conventions the codebase already holds:

- **gRPC infrastructure already exists** — `openclaude/grpc/` has a committed
  `.proto`, generated stubs, a mockable client seam, and a streaming model that
  0004 chose precisely because "its stream maps directly onto Aegis SWR's
  `EventBus`" and "needs no live process in unit tests."
- **EventBus/SSE** is the established progress-streaming pattern for the
  REST/SSE API (`specs/implementation_spec.md`).
- **Hostile-payload posture** (`../CLAUDE.md` §1): every incident payload is
  attacker-influenced. ADR 0006 extends this — a sandboxed worker that runs a
  harness over that payload must itself be treated as **semi-trusted**: its
  output is re-validated, and it is never handed secrets it does not need.
- **Single-active-harness-per-process** (0005 C2, as amended per-tier by ADR
  0006): each worker process still selects exactly one active backend per trust
  tier; the cluster layer must compose *with* that, not override it.

## Decision

Introduce a **new `aegis_swr/cluster/` package** (explicitly *not* part of
`harness/`) implementing a mastermind/worker control plane.

### 1. Transport — gRPC control plane, EventBus-over-stream progress

The mastermind↔worker **control plane is gRPC**, reusing the committed-proto +
generated-stub + mockable-client conventions already proven in
`openclaude/grpc/`. Rationale, weighed against the alternatives (table):

- A gRPC bidirectional stream maps **directly onto the existing `EventBus`** —
  worker progress (`AgentSpoke`, `ConsensusEvaluated`, `HumanInputRequired`)
  streams back frame-by-frame to the mastermind exactly as OpenClaude frames
  already stream onto the bus, with no polling.
- The contract is a **committed `.proto`**, so mastermind↔worker tests mock the
  stub and need **no live peer** — the identical test seam 0004 relied on.
- It reuses infra and reviewer familiarity the codebase already has; it does not
  introduce a message-broker operational dependency.

Only `cluster/grpc/client.py` and `cluster/grpc/server.py` import `grpc` or the
generated stubs — the same single-importer isolation 0005 C3 enforces for
`openclaude/grpc/client.py`. The existing REST/SSE API is retained as the
**human-facing** ingress/observability surface (operators submit incidents and
watch SSE as today); gRPC is the **internal** mastermind↔worker fabric.

### 2. Task-distribution contract

The mastermind maintains an **incident intake queue** and dispatches
`TaskAssignment` messages; workers return results on a streamed `TaskResult`
channel. (Field names are indicative; the authoritative schema is the committed
`.proto`, authored in the implementation task.)

**`TaskAssignment` (mastermind → worker)** carries:
- `task_id` — UUID4, the **idempotency key** (worker dedupes on it).
- `incident_id` and `mode` (`IncidentMode`).
- **A redacted incident reference, not raw payload** — a content-addressed handle
  (e.g. `dump_hash` + an authorized fetch URI) that the worker pulls over an
  authorized channel into its *own* sandbox; raw dump/log bytes never travel in
  the task message itself. This keeps payload movement on one audited path and
  out of control-plane logs.
- `required_trust_tier` and `required_capability` — the backend posture the task
  needs (e.g. "payload-tier ⇒ sandboxed backend", per ADR 0006 D).
- `deadline` / `attempt` — for timeout and retry semantics.

**`TaskResult` (worker → mastermind)** carries: `task_id`, status, the
**structured, redacted `RCAReport`** (the existing Pydantic schema), token/cost
accounting (via the `CodeResult.token_estimate` lineage, 0005 C9), and any
`HITLRequest`. Progress events stream on the same channel before the terminal
result.

**Idempotency / retry.** At-least-once delivery with **worker-side idempotent
processing keyed on `task_id`**: a redelivered task returns the cached result
rather than re-running the panel. Retries use bounded exponential backoff
(`asyncio.sleep`, never `time.sleep`, per 0005 C13); after N attempts the task is
**dead-lettered** to a mastermind-side queue for human triage — a failed forensic
task surfaces, it is never silently dropped or silently retried on a different
worker in a way that masks the failure (mirroring 0005's no-silent-fallback
stance).

### 3. Worker sandboxing enforced at the network boundary

Workers are **semi-trusted**, mirroring how the codebase treats incident payload:

- **No mastermind-level secrets cross to a worker.** A worker receives only what
  its task needs: the redacted incident handle and its own task scope. It holds
  **only its own harness credentials** (its OpenHands/Claude Code/OpenClaude
  config, per ADR 0006 A); it never receives the mastermind's store credentials,
  other backends' keys, or cluster-admin tokens.
- **Workers are isolated from each other.** A worker can reach the mastermind and
  its own harness/sandbox only — never another worker, and never another
  incident's data. Enforced by **mTLS** between mastermind and each worker plus
  **per-worker scoped tokens** (a worker's token authorizes only its assigned
  `task_id`s and its own incident-handle fetches).
- **Worker output is re-validated, not trusted.** A `TaskResult` is treated as
  semi-trusted input: the mastermind re-runs the deterministic
  `skeptic`/`consensus` validation (ADR 0006 B.4) over the returned structured
  hypotheses before the result is promoted to a trusted `RCAReport`. A compromised
  or malfunctioning worker cannot inject an unvetted conclusion.
- **Redaction holds across the wire.** `TaskResult` and all streamed progress carry
  only redacted/structured content; `SensitiveFilter` covers the gRPC sinks; no
  raw payload or secret appears in a control-plane log or exception (0005 C13).

### 4. Composition with single-active-harness-per-process

**Each worker keeps its own `AEGIS_CODE_INTEL_BACKEND` and its own per-tier
selection** (0005 C2 as amended by ADR 0006). The mastermind does **not** override
a worker's backend. Instead:

- At registration each worker **advertises its capabilities** — which backend
  families and trust tiers it can serve (e.g. "payload-tier: openhands;
  trusted-source-tier: claude_code") — in a `WorkerCapabilities` handshake.
- The mastermind **routes by advertised capability**: a payload-tier task is
  assigned only to a worker advertising a sandboxed payload-tier backend.
- This composes cleanly with 0005's single-active model: selection stays a
  per-process concern; the cluster layer is a *matcher* over advertised
  capability, never a remote mutator of a worker's selector. If no worker
  advertises the required capability, the task is **queued and surfaced** (a loud
  capability gap), never downgraded to an unsuitable backend.

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| **Make this an extension of `harness/`** | No new package | `harness/` is a pure in-process backend-selection surface; adding network/transport/trust there violates its charter and the 0004/0005 isolation posture | Must be a new subsystem; `cluster/` keeps `harness/` clean |
| **REST/SSE for the control plane** (reuse the API pattern) | Already in the codebase; simplest | SSE is unidirectional server→client; task *dispatch* and bidirectional control fit awkwardly; no committed-schema mock seam like gRPC's | Keep REST/SSE for human ingress/observability; gRPC fits bidirectional internal control and reuses the existing proto/mock seam |
| **Message queue / broker** (e.g. Redis Streams, RabbitMQ, SQS) | Durable at-least-once, natural dead-lettering, decouples producer/consumer | New operational dependency the codebase doesn't have; weaker typed-contract story than a committed proto; heavier for the initial topology | Deferred to **future scope** for durable intake; the gRPC control plane can front a broker later without changing the task contract |
| **Mastermind assigns/overrides each worker's backend remotely** | Central control of model posture | Breaks single-active-per-process (0005 C2); turns the cluster layer into a remote mutator of a security-relevant selector; a worker could be forced onto a non-sandboxed backend for payload work | Route by *advertised* capability instead; selection stays a per-process decision |
| **Ship raw payload inside the task message** | One hop; worker needs no fetch channel | Puts hostile payload on the control plane and into its logs; bloats messages; widens the redaction surface | Send a redacted handle; the worker pulls payload into its own sandbox on one audited path |
| **Trust worker output directly** | Less mastermind compute | A semi-trusted/compromised worker could inject an unvetted RCA conclusion | Re-validate via deterministic skeptic/consensus mastermind-side |

## Consequences

### Positive

- **Horizontal scale** of incident analysis with per-worker sandbox isolation.
- **Reuses proven infrastructure** — the `openclaude/grpc/` proto+mock seam and
  the `EventBus` streaming model extend naturally to the cluster fabric.
- **Trust boundary is explicit** — semi-trusted workers, scoped tokens, mTLS,
  no secret leakage, output re-validation; consistent with the hostile-payload
  posture the product already assumes.
- **Composes with, rather than fights, single-active-per-process selection** —
  capability advertisement + mastermind routing keeps backend choice local.

### Negative

- **A genuinely new subsystem** to build, secure, and operate: PKI/mTLS, token
  scoping, a queue, dead-lettering, and worker lifecycle/health. Substantial
  surface for a `security-auditor` CRITICAL gate.
- **Operational complexity** — certificate rotation, worker registration/health,
  and capability-advertisement drift are new failure modes.
- **Double arbitration cost** — re-validating worker output mastermind-side costs
  additional reasoning, the deliberate price of not trusting a worker's verdict.
- **Payload-fetch channel** is a second audited path that must carry the same
  redaction and authorization guarantees as the MCP surface in ADR 0006.

### Future scope

- **Durable broker** behind the gRPC control plane for at-least-once intake that
  survives a mastermind restart (the task contract is designed to allow this
  without change).
- **Multi-mastermind / HA** (leader election, mastermind failover) — out of scope
  here; this ADR assumes a single mastermind.
- **Cross-worker work-stealing / load rebalancing** beyond simple
  capability-matched dispatch.
- **Autonomous remediation across the cluster** (ADR 0006 Stage 3 executed on a
  worker) inherits all of ADR 0006's gating and is not enabled by this ADR.

## Validation / Rollout

- **Isolation:** only `cluster/grpc/{client,server}.py` import `grpc`/stubs;
  `core/`, `views/`, `harness/`, and the backend packages import no `cluster`
  module (grep-enforced, mirroring 0005 C3).
- **Mock-peer tests:** mastermind↔worker flows run against a mocked gRPC stub with
  **no live peer**, per the 0004 seam.
- **Idempotency:** a redelivered `task_id` returns the cached result without
  re-running the panel; dead-lettering fires after N bounded-backoff attempts.
- **Secret containment:** a worker token authorizes only its own `task_id`s and
  incident-handle fetches; a worker cannot reach another worker or another
  incident's data; no mastermind store credential is ever present in a worker's
  environment (asserted in an integration test with a hostile worker fixture).
- **Redaction across the wire:** no raw payload/secret in any `TaskAssignment`,
  `TaskResult`, streamed event, or control-plane log (hostile-fixture assertion).
- **Capability routing:** a payload-tier task is never assigned to a
  host-permission-only worker; an unmatched task is queued and surfaced, never
  downgraded.
- **Output re-validation:** a `TaskResult` with a tampered conclusion is caught by
  mastermind-side skeptic/consensus before promotion.

## Links

- **Depends on / companion:** [ADR 0006 - Harness as sole LLM gateway](/docs/adr/0006-harness-as-sole-llm-gateway.md)
  (trust tiers, per-role sessions, deterministic consensus re-validation)
- **Reused infrastructure:** `openclaude/grpc/` (committed proto + mock-client
  seam), `core/events.py` `EventBus`, REST/SSE API (`specs/implementation_spec.md`)
- **Hostile-payload posture:** `../CLAUDE.md` §1; 0005 C13
- **Follow-up:** hand `cluster/` proto, client/server, token-scoping, and queue to
  `python-expert`; mock-peer + hostile-worker + redaction suites to
  `testing-expert`; `security-auditor` CRITICAL gate on the mTLS/token/trust
  boundary; `incident-analyst` pass on the distributed lifecycle and
  dead-letter/escalation path.
