# 03 — `get_event_log` + `get_evidence_slice`

**Parent task:** 05.0 Aegis MCP Tool Surface
**State:** ⬜ Not started
**Depends on:** 01 (scaffolding)
**Blocks:** 05
**Contracts:** C7, C8

## Objective

Implement the two on-demand pull tools that let a session fetch deeper run detail
without the full corpus being pushed — both redacted at the tool boundary.

## Scope

### `get_event_log`

- Input: a `run_id`/`incident_id` (opaque handle) + an optional event-type filter.
- Handler: return the structured `DomainEvent` stream for that run (the
  `EventBus`/persisted event log), projected to a **redacted structured** form —
  event type, timestamp, node/agent key, consensus score, status — **never** the
  raw turn text or any payload-bearing field. Mirrors the 0004 Topology-C
  `get_event_log` sketch.

### `get_evidence_slice`

- Input: a `run_id` + a bounded slice selector (e.g. a frame index range, a
  log-line range, or an evidence key) + a hard byte cap.
- Handler: return only the requested bounded slice of evidence text, passed through
  `mcp/redaction.py` (subtask 05) so any secret/PII in the slice is redacted. The
  cap (and a per-session total-bytes budget) prevents a session from pulling the
  whole dump a slice at a time (a confidentiality + context-window guard).
- The slice is drawn from the already-extracted brief/evidence structures, not from
  re-reading the raw dump file.

## Constraints

- Both tools return only redacted content; neither exposes raw dump/log/stack bytes
  (C8).
- `get_evidence_slice` enforces the per-call cap **and** a per-session cumulative
  budget; exceeding the budget is a loud, non-retriable tool failure, not a silent
  truncation that hides the attempt (C8).
- No tool argument or result is logged unredacted (C12).

## Acceptance criteria

- [ ] `get_event_log` returns a redacted structured event projection; no raw turn
      text or payload field (C8).
- [ ] `get_evidence_slice` returns only the requested bounded, redacted slice; the
      per-call cap and per-session budget are enforced (C8).
- [ ] Both route through `mcp/redaction.py` (C8).
- [ ] Exceeding the slice budget is a loud tool failure (not silent truncation).
- [ ] A hostile fixture confirms no raw secret/PII leaves either tool (Task 08.0).
- [ ] `ruff` clean; RST docstrings.
