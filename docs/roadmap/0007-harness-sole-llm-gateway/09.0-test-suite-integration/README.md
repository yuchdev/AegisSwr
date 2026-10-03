# Task 09.0 — Test Suite — Integration

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 Validation/Rollout (live end-to-end verification)
**Contracts:** C1, C6, C7, C8, C9, C11

## Scope

The live integration suite under `tests/integration/harness_gateway/`, **skipped**
(not failed) when a backend's presence signal, binary, or Docker is absent (the
0004/0005 convention). It verifies the inversion end-to-end against a real harness:
a per-role panel driven by harness sessions, the MCP tool round-trip, and a
no-key investigation producing a real `RCAReport`.

The payload-tier suites require **Docker + OpenHands** (the sandboxed payload-tier
backend, C9); the trusted-source suites require a configured host-permission
backend. All are gated behind an explicit `AEGIS_GATEWAY_INTEGRATION` signal plus
the relevant presence signals, and self-skip cleanly otherwise.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [`conftest.py` + skip guards](01-conftest-skip-guards.md) | ⬜ Not started | 02, 03, 04 |
| 02 | [Live per-role harness panel (OpenHands)](02-live-per-role-panel.md) | ⬜ Not started | - |
| 03 | [Live MCP tool round-trip](03-live-mcp-round-trip.md) | ⬜ Not started | - |
| 04 | [End-to-end no-key investigation](04-e2e-no-key-investigation.md) | ⬜ Not started | - |

Subtask 01 (fixtures/skip guards) is the foundation; 02–04 depend on it.

## Contracts touched

- **C1/C9** — the no-key, sandboxed-payload-tier posture is exercised live.
- **C6** — consensus is verified deterministic over real structured session output.
- **C7/C8** — the hybrid push + MCP pull + redaction boundary is verified against a
  real session.

## Key constraints

- Every suite **skips** (never fails/errors) without its signal/binary/Docker.
- The hostile fixture (Task 08.0 subtask 05) is reused to assert no live session,
  log, or tool response leaks a seeded secret/PII (C8).

## Files created or modified by this task

```
tests/integration/harness_gateway/
├── __init__.py
├── conftest.py                       ← skip guards + live fixtures (subtask 01)
├── test_live_per_role_panel.py       ← subtask 02
├── test_live_mcp_round_trip.py       ← subtask 03
└── test_e2e_no_key_investigation.py  ← subtask 04
```
