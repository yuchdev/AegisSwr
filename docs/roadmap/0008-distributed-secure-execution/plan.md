# Milestone 0008 — Distributed Secure Execution

**Package:** `aegis-swr` | **Module roots:** extends `aegis_swr/cluster/` (the
ADR 0007 subsystem); new `aegis_swr/sandbox/` execution-strategy family; extends
`aegis_swr/backends/debug/`, `aegis_swr/core/`, and `aegis_swr/agents/`.
**Depends on:**

- [ADR 0008](/docs/adr/0008-distributed-secure-execution-sandbox.md) — this
  milestone's decision record.
- [ADR 0007](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md) /
  the `cluster/` subsystem (gRPC control plane, mTLS, scoped tokens, capability
  advertisement, `TaskAssignment`/`TaskResult`, idempotency, dead-lettering) —
  **extended, not duplicated**. ADR 0007 is itself *Proposed*; this milestone is
  gated on its `cluster/` package existing. See *Sequencing & external gating*.
- [ADR 0006](/docs/adr/0006-harness-as-sole-llm-gateway.md) — the payload trust
  tier, the MCP redaction chokepoint, and sandbox-mandatory-for-payload. The
  **return path** for captured artifacts re-enters through these.

This milestone implements [ADR 0008 — Distributed secure execution](/docs/adr/0008-distributed-secure-execution-sandbox.md).
It takes the **extracted** former Milestone 0001 Task 9 ("Secure Code Sandbox" — a
local Docker patch-compile check, never started; original scope in
[implementation_spec.md §10](/docs/specs/implementation_spec.md)) and **expands**
it into a cross-instance, cross-platform **distributed execution architecture**: a
single **analytical center** instance (the ADR 0006 forensic panel) delegates
**execution work** — patch validation, *live crash reproduction*, and fresh
dump/stack/log capture — to one or more **sandbox worker** instances that may run
on a different OS/platform than the center (e.g. center on macOS, worker on
Windows). Captured artifacts are shipped back and re-ingested as new hostile
payload.

> **Extraction note.** This milestone was carved out of
> [Milestone 0001](/docs/roadmap/0001-generic-implementation/plan.md) on
> 2026-10-03; Milestone 0001's Tasks 10/11 were renumbered to 9/10 and its
> `11.0-documentation/` folder became `10.0-documentation/`. The `Task 5 → Task 9
> (Sandbox)` dependency edge and the sandbox hardening/image-build chores moved
> here with the executor. Milestone 0001 is **not** touched further by this
> milestone.

> **Roadmap vs ADR numbering.** This is roadmap **milestone 0008** and it
> implements **ADR 0008** — the numbers coincide this time, but roadmap and ADR
> numbers remain independent sequences in this repository (ADR 0004 documents
> roadmap milestone 0005; roadmap milestone 0007 implements ADR 0006). Do not
> infer a general 1:1 mapping.

---

## Decomposition level (declared)

This plan is written at **task-level granularity**, mirroring
[Milestone 0005](/docs/roadmap/0005-harness-backends/plan.md) (see the roadmap
index note: "Milestone 0005 is at task-level granularity — subtask decomposition
is a later pass"). **Subtask (`{TT.t}-{slug}/NN-*.md`) decomposition is a
deliberate later pass**, taken once the `cluster/` subsystem of ADR 0007 is
actually built (this milestone is gated on it) so that the execution-task contract
is decomposed against real `cluster/` interfaces rather than proposed ones. The
task table, numbered contracts, architecture diagram, dependency graph, file map,
and global acceptance criteria below carry the rigor of Milestone 0007's plan; the
per-subtask atomic specs follow in the subtask pass.

---

## Background

[implementation_spec.md §10](/docs/specs/implementation_spec.md) specified a
narrow local sandbox: when the Code Analyst agent emits a `probabilistic_fix`
(unified diff), `sandbox/executor.py` runs `docker run --rm --network=none
--read-only …` against a pre-built per-language image (`cpp20`/`python311`/
`java21`/`typescript5`), compiles + AST-lints, and returns `ValidationResult {
passed, exit_code, compiler_output, lint_findings }`; on failure the agent may
revise once. It was never started.

The user's directive expands this three ways (ADR 0008 Context):

1. **Patch validation** — the original compile/lint check (retained as one
   execution kind).
2. **Live crash reproduction** — actually *run the target application under
   instrumentation* to reproduce a crash, as opposed to parsing an existing dump
   post-mortem (which is all today's `backends/debug/{cdb,gdb,lldb}_worker.py` do,
   locally).
3. **Fresh artifact capture** — capture the resulting dump/stacks/logs and ship
   them back to the center.

Because a worker now **executes arbitrary target/candidate code** and the
**artifacts flow back** as new attacker-influenced payload, this is a
**bidirectional** hostile-data problem. The design decision (ADR 0008 §A) is to
**extend ADR 0007's `cluster/` subsystem** with a new execution-worker capability
rather than build a separate protocol: reuse the gRPC control plane, mTLS, scoped
tokens, idempotency, and dead-lettering; add an `ExecutionTask`/`ExecutionResult`
contract, an execution capability descriptor, and — the one genuinely new surface
— a **return-path redaction boundary** (the inverse of ADR 0007's inbound one).

### Terminology (carried from ADR 0008)

The files `backends/debug/{cdb,gdb,lldb}_worker.py` are **debug backends** —
in-process strategies that parse an *existing* dump post-mortem. A **sandbox
worker** is a *separate Aegis SWR instance* on the network that *launches and
instruments* a target and *uses* the debug backends once it has a fresh dump.
This plan says **debug backend** vs. **sandbox worker** throughout.

---

## Architecture

```
           ANALYTICAL CENTER (e.g. macOS)                         SANDBOX WORKER (e.g. Windows)
┌───────────────────────────────────────────────┐      ┌──────────────────────────────────────────────┐
│ core/orchestrator.py  (ADR 0006 forensic panel)│      │ cluster/grpc/server.py   (ADR 0007, reused)    │
│ agents/code_analyst.py → probabilistic_fix     │      │   WorkerCapabilities handshake + exec descriptor│
│        │                                        │      │        │  (os/arch, debug_toolchain, runtime,   │
│        ▼                                        │      │        │   language_runtimes)  ◄── C.C2          │
│ cluster/ (ADR 0007, EXTENDED)                   │      │        ▼                                        │
│   scheduler: capability-matched routing ◄─ C.C3 │ gRPC │ sandbox/   (NEW execution-strategy family)      │
│   ExecutionTask  (TaskAssignment subtype) ─ C.C1├─────►│   base.py    ExecutionStrategy ABC  ◄── C.C4    │
│        │  content-addressed input handles       │ mTLS │   validate_patch_strategy.py  (spec §10 scope)  │
│        │  (patch/build/symbol), sandbox_profile │ +    │   reproduce_strategy.py       (live launch)     │
│        ▼                                        │tokens│   collect_strategy.py         (stack/log grab)  │
│ ExecutionResult (TaskResult subtype)  ◄── C.C1  │◄─────┤        │  docker/gvisor: network=none, cap_drop  │
│   artifact *references* + redacted summary      │      │        │  ALL, read-only, caps, timeout ◄─ C.C5  │
│        │                                        │      │        ▼                                        │
│        ▼  authorised content-addressed FETCH    │      │ backends/debug/* used on the FRESH dump         │
│ core/artifact_ingest.py  ◄── C.C6               │◄─────┤ sandbox/redaction.py  (return-path) ◄── C.C7    │
│   re-scrub via Data Adapter + ADR 0006 MCP      │fetch │   redact at worker boundary before egress       │
│   → re-validate verdict (skeptic/consensus)     │      │ (holds NO center creds; scoped token only)      │
└───────────────────────────────────────────────┘      └──────────────────────────────────────────────┘
```

**Hard boundaries (inherited):**

- Only `cluster/grpc/{client,server}.py` import `grpc`/stubs (ADR 0007 Validation,
  extended). `core/`, `views/`, `harness/`, and the backend packages import no
  `cluster` module.
- No raw dump/log/stack byte crosses the control plane; artifacts move only over
  the authorised content-addressed fetch channel and are **re-scrubbed on center
  ingestion** (C.C6/C.C7). `SensitiveFilter` on every new sink.
- Execution-only workers hold **no model key and no center store credential**
  (ADR 0007 §3; C.C5).

---

## Tasks

| Task | Name                                           | Category       | Output                                                                                                                                                             |
|------|------------------------------------------------|----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 01.0 | Execution Contract & Proto Extension           | infrastructure | `ExecutionTask`/`ExecutionResult` as `TaskAssignment`/`TaskResult` subtypes in the `cluster/` committed `.proto`; `execution_kind` enum; artifact-reference schema (C.C1) |
| 02.0 | Execution Capability Advertisement & Routing   | configuration  | Extend `WorkerCapabilities` with the execution descriptor (os/arch, debug_toolchain parse-vs-launch, container_runtime, language_runtimes); capability-matched scheduler + loud capability-gap (C.C2, C.C3) |
| 03.0 | Sandbox Execution-Strategy Family              | infrastructure | `aegis_swr/sandbox/`: `ExecutionStrategy` ABC + `validate_patch` / `reproduce_crash` / `collect_*` strategies + factory; Factory-Strategy per `../CLAUDE.md` (C.C4) |
| 04.0 | Sandbox Isolation Profile Enforcement          | infrastructure | `sandbox_profile` enforcement (network=none, cap_drop=ALL, read-only, tmpfs/mem/cpu caps, timeout, RAII teardown); image-digest verify, never-pull; gVisor-preferred (C.C5) |
| 05.0 | Live Reproduction via Debug Backends           | integration    | Worker launches the target under instrumentation and drives `backends/debug/*` to capture a **fresh** dump/stack (distinct from today's post-mortem parse) (C.C4, C.C5) |
| 06.0 | Return-Path Redaction & Artifact Transport     | infrastructure | `sandbox/redaction.py` (redact at worker boundary) + authorised content-addressed artifact fetch into the center object store; no raw byte on the control plane (C.C7) |
| 07.0 | Center-Side Artifact Ingestion & Re-Validation | integration    | `core/artifact_ingest.py`: re-scrub worker artifacts through the Data Adapter + ADR 0006 MCP chokepoint; re-validate `validate_patch` verdicts via skeptic/consensus; Code Analyst correction-retry loop preserved (C.C6) |
| 08.0 | Co-Hosted Payload-Tier Capability (optional)   | configuration  | Allow one worker to advertise **both** execution and ADR 0006 payload-tier harness capabilities, scheduled independently; execution-only worker needs no model key (C.C8) |
| 09.0 | Test Suite — Unit                              | testing        | Capability-routing, sandbox-profile enforcement, return-path redaction, re-ingestion re-scrub, no-trust-shortcut, credential-containment suites (ADR Validation)  |
| 10.0 | Test Suite — Integration                       | testing        | Mock-peer center↔worker execution flow; hostile-worker + sandbox-escape fixtures; cross-platform capability-gap; skipped without Docker/gVisor/cluster signals     |
| 11.0 | Documentation, Security Gate & CI              | documentation  | Config/operator docs for the worker fleet; `security-auditor` **CRITICAL** gate threat model; `incident-analyst` lifecycle pass; CI isolation/import-ban extension; roadmap/docs sync; closeout |

**Sequencing.** 01.0 (contract) and 02.0 (capability/routing) are the foundation
and can proceed in parallel once the `cluster/` subsystem exists. 03.0 (strategy
family) depends on 01.0. 04.0 (isolation) gates 05.0 (live reproduction) —
reproduction must only run under an enforced profile. 06.0 (return path) depends on
03.0/05.0 producing artifacts. 07.0 (center ingestion) depends on 06.0. 08.0
(co-hosting) depends on 02.0 (capability model) and is optional. 09.0/10.0 are
written **incrementally alongside** their implementation tasks (the 0004/0005/0007
convention). 11.0 closes the milestone and carries the CRITICAL security gate.

### Sequencing & external gating

This milestone is **gated on ADR 0007's `cluster/` package being built** (ADR 0007
is *Proposed*; no `cluster/` exists yet). Until then, Tasks 01.0/02.0 may land as
**contract/proto design against the proposed ADR 0007 interfaces**, but the
strategy family (03.0+) should not be implemented against a non-existent transport.
The subtask decomposition pass (declared above) is timed to follow the `cluster/`
build for exactly this reason.

---

## Shared contracts (authoritative)

Defined once here; the subtask pass and per-task READMEs reference them by number.
All extend ADR 0007/0006 contracts rather than restating them.

### C.C1 — `ExecutionTask` / `ExecutionResult` (extend ADR 0007 envelopes)

`ExecutionTask` is a `TaskAssignment` subtype; `ExecutionResult` is a `TaskResult`
subtype. The authoritative schema is the `cluster/` committed `.proto`.
`ExecutionTask` carries `task_id` (UUID4 idempotency key), `incident_id`, `mode`,
an `execution_kind` enum (`validate_patch` | `reproduce_crash` | `collect_logs` |
`collect_stack`), a `required_capability` descriptor (C.C2),
**content-addressed input handles** (patch/build/symbol — hash + authorised fetch
URI, never inline bytes), a `sandbox_profile` (C.C5), and `deadline`/`attempt`.
`ExecutionResult` carries `task_id`, status (`passed` | `failed` |
`crashed_as_expected` | `sandbox_error` | `timeout`), the retained `ValidationResult`
for `validate_patch` (redacted, C.C7), **artifact references** (not bytes) plus a
redacted structured summary for reproduction/collection, and token/cost accounting
(0005 C9) when a harness session was involved. Idempotency, bounded-backoff retry,
and dead-lettering are ADR 0007 §2 **verbatim** — a redelivered execution task
returns the cached result rather than re-running arbitrary code.

### C.C2 — Execution capability descriptor (extends ADR 0007 §4)

`WorkerCapabilities` gains an execution dimension: `os`/`arch`
(`windows/x64`, `linux/x64`, `darwin/arm64`, …), `debug_toolchain` (which debug
backends are usable, each flagged **parse-only** vs. **launch-and-instrument**),
`container_runtime` (`docker` | `gvisor` | none), and `language_runtimes` (the
available patch-compile images). Advertised at registration; the center matches an
`ExecutionTask.required_capability` against it.

### C.C3 — Capability-matched routing (extends ADR 0007 §4)

An `ExecutionTask` is assigned only to a worker whose descriptor **satisfies** its
`required_capability` (e.g. "reproduce on Windows" ⇒ `os=windows` **and**
launch-and-instrument Windows toolchain). If none satisfies it, the task is
**queued and surfaced as a loud capability gap** — never run on a mismatched
platform, never downgraded from reproduce to parse-only (ADR 0007 no-downgrade
stance).

### C.C4 — `aegis_swr/sandbox/` execution-strategy family (Factory-Strategy)

A new backend family under `aegis_swr/sandbox/` following the product's
Factory-Strategy convention (`../CLAUDE.md` Architecture): an `ExecutionStrategy`
ABC, concrete strategies per `execution_kind` (`validate_patch_strategy.py`,
`reproduce_strategy.py`, `collect_strategy.py`), and a
`create_execution_strategy(...)` factory. `validate_patch` carries the original
spec §10 compile/AST-lint behaviour and `ValidationResult` schema; `reproduce_crash`
launches the target under instrumentation and drives a debug backend (C.C5) to
capture a fresh dump.

### C.C5 — Sandbox isolation profile (inherits spec §10 + ADR 0006 §D)

Every execution runs inside the `ExecutionTask.sandbox_profile`: `network=none`
(no egress), `cap_drop=ALL`, read-only root FS, size-bounded tmpfs, memory/CPU
caps, a hard wall-clock timeout, and **RAII teardown of the container on every exit
path** (success/crash/timeout/error). Images are **pre-built and never pulled at
runtime**; the worker **verifies the image digest** before running. `gvisor` is
**preferred** for untrusted-patch/target execution where advertised; plain Docker
is the floor. The worker holds only its own execution credentials and its scoped
token (ADR 0007 §3) — no center store credential, no model key (unless co-hosting,
C.C8), no other incident's data, no other worker reachable.

### C.C6 — Center-side re-ingestion & re-validation (ADR 0006 §C/§D, ADR 0007 §3)

Worker-produced artifacts are **not** trusted because they are "ours." On center
ingestion (`core/artifact_ingest.py`) raw artifact bytes re-enter through the
**same payload-tier path** as any fresh incident payload: the Data Adapter
scrub/noise-filter stages and, for any model-facing use, the ADR 0006 §C MCP
redaction chokepoint. `validate_patch` verdicts and reproduction summaries are
semi-trusted input re-arbitrated by the deterministic skeptic/consensus layer
(ADR 0006 §B.4) before promotion; a tampered worker cannot inject an unvetted
conclusion. The Code Analyst correction-retry loop (spec §10) is preserved.

### C.C7 — Return-path redaction boundary (the one genuinely new surface)

The inverse of ADR 0007's inbound redaction. `sandbox/redaction.py` redacts at the
**worker boundary** before anything leaves the worker: the `ExecutionResult`
structured summary carries only redacted/structured fields; `SensitiveFilter`
covers the worker's gRPC and log sinks; **no raw artifact byte** appears in a
control-plane message or a worker log. Raw bytes move **only** over the authorised
content-addressed fetch channel into the center object store, carrying the same
authorization/redaction guarantees as ADR 0006/0007's inbound channel.

### C.C8 — Co-hosted payload-tier capability (ADR 0006/0007 trust tiers; optional)

A worker **may** advertise **both** `execution` (this milestone) and ADR 0006
**payload-tier harness reasoning** (ADR 0007 over ADR 0006) because both need the
identical Docker-sandboxed posture. They remain **separate advertised capabilities
scheduled independently**: an execution-only worker needs no model key; a
reasoning-only worker is ADR 0007's original shape; a co-hosted worker serves both.
Co-location is a deployment topology, never a merged capability.

### C.C9 — Cross-cutting conventions (inherited verbatim from 0001–0007)

- `Optional[T]` from `typing`, never `T | None` (including subscripts /
  `Annotated[...]`); `from __future__ import annotations` in every new file.
- `ruff` (E,F,I,UP,B,SIM; line length 100) clean; `ruff format` is the formatter.
- Every new public class/function has an RST-style docstring
  (`:param:`/`:ivar:`/`:return:`).
- Loguru with `SensitiveFilter` on **every** sink; no raw dump/log/stack text, no
  secret/credential, and no unredacted model prompt/response ever reaches a log
  sink or exception.
- `asyncio.sleep` for backoff — never `time.sleep`; no bare `except:`; every
  external call (gRPC, container runtime, debugger subprocess, artifact fetch) has
  a timeout and a defined failure path; RAII via context managers for every
  subprocess/socket/container/file resource.

### C.C10 — Module isolation & import bans (extends ADR 0007 Validation / 0005 C13)

Only `cluster/grpc/{client,server}.py` import `grpc`/stubs; `core/`, `views/`,
`harness/`, and the backend packages import no `cluster` module. The new
`aegis_swr/sandbox/` family imports no `cluster` module directly (it is driven by
the worker server). Grep-enforced in CI (Task 11.0), with a self-test proving the
guard turns red on a re-introduced import.

---

## Dependency graph

```
            (external gate: ADR 0007 cluster/ package exists)
                                │
        ┌───────────────────────┴───────────────────────┐
        ▼                                                ▼
Task 01.0 (Execution Contract/Proto)          Task 02.0 (Capability Advert + Routing)
        │                                                │
        ▼                                                │
Task 03.0 (Sandbox Strategy Family)                      │
        │                                                │
        ▼                                                │
Task 04.0 (Isolation Profile Enforcement)                │
        │                                                │
        ▼                                                │
Task 05.0 (Live Reproduction via Debug Backends)         │
        │                                                │
        ▼                                                │
Task 06.0 (Return-Path Redaction + Artifact Transport)   │
        │                                                │
        ▼                                                │
Task 07.0 (Center Ingestion + Re-Validation) ◄───────────┘
        │
        ▼
Task 08.0 (Co-Hosted Payload-Tier Capability — optional)
        │
   Tasks 01–08 ┤
               ├──► Task 09.0 (Unit Tests)        ← incremental
               ├──► Task 10.0 (Integration Tests) ← incremental
               └──► Task 11.0 (Docs + security CRITICAL gate + CI + closeout)
```

**Minimum viable:** 01.0 → 03.0 → 04.0 → 02.0 → 06.0 → 07.0 → 09.0 — a center that
delegates a **`validate_patch`** task to a single remote worker under an enforced
sandbox profile, ships back a redacted result, re-ingests and re-validates it, and
restores the original spec §10 Code Analyst flow across the network.
**Full milestone:** all eleven tasks, including live cross-platform reproduction,
the co-hosted payload tier, integration/hostile-worker suites, and the CRITICAL
security gate.

---

## File map (target state after milestone)

```
src/aegis_swr/
├── cluster/                         ← EXTENDED (ADR 0007 subsystem)
│   ├── grpc/
│   │   ├── aegis_cluster.proto      ← extended: ExecutionTask/ExecutionResult subtypes (C.C1)
│   │   ├── client.py                ← extended: dispatch/collect execution tasks (sole grpc importer)
│   │   └── server.py                ← extended: WorkerCapabilities exec descriptor handshake (C.C2)
│   ├── capabilities.py              ← extended: execution capability descriptor (C.C2)
│   └── scheduler.py                 ← extended: capability-matched routing + loud capability-gap (C.C3)
├── sandbox/                         ← NEW execution-strategy family (Factory-Strategy; C.C4)
│   ├── __init__.py                  ← create_execution_strategy(...) factory
│   ├── base.py                      ← ExecutionStrategy ABC
│   ├── validate_patch_strategy.py   ← spec §10 compile/AST-lint; ValidationResult retained
│   ├── reproduce_strategy.py        ← launch target under instrumentation → fresh dump (C.C5)
│   ├── collect_strategy.py          ← fresh stack/log capture
│   ├── profile.py                   ← sandbox_profile enforcement + image-digest verify (C.C5)
│   └── redaction.py                 ← return-path redaction at the worker boundary (C.C7)
├── backends/debug/                  ← EXTENDED: launch-and-instrument path alongside post-mortem parse (C.C4)
├── core/
│   ├── artifact_ingest.py           ← NEW: re-scrub worker artifacts via Data Adapter + MCP chokepoint; re-validate (C.C6)
│   └── exceptions.py                ← add SandboxExecutionError (promoted from spec §3), ExecutionCapabilityError
└── agents/code_analyst.py           ← UNCHANGED contract; its probabilistic_fix now validated across the cluster

config/
├── settings.py                      ← SandboxSettings (runtime, caps, timeout) + worker-fleet/center settings
└── config.yaml                      ← sandbox + cluster worker-fleet defaults

tests/
├── unit/
│   ├── sandbox/                     ← test_strategies.py, test_profile.py, test_redaction.py (C.C5, C.C7)
│   ├── cluster/                     ← test_execution_contract.py, test_capability_routing.py (C.C1-C.C3)
│   └── core/                        ← test_artifact_ingest.py (C.C6)
└── integration/
    └── distributed_execution/       ← mock-peer center↔worker exec flow; hostile-worker + sandbox-escape fixtures;
                                        cross-platform capability-gap; skipped without Docker/gVisor/cluster signals

docs/
├── config/
│   ├── sandbox-worker-fleet.md      ← NEW: operator guide for execution workers (OS/toolchain/runtime advertisement)
│   └── distributed-execution.md     ← NEW: center↔worker execution topology, capability routing, return path
└── security/
    └── 2026-10-DD-distributed-secure-execution.md ← NEW: security-auditor CRITICAL threat model (arbitrary exec + bidirectional payload)

docs/roadmap/README.md               ← updated: Milestones table row + footnote
docs/README.md                       ← updated: roadmap table row + ADR table row
docs/adr/README.md                   ← updated: ADR inventory row
```

> **Build chores moved here from Milestone 0001 (with the extraction):**
> `Makefile` `build-sandbox-images`, the per-language image Dockerfiles
> (`cpp20`/`python311`/`java21`/`typescript5`), and the `--network=none --cap-drop
> ALL --read-only` sandbox-hardening checklist item (formerly Milestone 0001
> Task 9 deliverable 4 / Task 9 success criteria). They are owned by Task 04.0 /
> Task 11.0 here.

---

## Global acceptance criteria

- [ ] **Extends, not duplicates, ADR 0007.** `ExecutionTask`/`ExecutionResult` are
      subtypes of ADR 0007's `TaskAssignment`/`TaskResult`; mTLS, scoped tokens,
      idempotency, backoff, and dead-lettering are reused verbatim; no second
      transport/PKI is introduced (C.C1, ADR §A).
- [ ] **Capability routing:** a `reproduce_crash` task requiring `os=windows` +
      launch-and-instrument is never assigned to a non-Windows or parse-only
      worker; an unmatched task is queued and surfaced as a loud capability gap,
      never downgraded (C.C2, C.C3).
- [ ] **Sandbox enforcement:** every execution runs with `network=none`,
      `cap_drop=ALL`, read-only root, bounded tmpfs/memory/CPU, a hard timeout, and
      RAII container teardown on crash/timeout/error; the image digest is verified
      and never pulled at runtime; a worker attempting egress is blocked (C.C5).
- [ ] **Live reproduction is genuinely live:** a `reproduce_crash` task launches
      the target under instrumentation and produces a **fresh** dump/stack (not a
      re-parse of a supplied dump), then drives the debug backend to extract it
      (C.C4, C.C5).
- [ ] **Return-path redaction:** no raw dump/log/stack byte appears in any
      `ExecutionResult`, streamed event, worker log, or control-plane log;
      artifacts move only over the authorised content-addressed fetch channel —
      asserted with a hostile artifact fixture carrying seeded secrets/PII (C.C7).
- [ ] **No trust shortcut on ingestion:** a worker-produced dump re-enters through
      the Data Adapter scrub + ADR 0006 MCP chokepoint, not a trusted bypass; a
      tampered `validate_patch` verdict is caught by center-side skeptic/consensus
      before promotion (C.C6).
- [ ] **Credential containment:** an execution-only worker holds no model key and
      no center store credential; a co-hosted payload-tier worker's harness
      credentials are its own (C.C5, C.C8; ADR 0007 §3 hostile-worker fixture).
- [ ] **Co-hosting is optional and independently scheduled:** execution and
      payload-tier capabilities are separately advertised; either can be present
      without the other (C.C8).
- [ ] **Original spec §10 flow preserved across the cluster:** the Code Analyst's
      `probabilistic_fix` is validated (compile/AST-lint) on a worker and the
      correction-retry loop still functions (C.C4, C.C6).
- [ ] **Isolation:** only `cluster/grpc/{client,server}.py` import `grpc`/stubs;
      `sandbox/` imports no `cluster` module; grep-enforced with a red-on-reintroduce
      self-test (C.C10).
- [ ] No raw incident payload, secret, or unredacted model prompt/response reaches
      any log sink; `SensitiveFilter` covers every new sink (C.C9).
- [ ] All new public classes/functions have RST docstrings; `Optional[T]` not
      `T | None`; `from __future__ import annotations` present (C.C9).
- [ ] `ruff` clean; coverage ≥90% on the `sandbox/` strategy family and the
      return-path redaction boundary; 100% branch on the capability-matching router
      and the sandbox-profile enforcement (ADR Coverage).
- [ ] `security-auditor` **CRITICAL** gate passed on the arbitrary-execution
      sandbox and the bidirectional payload boundary; `incident-analyst` pass on
      the reproduce→capture→ingest lifecycle and the dead-letter/escalation path
      (Task 11.0; ADR Links).

---

## Open questions carried from ADR 0008 (flagged, not resolved)

- **Windows-only system requirement vs. cross-platform workers.** Root
  `../CLAUDE.md` states the *current* system requirement is "Windows 10/11 x64"
  only, which is in tension with the already-built Linux/macOS debug backends and
  this milestone's macOS-center / Windows-worker vision. Treated as a pre-existing
  product-README documentation gap for the user to resolve, not something this
  milestone silently changes.
- **ADR 0007 is itself *Proposed* and `cluster/` is unbuilt.** This milestone is
  gated on that package existing; the subtask decomposition pass is deliberately
  timed to follow the `cluster/` build.
