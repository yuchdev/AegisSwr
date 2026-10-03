# 03 — Panel parity test

**Parent task:** 08.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** Task 04.0 (subtask 03)
**Contracts:** C6

## Objective

Consolidate and own the panel-parity suite (co-authored with Task 04.0 subtask 03):
prove weights, the one-arbiter invariant, and `consensus.py` output are unchanged
under per-role harness sessions.

## Scope (`tests/unit/agents/test_panel_parity.py`)

- Re-run the Task 04.0 subtask 03 assertions as the authoritative milestone gate:
  weight-map parity (ADR 0002), one-arbiter invariant under per-role injection, and
  byte-for-byte identical `consensus_score`/routing/final `RCAReport` under
  identical seeded structured output (ids/timestamps normalised).
- Add a **determinism** assertion: two independent runs over the same seeded
  harness-double output produce identical consensus output (no clock/network
  leakage via the adapter parse, C4 subtask 04).
- Assert `core/consensus.py` is unedited (file-content/invariant check) and that the
  arbiter node calls it (arbitration never delegated to a harness).

## Acceptance criteria

- [ ] Weight/one-arbiter/consensus-output parity holds under per-role sessions (C6).
- [ ] Consensus output is deterministic across repeated seeded runs.
- [ ] `consensus.py` is unedited and is the arbiter.
- [ ] `ruff` clean.
