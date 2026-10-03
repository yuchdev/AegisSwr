# 04 — Hybrid context seeding + token lineage

**Parent task:** 04.0 Panel Rewiring onto Per-Role Sessions
**State:** ⬜ Not started
**Depends on:** 01 (per-role injection); dovetails with Task 05.0 (redaction)
**Blocks:** Task 05.0
**Contracts:** C7, C8, C10, C12

## Objective

Seed each role's session with the **bounded, pre-redacted incident summary** (the
push half of the hybrid context model) and confirm per-role token accounting folds
into the existing tracker — without ever forwarding unredacted payload.

## Scope

- **Bounded push (C7).** At panel resolution, assemble the seed context from
  in-pipeline data already produced: the `IncidentBrief` (`brief.model_dump`) and
  the top-k `HistoryAnalysis.as_context()` hits from `core/incident_similarity.py`
  (the "load similar issues into context memory" phrase → `get_similar_incidents`,
  Task 05.0). Pass it through the Task 05.0 redaction boundary
  (`mcp/redaction.py`) **before** it reaches any session, then hand the redacted
  summary to the `HarnessSession` as the pushed context (subtask 03.0/01).
- **Top-k bound.** Cap the pushed history to a configured `k` (default small, e.g.
  3) and a total byte budget so the seed never exceeds a backend's context window;
  deeper detail is pulled on demand via the MCP surface (C7), not pushed.
- **Token lineage (C10).** Confirm each role session's `CodeResult.token_estimate`
  folds into `token_tracker` via the unchanged `_fold_turn`; `RCAReport`
  `total_input_tokens`/`total_output_tokens` keep their meaning across N per-role
  sessions (sum over roles, as today over rounds).
- **No unredacted forward.** Assert (hostile-fixture test, Task 08.0) that the
  seed handed to any session contains no raw dump/log/stack bytes and no seeded
  secret/PII — only the redacted brief + redacted structured history hits.

## Constraints

- The push reuses the **same** redaction boundary as the MCP tools (C8); redaction
  is not re-implemented here.
- No raw payload/summary text is logged; `SensitiveFilter` on every sink (C12).

## Acceptance criteria

- [ ] Each role session is seeded with the redacted `IncidentBrief` + top-k redacted
      history hits (C7).
- [ ] The pushed summary is bounded by `k` and a byte budget; deeper detail is
      pull-only via MCP (C7).
- [ ] The seed passes through `mcp/redaction.py` before reaching any session (C8).
- [ ] Per-role `token_estimate` folds into `token_tracker`; `RCAReport` token totals
      sum correctly over roles (C10).
- [ ] A hostile fixture confirms no raw payload/secret in the seed (C8; full
      assertion in Task 08.0).
- [ ] `ruff` clean.
