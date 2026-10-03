# 05 — Milestone closeout + CHANGELOG

**Parent task:** 10.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** all prior tasks
**Contracts:** all (verification)

## Objective

Close the milestone: verify every global acceptance criterion, record the
milestone's decisions of record in `status.md`, and add the CHANGELOG entry.

## Scope

- Walk the [plan.md Global acceptance criteria](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
  checklist and record evidence for each (grep/no-key-boot/panel-parity/trust-tier/
  redaction/autonomy-gate), mirroring the Milestone 0004 "Global-acceptance
  verification (spot-checked)" closeout.
- Fill in `status.md`'s per-task detail (Delivered + key decisions + test coverage),
  flip each task's status cell, and resolve or carry forward each of the four
  flagged open items (session statefulness, MCP authz, selector naming,
  `analyze_incident` recursion) with the decision actually taken.
- Confirm the required review gates ran: `security-auditor` on the MCP surface
  (Task 05.0) and every autonomy escalation (Task 07.0); `incident-analyst` on the
  autonomy-stage lifecycle; `feature-reviewer` on the panel rewiring.
- `CHANGELOG.md`: add a Milestone 0007 entry naming all ten tasks, the four deleted
  reasoning paths, the sole-gateway/no-key posture, the trust-tier amendment to
  0005 C2, the MCP redaction surface, and the Stage 0/1 autonomy scaffolding; record
  the supersession of Milestone 0003's dispatch tasks.
- Final `ruff check . && uv run pytest -q --cov` clean per `.claude/CLAUDE.md` §4;
  `check_doc_links.py` clean across `docs/`.

## Acceptance criteria

- [ ] Every plan.md global acceptance criterion is verified with recorded evidence.
- [ ] `status.md` per-task detail is filled; all task cells reflect final state;
      the four open items are resolved/carried with the decision taken.
- [ ] `security-auditor` (MCP + autonomy) and `incident-analyst` (autonomy
      lifecycle) gates passed; no CRITICAL open at merge.
- [ ] `CHANGELOG.md` carries the Milestone 0007 entry.
- [ ] `ruff` + full test suite + `check_doc_links.py` clean.
