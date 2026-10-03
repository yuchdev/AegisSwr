# 01 — `AutonomyStage` gate + opt-in flags

**Parent task:** 07.0 Staged Autonomy Scaffolding (Stage 0/1)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03, 04 (this task)
**Contracts:** C11, C9, C12

## Objective

Define `core/autonomy.py`: an `AutonomyStage` enum and a per-deployment opt-in gate
that resolves the active stage from settings, defaulting to **Stage 0 (Analyse)**
and refusing to grant any higher capability without an explicit opt-in.

## Design

```python
class AutonomyStage(IntEnum):
    """The staged-autonomy capability ladder (C11, ADR 0006 §E.9).

    Each higher stage adds exactly one capability tier and is opt-in; Stage 0 is
    the default. Stages 2 and 3 are not executable in this milestone (Stage 2 is a
    stub; Stage 3 is a future ADR).
    """
    ANALYSE = 0           # read-only; RCAReport / HITLRequest (today)
    SUGGEST = 1           # + candidate patch/playbook, never executed
    EXECUTE_VALIDATED = 2 # stub only in this milestone
    AUTONOMOUS = 3        # future ADR; rejected at the gate here


class AutonomyGate:
    """Resolves the active stage from opt-in settings and authorises a capability.

    - Default is ANALYSE when no opt-in flag is set.
    - SUGGEST requires its explicit opt-in flag.
    - EXECUTE_VALIDATED is accepted as a *stage value* only to drive the stub
      (subtask 04); it grants no execution capability in this milestone.
    - AUTONOMOUS is rejected loudly here (a future ADR owns it).
    - execution_allowed() is always False in this milestone (no stage wires it).
    """
```

## Scope

- Add autonomy opt-in flags to settings (default none → Stage 0), e.g.
  `AEGIS_AUTONOMY_STAGE` (default `analyse`) with validation that `autonomous` is
  rejected (future ADR) and `execute_validated` only enables the stub path
  (subtask 04), never real execution.
- `AutonomyGate.requires(stage)` / `authorise(capability)` helpers the orchestrator
  and synthesis path consult: Stage 1's candidate-patch attachment (subtask 02) is
  gated behind `stage >= SUGGEST`; any execution request returns a loud refusal
  (no execution path exists).
- Any stage ≥ 1 requires the execution/scratch tier to be the **payload/sandbox**
  tier (C9); the gate refuses to grant a write-capable stage when no sandboxed
  backend is active.
- Record (in docstrings + the Task 10.0 doc) that stage transitions are
  `incident-analyst` lifecycle changes and capability escalations are
  `security-auditor` gates.

## Acceptance criteria

- [ ] `AutonomyStage` enum + `AutonomyGate` exist in `core/autonomy.py` (C11).
- [ ] Default resolves to Stage 0 (Analyse) with no opt-in flag set.
- [ ] Stage 1 requires an explicit opt-in flag; `autonomous` is rejected loudly.
- [ ] `execution_allowed()` is always `False` in this milestone (no execution path).
- [ ] A write-capable stage is refused when no sandboxed backend is active (C9).
- [ ] 100% branch coverage on the gate (ADR Coverage).
- [ ] `ruff` clean; RST docstrings; `Optional[T]` not `T | None`.
