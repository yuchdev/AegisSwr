# 03 — Consensus/weight/one-arbiter parity proof

**Parent task:** 04.0 Panel Rewiring onto Per-Role Sessions
**State:** ⬜ Not started
**Depends on:** 01 (per-role injection), 02 (orchestrator wiring)
**Blocks:** Task 08.0
**Contracts:** C6

## Objective

Prove — as the defining acceptance gate of this milestone — that moving the panel
onto per-role harness sessions leaves the deterministic Aegis-side arbitration
**unchanged**: identical weights, the exactly-one-ARBITER invariant, and
byte-for-byte identical `consensus.py` output under identical structured per-agent
input.

## Scope (`tests/unit/agents/test_panel_parity.py`)

1. **Weight parity.** For a representative panel, assert `resolve_consensus_weights`
   returns the same map whether each agent is backed by the old shared backend or a
   per-role `HarnessSessionBackend` (weight is intrinsic `default_weight`, not
   backend-derived — ADR 0002).
2. **One-arbiter invariant.** A panel with zero or two-plus arbiters still raises
   `PanelResolutionError` under per-role injection; a valid panel resolves.
3. **Consensus-output parity.** Drive the full orchestrator graph twice over the
   **same seeded structured per-agent output** — once via `ScriptedAIBackend`
   (standing in for the pre-refactor shared backend) and once via a
   `ScriptedAIBackend`-equivalent *harness double* (a `HarnessSessionBackend` whose
   session returns the identical seeded `CodeResult.content`) — and assert:
   - identical `consensus_score` per round,
   - identical convergence/HITL routing decision,
   - identical final `RCAReport` (modulo non-deterministic ids/timestamps, which
     the test fixes/normalises).
4. **Arbitration stays Aegis-side.** Assert `core/consensus.py` is invoked by the
   arbiter node (not delegated to a harness) and that no harness session is asked
   to "weigh the debate" — the structured `Hypothesis`/`SkepticVerdict` output is
   what `consensus.py` reads (C6).

## Why this is the gate

ADR 0006 §B.4 and the Alternatives table reject moving arbitration into a harness
precisely because it would void the auditable, reproducible consensus. This proof
is the evidence that the inversion preserved it; it is also the parity criterion
named in the ADR Validation/Rollout section.

## Acceptance criteria

- [ ] Weight map is identical under shared-backend vs per-role injection (ADR 0002).
- [ ] One-arbiter invariant holds under per-role injection.
- [ ] `consensus_score`, routing, and final `RCAReport` are byte-for-byte identical
      under identical seeded structured output (ids/timestamps normalised).
- [ ] The test asserts `consensus.py` is the arbiter (arbitration never delegated to
      a harness) (C6).
- [ ] `core/consensus.py` is unedited (assert via a file-level invariant / isolation
      test).
- [ ] `ruff` clean.
