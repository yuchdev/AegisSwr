# 04 — `analyze_incident` (payload tier + recursion gate)

**Parent task:** 05.0 Aegis MCP Tool Surface
**State:** ⬜ Not started
**Depends on:** 01 (scaffolding)
**Blocks:** 05
**Contracts:** C8, C9

## Objective

Implement `analyze_incident` — the high-level forensic tool that runs Aegis's own
pipeline as a structured sub-capability (the Topology-C inversion) — as a
**payload-tier** tool that runs only on a sandboxed backend, with an explicit gate
against the single-process recursion risk.

## Scope

- Input: a redacted incident handle (`dump_hash` + an authorized reference) + mode;
  the tool does **not** accept raw payload in the call (the redacted-handle pattern
  ADR 0007 uses for task messages, applied here).
- Handler: runs the forensic pipeline for the referenced incident and returns the
  structured, redacted `RCAReport` (+ any `HITLRequest`).
- **Payload tier (C9):** because it ingests raw/attacker-influenced payload
  end-to-end, this tool is **payload-tier** and must execute only on a
  Docker-sandboxed backend (OpenHands). The composition rejects wiring it on a
  host-permission backend (Task 06.0).

## Recursion-risk gate (flagged open item)

ADR §C.6 lists `analyze_incident` among the MCP tools, but in this single-process
ADR the panel **is** the analysis — a harness session calling `analyze_incident`
could trigger a session → `analyze_incident` → panel-of-sessions regress. This is
**underspecified** by the ADR. **Proposed gate (flag for `security-auditor`):**

1. `analyze_incident` is **opt-in**, gated behind an explicit
   "external-orchestrator" deployment flag — intended for an *external* OpenClaude/
   operator driving Aegis as a sub-capability, not for the in-process panel's own
   sessions.
2. When the in-process panel is active, `analyze_incident` **rejects re-entrant
   invocation** keyed on the active `incident_id` (a loud non-retriable tool
   failure), so a panel session cannot recursively re-drive the same incident.
3. A depth/one-shot guard bounds any nested analysis to a single level.

Record the decision in `status.md` → Open items and in the security threat model
(subtask 05); do not enable `analyze_incident` for in-process sessions without the
`security-auditor` sign-off.

## Acceptance criteria

- [ ] `analyze_incident` accepts only a redacted incident handle, returns a redacted
      structured `RCAReport`/`HITLRequest` (C8).
- [ ] It is payload-tier; composition rejects it on a host-permission backend (C9).
- [ ] It is opt-in behind an external-orchestrator flag and rejects re-entrant
      invocation on the active `incident_id` (recursion gate).
- [ ] The recursion posture is recorded in `status.md` and the threat model, flagged
      for `security-auditor`.
- [ ] `ruff` clean; RST docstrings.
