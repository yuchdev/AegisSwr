# 02 — Stage 1 candidate-patch output on `RCAReport`

**Parent task:** 07.0 Staged Autonomy Scaffolding (Stage 0/1)
**State:** ⬜ Not started
**Depends on:** 01 (`AutonomyGate`)
**Blocks:** Task 08.0
**Contracts:** C11, C9, C12

## Objective

Add the Stage 1 "Suggest" output: an optional **candidate patch/playbook** field on
`RCAReport`, attached by the synthesis path only when Stage 1 is opted in, carrying
a `never_executed` marker — the model proposes a fix, Aegis never runs it.

## Scope

- `core/schemas.py`: add an optional `candidate_remediation` field to `RCAReport`
  (a small Pydantic model carrying the proposed patch/playbook text, a
  `never_executed: bool = True` marker, the originating stage, and a
  `requires_human_review: bool = True` marker). Default `None` so Stage 0 reports
  are unchanged (schema is additive; existing serialisation is backward-compatible).
- `core/orchestrator.py`: in the synthesis path (`_make_synthesizer_node` /
  `_synthesize_remediation`), when `AutonomyGate` resolves `stage >= SUGGEST`,
  attach a `candidate_remediation` produced by a harness session (payload/sandbox
  tier, C9) that may write to **sandbox scratch only**. The existing
  `RemediationPlan` advisory path is preserved; `candidate_remediation` is the
  Stage-1-specific, explicitly-never-executed artifact.
- The existing "never auto-remediate without `AEGIS_PROD_CONFIRMED=1`" rule and the
  `_make_synthesizer_node` "only ATTACHES an advisory plan, never dispatches"
  comment are **preserved and reinforced** — Stage 1 attaches, it does not execute.
- Redaction: the candidate patch text passes through the same redaction boundary
  (Task 05.0) before persistence/emission so it carries no secret/PII (C12).

## Constraints

- Stage 0 behaviour is byte-for-byte unchanged (the field is `None`); the parity
  proof (Task 04.0 subtask 03) must still pass with autonomy at Stage 0.
- No execution path is wired; a Stage 1 candidate patch is inert data (C11).

## Acceptance criteria

- [ ] `RCAReport` gains optional `candidate_remediation` (default `None`); Stage 0
      reports are unchanged and backward-compatible.
- [ ] The synthesis path attaches a candidate patch only when `stage >= SUGGEST`,
      produced on a sandboxed session, marked `never_executed=True` (C11, C9).
- [ ] The "never auto-remediate" rule/comment is preserved and reinforced.
- [ ] The candidate patch is redacted before persistence/emission (C12).
- [ ] The Stage-0 parity proof still passes.
- [ ] `ruff` clean; RST docstrings.
