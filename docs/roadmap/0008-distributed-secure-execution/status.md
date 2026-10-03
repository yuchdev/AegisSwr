# Milestone 0008 — Distributed Secure Execution — Status

Tracks progress against [plan.md](/docs/roadmap/0008-distributed-secure-execution/plan.md).
Updated as each task lands.

## Current status

| Task | Name                                           | Status        | Tests |
|------|------------------------------------------------|---------------|-------|
| 01.0 | Execution Contract & Proto Extension           | ⬜ Not started | -     |
| 02.0 | Execution Capability Advertisement & Routing   | ⬜ Not started | -     |
| 03.0 | Sandbox Execution-Strategy Family              | ⬜ Not started | -     |
| 04.0 | Sandbox Isolation Profile Enforcement          | ⬜ Not started | -     |
| 05.0 | Live Reproduction via Debug Backends           | ⬜ Not started | -     |
| 06.0 | Return-Path Redaction & Artifact Transport     | ⬜ Not started | -     |
| 07.0 | Center-Side Artifact Ingestion & Re-Validation | ⬜ Not started | -     |
| 08.0 | Co-Hosted Payload-Tier Capability (optional)   | ⬜ Not started | -     |
| 09.0 | Test Suite — Unit                              | ⬜ Not started | -     |
| 10.0 | Test Suite — Integration                       | ⬜ Not started | -     |
| 11.0 | Documentation, Security Gate & CI              | ⬜ Not started | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status: ⬜ NOT STARTED (opened 2026-10-03), 0 of 11 tasks.**
This milestone implements [ADR 0008](/docs/adr/0008-distributed-secure-execution-sandbox.md)
and **extends** the `cluster/` subsystem of
[ADR 0007](/docs/adr/0007-multi-instance-mastermind-worker-protocol.md).

## Notes & decisions

- **Origin (2026-10-03).** Extracted from
  [Milestone 0001](/docs/roadmap/0001-generic-implementation/plan.md) — the former
  Task 9 "Secure Code Sandbox" (a local Docker patch-compile check; never started;
  original scope in [implementation_spec.md §10](/docs/specs/implementation_spec.md)).
  Expanded from a single-host compile check into a cross-instance, cross-platform
  distributed execution architecture (analytical center ↔ sandbox workers). The
  build chores that moved with the extraction (per-language sandbox image
  Dockerfiles, `build-sandbox-images` Make target, the `--network=none --cap-drop
  ALL --read-only` hardening checklist item) are now owned by Tasks 04.0 / 11.0.

- **Decomposition level: task-level** (declared in
  [plan.md → Decomposition level](/docs/roadmap/0008-distributed-secure-execution/plan.md#decomposition-level-declared)),
  mirroring Milestone 0005. Subtask decomposition is a deliberate later pass, timed
  to follow the build of ADR 0007's `cluster/` package so the execution-task
  contract is decomposed against real interfaces.

- **Key architectural decisions (ADR 0008).**
  - **Extend ADR 0007's `cluster/`**, do not build a separate protocol (§A): reuse
    gRPC control plane, mTLS, scoped tokens, idempotency, dead-lettering; add
    `ExecutionTask`/`ExecutionResult` subtypes, an execution capability descriptor,
    and a **return-path redaction boundary** (the one genuinely new surface).
  - **Worker capabilities and payload-tier harness hosting are co-locatable but
    logically separate** (§E): one worker may advertise both, scheduled
    independently; an execution-only worker needs no model key.
  - Captured artifacts are **new hostile inbound payload** re-scrubbed on center
    ingestion (§D.2) — no trust shortcut for "our own" worker.

- **External gate.** ADR 0007 is itself *Proposed* and `cluster/` is unbuilt; this
  milestone is gated on that package existing.

## Flagged open items

1. **Windows-only vs. cross-platform tension.** Root `../CLAUDE.md` system
   requirement is "Windows 10/11 x64" only, in tension with the already-built
   Linux/macOS debug backends and this milestone's macOS-center / Windows-worker
   vision. Pre-existing product-README documentation gap — surfaced for the user,
   not resolved here.
2. **Milestone 0001 status.md internal inconsistency (noted, not owned here).** Its
   Task 4 table row reads "🔶 In progress (only cdb complete)" while its detailed
   "Task 4 — Debug Backends ✅" section lists gdb/lldb/windbg_js as delivered. This
   milestone assumes the debug backends exist (it drives them for live
   reproduction) but does not reconcile Milestone 0001's own tracker.
