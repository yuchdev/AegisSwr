# Task 08.0 — Test Suite — Unit

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 Validation/Rollout (grep, no-key boot, panel parity,
trust-tier, redaction, autonomy-gate)
**Contracts:** all — this task is the enforcement mirror of C1–C13.

## Scope

The mock-based unit suite, written **incrementally alongside** Tasks 01.0–07.0
(the 0004/0005 convention) and consolidated here. It directly encodes every check
the ADR's Validation/Rollout section names, so a reviewer can trace each ADR
assertion to a test.

All unit tests pass with **no** API keys, `AEGIS_*_TIER_BACKEND` unset, autonomy at
Stage 0, and no `claude`/Docker/OpenHands available — using `ScriptedAIBackend`
(C2) and `HarnessSessionBackend` doubles.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Grep/import-ban tests](01-import-ban-tests.md) | ⬜ Not started | - |
| 02 | [No-key boot test](02-no-key-boot.md) | ⬜ Not started | - |
| 03 | [Panel parity test](03-panel-parity.md) | ⬜ Not started | - |
| 04 | [Trust-tier enforcement test](04-trust-tier-enforcement.md) | ⬜ Not started | - |
| 05 | [Redaction test (hostile fixture)](05-redaction-hostile-fixture.md) | ⬜ Not started | - |
| 06 | [Autonomy stage-gate test](06-autonomy-stage-gate.md) | ⬜ Not started | - |

The subtasks are independent and co-land with their implementation tasks; this
README is the consolidation point and the coverage-gate owner.

## Coverage gates (ADR)

- ≥90% on the harness adapter (`backends/ai/harness_adapter.py`) and the MCP tool
  surface (`aegis_swr/mcp/`).
- 100% branch on the trust-tier selection (`harness/config.py` per-tier resolution)
  and the autonomy-stage gate (`core/autonomy.py`).
- The full unit suite stays green with every external signal/key unset.

## Files created or modified by this task

```
tests/unit/
├── backends/ai/test_import_bans.py        ← subtask 01
├── test_no_key_boot.py                    ← subtask 02
├── agents/test_panel_parity.py            ← subtask 03 (shared with Task 04.0)
├── harness/test_trust_tier.py             ← subtask 04 (shared with Task 06.0)
├── mcp/test_redaction.py                  ← subtask 05 (shared with Task 05.0)
└── core/test_autonomy.py                  ← subtask 06 (shared with Task 07.0)
```
