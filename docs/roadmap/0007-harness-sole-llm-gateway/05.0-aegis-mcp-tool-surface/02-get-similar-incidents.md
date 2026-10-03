# 02 — `get_similar_incidents` (incident_similarity)

**Parent task:** 05.0 Aegis MCP Tool Surface
**State:** ⬜ Not started
**Depends on:** 01 (scaffolding)
**Blocks:** 05
**Contracts:** C7, C8

## Objective

Implement the `get_similar_incidents` MCP tool, served by the unchanged
`core/incident_similarity.py`, returning **redacted structured hits** — never raw
prior payloads. This is the user's "load similar issues into context memory"
capability.

## Scope

- Input: the current incident's structured signature inputs (a `dump_hash` or the
  already-extracted brief fields) + an optional `k` and `threshold`. The tool does
  **not** accept raw payload text as input.
- Handler: build the live signature via `signature_from_brief`, load recent reports
  from the relational store (the same `load_recent` path the orchestrator uses),
  and call `analyze_history(...)` → `HistoryAnalysis`. Return
  `HistoryAnalysis.as_context()` restricted to the top-`k` `matched_incidents`
  (`HistoryMatch.as_dict()`-shaped: incident id, similarity, created_at, faulting
  function, code location, failure bucket, root cause).
- **Redaction (C8):** every returned field passes through `mcp/redaction.py`
  (subtask 05) — root-cause and code-location strings may incidentally carry PII/
  secret-looking tokens from historical reports and must be redacted at the
  boundary. Raw stored-report payload text is never read into the response.
- `core/incident_similarity.py` is **read-only** here — no modification (C8).

## Constraints

- The tool is a **read-only context** tool, available to every role's session
  (investigators, skeptic) regardless of trust tier — it returns only redacted
  structured metadata, no raw payload (C8).
- Deterministic: the scoring is the existing pure-function similarity (no network),
  so a seeded history yields a stable response (eases testing).

## Acceptance criteria

- [ ] `get_similar_incidents` returns top-`k` redacted structured hits from
      `analyze_history` (C7).
- [ ] It accepts no raw payload text as input and reads no raw stored-report payload
      into the response (C8).
- [ ] Every returned field passes through `mcp/redaction.py` (C8).
- [ ] `core/incident_similarity.py` is unchanged.
- [ ] A hostile-history fixture (a stored report whose root_cause carries a seeded
      secret) yields a response with the secret redacted (asserted in Task 08.0).
- [ ] `ruff` clean; RST docstrings.
