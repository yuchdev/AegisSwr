# 0008 - Distributed secure execution: cross-platform sandbox workers that reproduce, capture, and validate on the center's behalf

> **Status:** Proposed
>
> **Date:** 2026-10-03
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

Milestone 0001's former **Task 9 — Secure Code Sandbox** (never started; full
original scope in [implementation_spec.md §10](/docs/specs/implementation_spec.md))
was narrow: when the Code Analyst agent produces a `probabilistic_fix` (a unified
diff), a **local** Docker executor (`sandbox/executor.py`,
`sandbox/validators.py`, per-language images `cpp20`/`python311`/`java21`/
`typescript5`) compiles-and-AST-lints the patch
(`docker run --rm --network=none --read-only …`, images pre-built never pulled at
runtime) and returns a `ValidationResult { passed, exit_code, compiler_output,
lint_findings }` so the panel can include or correct the candidate before the
report. That is a single-host, single-shot, compile-only check.

The user's directive expands this into a **distributed, cross-platform execution
architecture**. A single **analytical center** instance — the one that runs the
agentic forensic panel (the LLM debate of ADR 0006) — must be able to delegate
**execution work** to one or more **sandbox worker** instances that may run on an
entirely different OS/platform than the center (the user's example: center on
macOS, worker on Windows). The worker's job spans a spectrum well beyond the
original compile check:

1. **Patch validation** (the original Task 9 scope) — compile/AST-lint a
   candidate patch in a network-isolated container.
2. **Live reproduction** — actually *run the target application under
   instrumentation* to reproduce a crash, as opposed to parsing an existing dump
   file post-mortem (which is all today's `backends/debug/{cdb,gdb,lldb}_worker.py`
   do, locally — see *Terminology* below).
3. **Fresh artifact capture** — capture the crash dump, stack traces, and logs
   produced by that live run and ship them back to the center for the panel to
   consume.

This milestone has been **extracted from Milestone 0001** and renumbered into its
own [Milestone 0008](/docs/roadmap/0008-distributed-secure-execution/plan.md);
this ADR is its decision record.

### Terminology — "worker" in this ADR vs. the debug "workers"

The product already ships files named `backends/debug/cdb_worker.py`,
`gdb_worker.py`, `lldb_worker.py`. Those are **in-process strategy
implementations** that parse an *existing* dump file locally and post-mortem;
they are not network peers and do not launch a target application. This ADR's
"worker" is a **separate Aegis SWR instance** on the network. To avoid collision,
this record calls the former **debug backends** and the latter **sandbox
workers** (or just *workers*). The sandbox worker *uses* the debug backends
internally once it has produced a fresh dump.

### Why this is a different trust/payload problem than ADR 0007

[ADR 0007](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md) already
designed a `cluster/` package: a gRPC mastermind↔worker control plane distributing
**forensic-panel reasoning work**. There, each worker runs its *own* harness-backed
LLM panel over a **redacted incident the mastermind sends in**; the payload flows
**center → worker**, the worker holds harness/LLM credentials, and its output
(`TaskResult`) is a structured, redacted `RCAReport` that the mastermind
re-validates. The trust model is "semi-trusted reasoner."

This milestone inverts the payload direction and escalates the trust problem on
both ends:

- **The worker executes, it does not (only) reason.** A sandbox worker runs an
  **untrusted/candidate patch or the target application itself** — arbitrary code
  execution *by design*. Sandbox escape and host compromise are live per-worker
  concerns independent of OS, a materially higher bar than ADR 0007's
  "reason-over-redacted-text" worker.
- **The artifacts flow back out.** The fresh crash dumps, stack traces, and logs
  a worker captures are **new untrusted data flowing into the center** — exactly
  the hostile incident payload `../CLAUDE.md` §1 mandates treating as attacker-
  influenced. They are not trusted-by-default merely because they came from "our
  own" worker. The **return path** therefore needs the same payload-tier
  redaction/sanitisation discipline that [ADR 0006](/docs/adr/0006-harness-as-sole-llm-gateway.md)
  §C/§D established for data flowing *into* a harness — the mirror image of the
  inbound redaction ADR 0007 applied to `TaskAssignment`.

So the two subsystems share transport, PKI, capability routing, and idempotency,
but differ in **what runs on the worker** (execution vs. reasoning) and **which
direction the hostile payload travels** (out vs. in). That shared/divergent split
is the whole of the Decision below.

### Conventions this design must respect

- **Factory-Strategy for every backend family** (`../CLAUDE.md` Architecture): a
  new execution-capability family follows the same ABC + concrete strategies +
  factory shape as the existing debug/ai/storage families.
- **Hostile-payload posture** (`../CLAUDE.md` §1; 0005 C13): no raw dump/log/stack
  text or secret in any log, exception, control-plane message, or persisted report
  unredacted. `SensitiveFilter` on every sink.
- **RAII via context managers** for every subprocess/socket/container/file
  resource; every external call gets a timeout and a defined failure path; no bare
  `except:`; `asyncio.sleep` for backoff, never `time.sleep` (0005 C13).
- **Single-active-harness-per-process, per trust tier** (0005 C2 as amended by ADR
  0006 §D): a worker that *also* hosts a harness session still selects one active
  backend per tier; the cluster layer composes with that, it does not override it.
- **gRPC control plane + committed-proto + mock-peer seam** already proven in
  `openclaude/grpc/` and adopted by ADR 0007; this ADR reuses it rather than
  inventing a parallel transport.

## Decision

### A. Extend ADR 0007's `cluster/` subsystem; do not build a separate protocol

The distributed sandbox is a **new worker *capability type* inside the existing
`cluster/` package**, not a new protocol. Concretely:

- The mastermind↔worker **gRPC control plane, mTLS, per-worker scoped tokens,
  `task_id` idempotency, bounded-backoff retry, and dead-lettering** (ADR 0007
  §1–§3) are **reused unchanged**. The center of this milestone *is* ADR 0007's
  mastermind; a "sandbox worker" is an ADR 0007 worker that advertises an
  **execution** capability instead of (or in addition to) a reasoning capability.
- A new **`SandboxWorker`** role sits alongside ADR 0007's harness-reasoning
  worker. It is dispatched the same `TaskAssignment` envelope, extended with
  execution-task fields (B.2), and returns the same `TaskResult` envelope,
  extended with an **artifact-reference** payload (B.3).
- **Capability advertisement** (ADR 0007 §4) is the extension point: the existing
  `WorkerCapabilities` handshake gains an execution dimension (C) so the
  mastermind's capability-matched scheduler can route "reproduce on Windows" only
  to a Windows-capable execution worker.

Rationale: one coherent cluster subsystem, reusing the already-designed and
already-security-reviewed transport/trust primitives, is strictly cheaper and
safer than a second bespoke protocol with its own PKI and threat model. **The one
genuinely new thing is the inverted payload direction** — artifacts flow *back* —
which §D handles with a dedicated return-path redaction boundary. Everything else
is an extension of ADR 0007, not a replacement. This ADR therefore
**extends ADR 0007** and inherits ADR 0003/0004/0005's harness/backend conventions
and ADR 0006's trust-tier/redaction posture where noted.

### B. Task and artifact contracts (extend ADR 0007's envelopes)

The authoritative schema is the committed `.proto` (authored in the
implementation milestone); field names here are indicative and extend ADR 0007's
`TaskAssignment`/`TaskResult`.

**`ExecutionTask` (center → worker)** — an `TaskAssignment` subtype carrying:

- `task_id` (UUID4 idempotency key), `incident_id`, `mode` (`IncidentMode`) — as
  ADR 0007.
- `execution_kind` — one of `validate_patch` | `reproduce_crash` |
  `collect_logs` | `collect_stack` (the capability spectrum; extensible enum).
- `required_capability` — the **execution capability descriptor** the task needs
  (C): target OS/arch, debugger toolchain, container runtime, language runtime.
- **Content-addressed input handles, never raw bytes** — e.g. a target-build
  handle, a candidate-patch handle (hash + authorised fetch URI), a symbol-source
  handle. The worker pulls these over the ADR 0006/0007 authorised fetch channel
  into its *own* sandbox; neither the candidate patch nor the target binary
  travels inline in the control-plane message.
- `sandbox_profile` — the enforced isolation posture for the run (D.1):
  `network=none`, `cap_drop=ALL`, `read_only` root, tmpfs size, memory/CPU caps,
  wall-clock timeout, runtime (`docker` | `gvisor`).
- `deadline` / `attempt` — timeout and retry semantics (ADR 0007 §2).

**`ExecutionResult` (worker → center)** — a `TaskResult` subtype carrying:

- `task_id`, status (`passed` | `failed` | `crashed_as_expected` |
  `sandbox_error` | `timeout`).
- For `validate_patch`: the original `ValidationResult { passed, exit_code,
  compiler_output, lint_findings }` (spec §10), **redacted at the worker boundary**
  (D.2) before it leaves the worker.
- For `reproduce_crash` / `collect_*`: **artifact references, not artifact bytes**
  — content-addressed handles (`artifact_hash` + an authorised fetch URI into the
  center-side object store) for each captured dump/stack/log, plus a small
  **redacted structured summary** (fault class, faulting module, frame count,
  symbol-resolution score) so the scheduler and panel can triage without
  fetching. Raw dump/log/stack bytes never travel inline on the control plane.
- `token_estimate` / cost accounting lineage (ADR 0007 §2; 0005 C9) when the task
  also drove a harness session (E).

**Idempotency / retry / dead-letter** are ADR 0007 §2 verbatim: at-least-once
delivery, worker-side dedupe on `task_id` (a redelivered execution task returns
the cached result rather than re-running — important, because re-running arbitrary
code is both expensive and a fresh escape opportunity), bounded exponential
backoff, dead-letter after N attempts to a human-triage queue. A failed
reproduction surfaces loudly; it is never silently dropped.

### C. Cross-platform execution-capability advertisement

ADR 0007's `WorkerCapabilities` handshake gains an **execution capability
descriptor** so the center's scheduler routes by *what a worker can actually do*:

- `os` / `arch` — e.g. `windows/x64`, `linux/x64`, `darwin/arm64`.
- `debug_toolchain` — which debug backends are present and usable for *live*
  instrumentation (not just post-mortem parsing): `cdb`/`windbg_js` (Windows),
  `gdb` (Linux), `lldb` (macOS), with a boolean distinguishing **parse-only** from
  **launch-and-instrument** capability per toolchain.
- `container_runtime` — `docker` / `gvisor` / none; `gvisor` advertises a stronger
  escape boundary and lets the scheduler prefer it for untrusted-patch execution.
- `language_runtimes` — the per-language patch-compile images available
  (`cpp20`/`python311`/`java21`/`typescript5`, extensible).

**Routing rule (extends ADR 0007 §4):** an `ExecutionTask` is assigned only to a
worker advertising a capability descriptor that *satisfies* its
`required_capability`. "Reproduce this crash against a Windows build" is routed
only to a worker advertising `os=windows` **and** a launch-and-instrument Windows
`debug_toolchain`. If no worker satisfies the descriptor, the task is **queued and
surfaced as a loud capability gap** (ADR 0007's no-downgrade stance) — never run
on a mismatched platform, never silently degraded from reproduce to parse-only.

### D. Security — a bidirectional hostile-data problem, both halves designed

**D.1 — Execution sandbox posture (the worker runs arbitrary code).** Every
execution task runs inside the `sandbox_profile` isolation (B.2), enforced at the
worker boundary and inherited from spec §10 and ADR 0006 §D:

- `network=none` (no egress), `cap_drop=ALL`, read-only root FS, size-bounded
  tmpfs, memory/CPU caps, hard wall-clock timeout, RAII teardown of the container
  on every exit path (including crash/timeout).
- Images are **pre-built and never pulled at runtime** (spec §10); the worker
  verifies the image digest it is about to run.
- `gvisor` is **preferred** for untrusted-patch and target-application execution
  where advertised (C); plain Docker is the floor. Running a target application
  *to crash it* is the maximal-risk case and is the one `security-auditor`
  CRITICAL gate item of this milestone.
- The worker holds **only its own execution credentials and its scoped token**
  (ADR 0007 §3): no center store credentials, no other incident's data, no other
  worker reachable. mTLS + per-task scoped tokens are reused verbatim.

**D.2 — Return-path redaction (artifacts are new hostile inbound payload).** This
is the inversion ADR 0007 did not have to solve. Captured dumps, stacks, and logs
are treated **exactly like any freshly ingested incident payload**:

- The worker **redacts at its own boundary** before anything leaves it: the
  structured summary in `ExecutionResult` carries only redacted/structured fields;
  `SensitiveFilter` covers the worker's gRPC and log sinks; no raw artifact byte
  appears in a control-plane message or a worker log.
- Raw artifact bytes move **only** over the authorised content-addressed fetch
  channel into the center-side object store, and on **center-side ingestion** they
  re-enter the pipeline through the **same payload-tier path** ADR 0006 mandates:
  the Data Adapter's scrub/noise-filter stages and, for any model-facing use, the
  ADR 0006 §C MCP redaction chokepoint. A worker-produced dump is **not** promoted
  to trusted just because the worker is "ours" — it is re-scrubbed on arrival.
- The center **re-validates worker output** (ADR 0007 §3): a `validate_patch`
  verdict or a reproduction summary is semi-trusted input; the deterministic
  skeptic/consensus layer (ADR 0006 §B.4) still arbitrates, and a tampered or
  malfunctioning worker cannot inject an unvetted conclusion.

### E. Relationship to ADR 0006 trust tiers — co-locatable, logically separate

A sandbox worker and an ADR 0006 **payload-tier harness host** both require the
*identical* Docker-sandboxed posture. This milestone therefore makes them **two
distinct advertised capabilities that MAY be co-hosted on one worker instance**,
not one merged concern:

- A single worker may advertise **both** `execution` (this ADR) and
  `payload-tier harness reasoning` (ADR 0007 over ADR 0006): it can execute a
  candidate patch *and* physically host an OpenHands-backed payload-tier harness
  session, because both run in the same sandboxed runtime it already operates.
- They remain **separate capabilities with separate trust treatments** in the
  `WorkerCapabilities` handshake, so the scheduler routes an execution task and a
  payload-reasoning task **independently** and either can be present without the
  other. A deployment may run execution-only workers (Windows reproduction boxes
  with no LLM credentials) and reasoning-only workers (ADR 0007's original shape)
  side by side.

Rationale: co-location is an efficient, sound **deployment topology** (one
sandboxed host, two jobs) but merging them into a single capability would conflate
two different trust escalations — "runs arbitrary target code" vs. "holds LLM
credentials and reasons over redacted payload" — and break independent scheduling.
Keeping them separable preserves the credential-minimisation posture (an
execution-only worker never needs a model key).

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| **Keep Task 9 as a local-only single-host compile check** (original scope) | Smallest; no network subsystem | Cannot reproduce a crash live, cannot run a Windows target from a macOS center, no fresh-artifact capture — none of the user's directive | Explicitly superseded by the user's cross-instance, cross-platform expansion |
| **Build a fully separate execution protocol** (own transport, own PKI, own threat model) | Clean-slate schema tuned to execution | Duplicates ADR 0007's gRPC control plane, mTLS, token scoping, idempotency, dead-lettering, and its entire `security-auditor` gate; two cluster subsystems to operate and reconcile | Extending ADR 0007's `cluster/` reuses proven, reviewed primitives; the only novel surface (return-path redaction) is additive |
| **Ship raw artifacts inline in `ExecutionResult`** | One hop; no fetch channel | Puts hostile dump/log bytes on the control plane and into its logs; bloats messages; widens the redaction surface exactly where ADR 0007 narrowed it | Return artifact *references*; raw bytes move on one audited content-addressed channel and re-enter via the payload-tier scrub |
| **Trust worker-produced artifacts as "ours"** (skip re-scrub/re-validate) | Less center compute | Violates `../CLAUDE.md` §1 — a freshly captured dump is attacker-influenced; a compromised worker could inject a crafted dump or a false verdict | Re-scrub on ingestion (D.2) and re-arbitrate verdicts center-side (ADR 0006 §B.4) |
| **Merge sandbox-execution and payload-tier harness hosting into one capability** | One worker role to schedule | Conflates two different trust escalations; forces an execution-only worker to also hold LLM credentials; breaks independent routing | Keep them co-locatable but separately advertised capabilities (E) |
| **Plain Docker only; no gVisor path** | Simpler ops | Running a target application *to crash it* is maximal-risk arbitrary execution; a stronger escape boundary is warranted where available | Advertise `container_runtime` and prefer gVisor for untrusted execution where present; Docker is the floor, not the ceiling |

## Consequences

### Positive

- **Cross-platform reproduction.** A macOS analytical center can reproduce a
  Windows-only crash on a Windows worker and ingest the fresh dump — the core
  capability the user asked for.
- **One cluster subsystem.** Transport, PKI, token scoping, idempotency, and
  dead-lettering are ADR 0007's, reused; the net-new surface is small and additive.
- **Bidirectional hostile-data posture is explicit.** The inbound path (ADR 0007)
  and the new outbound/return path (D.2) both carry redaction and
  re-validation; "our own worker" earns no trust shortcut.
- **Credential minimisation holds.** Execution-only workers need no model key;
  co-hosting with a payload-tier harness is a topology choice, not a requirement.
- **The Code Analyst integration point is preserved.** The original §10 validate-
  patch flow still exists — now as one `execution_kind` dispatched to a worker,
  with the correction-retry loop intact.

### Negative

- **A materially higher security bar than ADR 0007.** Arbitrary code execution by
  design (running a target application to crash it) is the single biggest attack
  surface the product has introduced; it carries a `security-auditor` CRITICAL
  gate and a dedicated threat model.
- **Operational weight.** Cross-platform worker fleets, pre-built per-language and
  per-OS images, image-digest verification, and gVisor availability are new
  operational dependencies and failure modes on top of ADR 0007's PKI/lifecycle.
- **A second audited payload channel in the *opposite* direction.** The return
  fetch channel for artifacts must carry the same guarantees as ADR 0006/0007's
  inbound channel, doubling the redaction/authz surface to review.
- **Reproduction is non-deterministic and expensive.** Live crash reproduction may
  be flaky; idempotent dedupe on `task_id` avoids re-running arbitrary code, but a
  genuine retry re-opens an escape opportunity and costs real wall-clock.
- **Windows-only-vs-cross-platform tension inherited, not resolved** (see
  *Open questions*).

### What ADR 0007 / 0006 contracts this ADR extends (explicit)

- **ADR 0007 §4 (`WorkerCapabilities`)** — extended with the execution capability
  descriptor (C); routing rule extended to execution tasks.
- **ADR 0007 §2 (`TaskAssignment`/`TaskResult`)** — extended with `ExecutionTask`/
  `ExecutionResult` subtypes (B); idempotency/backoff/dead-letter reused verbatim.
- **ADR 0007 §3 (semi-trusted worker, mTLS, scoped tokens, output re-validation)**
  — reused verbatim and extended with return-path artifact redaction (D.2).
- **ADR 0006 §C/§D (MCP redaction chokepoint, payload trust tier, sandbox
  mandatory for payload)** — the return path re-enters through this exact path;
  a co-hosted payload-tier harness obeys it unchanged (E).
- **spec §10 (local sandbox)** — becomes the `validate_patch` execution kind and
  the floor isolation profile; its `ValidationResult` schema is retained.

## Future scope

- **Stage 2/3 autonomous remediation on a worker** (ADR 0006 §E Stage 2/3,
  executed in the sandbox) inherits all of ADR 0006's gating and ADR 0007's
  dead-letter/escalation path; not enabled by this ADR.
- **Worker-pool autoscaling / work-stealing** beyond capability-matched dispatch
  (ADR 0007 future scope, shared here).
- **Record/replay determinism** for flaky reproductions (e.g. `rr` on Linux, Time
  Travel Debugging on Windows) as a later execution kind.
- **Durable broker** behind the control plane for execution-intake survival across
  a center restart (ADR 0007 future scope; the task contract already allows it).
- **Resolving the Windows-only system requirement** in root `../CLAUDE.md` against
  the cross-platform worker fleet (Open questions) — a documentation decision for
  the user, out of scope here.

## Validation / Rollout

- **Capability routing:** a `reproduce_crash` task requiring `os=windows` +
  launch-and-instrument is never assigned to a non-Windows or parse-only worker;
  an unmatched task is queued and surfaced, never downgraded (hostile-fixture +
  capability-gap test).
- **Sandbox enforcement:** every execution runs with `network=none`,
  `cap_drop=ALL`, read-only root, bounded tmpfs/memory/CPU, a hard timeout, and
  RAII container teardown on crash/timeout/error; the image digest is verified and
  never pulled at runtime (asserted with a worker fixture that attempts egress and
  is blocked).
- **Return-path redaction:** no raw dump/log/stack byte appears in any
  `ExecutionResult`, streamed event, worker log, or control-plane log; artifacts
  move only over the authorised fetch channel and are re-scrubbed on center
  ingestion (hostile-fixture artifact with seeded secrets/PII).
- **No-trust-shortcut:** a worker-produced dump re-enters through the Data Adapter
  scrub + ADR 0006 MCP chokepoint, not a trusted bypass; a tampered
  `validate_patch` verdict is caught by center-side skeptic/consensus before
  promotion.
- **Credential containment:** an execution-only worker holds no model key and no
  center store credential; a co-hosted payload-tier worker's harness credentials
  are its own (ADR 0007 §3 hostile-worker fixture).
- **Isolation:** only `cluster/grpc/{client,server}.py` import `grpc`/stubs
  (ADR 0007 Validation, extended); `core/`, `views/`, `harness/`, and the backend
  packages import no `cluster` module.
- **Coverage:** ≥90% on the execution-worker strategy family and the return-path
  redaction boundary; 100% branch on the capability-matching router and the
  sandbox-profile enforcement.

## Links

- **Extends:** [ADR 0007 - Multi-instance mastermind/worker protocol](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md)
  (gRPC control plane, mTLS, scoped tokens, capability advertisement, idempotency,
  dead-lettering — all reused; `ExecutionTask`/`ExecutionResult` + execution
  capability descriptor are the extensions)
- **Depends on / inherits:** [ADR 0006 - Harness as sole LLM gateway](/docs/adr/0006-harness-as-sole-llm-gateway.md)
  (payload trust tier, MCP redaction chokepoint, sandbox-mandatory-for-payload,
  staged autonomy — the return path re-enters through these)
- **Harness/backend conventions:** [ADR 0003](/docs/adr/0003-code-intel-composition-root.md),
  [ADR 0004](/docs/adr/0004-harness-composition-generalization.md),
  [ADR 0005](/docs/adr/0005-flake8-lint-adoption.md) (Factory-Strategy, isolation,
  lint posture)
- **Original scope:** [implementation_spec.md §10](/docs/specs/implementation_spec.md)
  (the local secure sandbox; now the `validate_patch` execution kind)
- **Milestone extraction:** [Milestone 0008 plan.md](/docs/roadmap/0008-distributed-secure-execution/plan.md);
  extracted from [Milestone 0001 plan.md](/docs/roadmap/0001-generic-implementation/plan.md)
  (former Task 9)
- **Hostile-payload posture:** `../CLAUDE.md` §1; 0005 C13
- **Follow-up:** hand the `cluster/` execution-worker strategy family,
  `ExecutionTask`/`ExecutionResult` proto extension, capability router, and
  return-path redaction to `python-expert`; mock-peer + hostile-worker +
  return-path-redaction + sandbox-escape suites to `testing-expert`;
  `security-auditor` **CRITICAL** gate on the arbitrary-execution sandbox and the
  bidirectional payload boundary; `incident-analyst` pass on the distributed
  reproduce→capture→ingest lifecycle and the dead-letter/escalation path.

## Open questions (flagged, not resolved here)

- **Windows-only system requirement vs. cross-platform workers.** Root
  `../CLAUDE.md` states the product's *current* system requirement is "Windows
  10/11 x64" only, which is in tension with the already-built Linux/macOS debug
  backends (`gdb_worker.py`, `lldb_worker.py`) *and* this milestone's explicit
  cross-platform (macOS center / Windows worker) vision. This appears to be a
  **pre-existing documentation gap** in the product README, not something this ADR
  should silently resolve; it is surfaced for the user to decide.
