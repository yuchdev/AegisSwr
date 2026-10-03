# 05 — Redaction test (hostile fixture)

**Parent task:** 08.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** Tasks 04.0, 05.0
**Contracts:** C7, C8, C12

## Objective

Prove the ADR's "Redaction" criterion: no raw dump/log/stack text reaches any
harness context, log sink, MCP tool response, or persisted report unredacted —
asserted with a **hostile fixture payload** carrying seeded secrets/PII.

## Scope (`tests/unit/mcp/test_redaction.py` + shared hostile fixture)

- Build a hostile incident fixture: a dump/log/stack corpus with seeded secrets
  (an API-key-shaped token, a bearer token, a connection string, a private-key
  block) and PII (emails, IPs) planted in evidence text, stack frames, and a prior
  stored report's `root_cause`.
- **Pushed summary (C7, Task 04.0):** assert the bounded summary seeded into each
  role's session contains none of the seeded secrets/PII and no raw dump/log bytes.
- **MCP tools (C8, Task 05.0):** for all four tools, assert every response field is
  redacted — `get_similar_incidents` (seeded secret in a historical `root_cause`),
  `get_event_log`, `get_evidence_slice` (seeded secret in the slice), and
  `analyze_incident` (redacted structured report). Assert redaction is fail-closed
  (an un-redactable result is dropped loudly, not forwarded).
- **Logs (C12):** capture loguru output across the run and assert none of the
  seeded secrets/PII appears in any log line; `SensitiveFilter` is active on every
  new sink.
- **Persistence:** assert the saved `RCAReport` (and any candidate patch) carries no
  seeded secret/PII.

## Acceptance criteria

- [ ] No seeded secret/PII in any pushed summary (C7).
- [ ] No seeded secret/PII in any of the four MCP tool responses; redaction is
      fail-closed (C8).
- [ ] No seeded secret/PII in any log line; `SensitiveFilter` active on every sink
      (C12).
- [ ] No seeded secret/PII in the persisted report or candidate patch.
- [ ] The hostile fixture is reused by the integration suite (Task 09.0).
