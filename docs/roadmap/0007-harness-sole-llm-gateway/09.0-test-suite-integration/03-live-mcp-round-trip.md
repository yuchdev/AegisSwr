# 03 — Live MCP tool round-trip

**Parent task:** 09.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards)
**Contracts:** C7, C8

## Objective

Verify, against a live harness session acting as an MCP client, that the four Aegis
MCP tools answer a real pull request and that every response crosses the redaction
boundary — using the hostile fixture to prove no seeded secret/PII leaks.

## Scope (`test_live_mcp_round_trip.py`, gated `require_gateway_integration`)

- Stand up the `AegisMcpServer` and have a live harness session call each tool:
  `get_similar_incidents`, `get_event_log`, `get_evidence_slice`, and (behind its
  opt-in, subtask 05.0/04) `analyze_incident`.
- Assert each returns well-formed redacted structured content; assert none of the
  hostile fixture's seeded secrets/PII appears in any response (C8).
- Assert the per-session capability token scopes the session to its own
  `incident_id` — a tool call with a token scoped to a different incident is
  refused loudly.
- Assert `analyze_incident` rejects re-entrant invocation on the active
  `incident_id` (recursion gate, subtask 05.0/04).
- Assert the pushed summary + the pulled tool responses together give the session
  the detail it needs without the full corpus ever being forwarded (C7).

## Acceptance criteria

- [ ] All four tools answer a live pull with redacted structured content (C8).
- [ ] No seeded secret/PII leaks through any tool (hostile fixture) (C8).
- [ ] Cross-incident token calls and re-entrant `analyze_incident` are refused
      loudly.
- [ ] The hybrid push+pull gives the session its detail without full-corpus
      forwarding (C7).
- [ ] Skips cleanly without the integration signal.
