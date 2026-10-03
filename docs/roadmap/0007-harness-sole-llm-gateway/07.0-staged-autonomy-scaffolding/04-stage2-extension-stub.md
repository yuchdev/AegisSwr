# 04 — Stage 2 extension-point stub (no execution)

**Parent task:** 07.0 Staged Autonomy Scaffolding (Stage 0/1)
**State:** ⬜ Not started
**Depends on:** 01 (`AutonomyGate`)
**Blocks:** none
**Contracts:** C11, C9

## Objective

Provide the Stage 2 **extension point** — a documented hook where
`/playbook-validate` and sandboxed execution will attach — **without building any
execution path**, so a future milestone has a clear seam and this milestone ships
no execution capability.

## Scope

- Define a `PlaybookValidationHook` seam (a protocol/abstract callable) in
  `core/autonomy.py` that a future Stage 2 implementation will supply: given a
  Stage-1 candidate playbook, it would run `/playbook-validate` and gate a
  sandboxed execution. In this milestone the hook has **no concrete
  implementation** — the default is a `NotImplementedError`-raising /
  always-refusing stub that documents where execution attaches.
- `AutonomyGate.execution_allowed()` remains `False` (subtask 01); the stub seam is
  never invoked for real execution. A guard test asserts that selecting
  `execute_validated` reaches the stub and **refuses** (loud), never running
  anything.
- Document (in docstrings + the Task 10.0 autonomy-stages doc) the full Stage 2
  gate chain for the future implementer: `/playbook-validate` passes →
  `HITLRequest` go/no-go → `incident-analyst` lifecycle review → execution **inside
  the sandboxed (OpenHands) runtime only** (C9), non-production target, no
  production credentials.
- Stage 3 is explicitly **out of scope** (future ADR); the stub makes no Stage 3
  affordance beyond rejecting the `autonomous` stage at the gate (subtask 01).

## Constraints

- **No execution code is written.** The stub refuses; it does not run a playbook,
  spawn a process, or call a backend to execute (C11).
- The seam must make the sandbox-only execution constraint (C9) structurally
  obvious to the future implementer (the hook signature carries the sandboxed
  session, not a host one).

## Acceptance criteria

- [ ] A `PlaybookValidationHook` seam exists with a refusing/`NotImplementedError`
      default stub; no execution path is wired (C11).
- [ ] Selecting `execute_validated` reaches the stub and is refused loudly (tested).
- [ ] The full Stage 2 gate chain and the sandbox-only constraint are documented for
      the future implementer (C9).
- [ ] Stage 3 remains out of scope; `autonomous` is rejected at the gate.
- [ ] `ruff` clean; RST docstrings.
