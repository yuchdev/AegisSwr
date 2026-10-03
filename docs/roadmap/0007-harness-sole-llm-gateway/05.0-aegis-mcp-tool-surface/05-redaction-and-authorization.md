# 05 — Redaction boundary + authorization (security gate)

**Parent task:** 05.0 Aegis MCP Tool Surface
**State:** ⬜ Not started
**Depends on:** 01–04 (every tool routes through this)
**Blocks:** none
**Contracts:** C8, C13, C12
**Gate:** `security-auditor` — CRITICAL blocks merge.

## Objective

Implement `mcp/redaction.py`: the **single** redaction + authorization boundary
every MCP tool response passes through, so no incident byte crosses into a harness
except redacted, `SensitiveFilter`-covered, and authorization-checked — and author
the threat model for the `security-auditor` gate.

## Scope

### Redaction

- A `redact(result)` function applied centrally by the server registration seam
  (subtask 01) to **every** tool result before it leaves the process. It:
  - strips/masks secret-looking tokens (API keys, bearer tokens, connection
    strings, private keys) and PII (emails, IPs where policy requires) from all
    string fields, reusing the project `SensitiveFilter` patterns so the redaction
    set is single-sourced with the log filter;
  - rejects (loud failure) any result still carrying a raw-payload sentinel or a
    field known to hold raw dump/log/stack bytes — redaction is fail-closed, not
    best-effort;
  - is idempotent and deterministic (eases hostile-fixture testing).
- The pushed-summary path (Task 04.0) reuses the **same** `redact` function so push
  and pull share one boundary (C7/C8).

### Authorization (flagged open item)

ADR §C.7 requires the surface be "authorization-checked" but does not specify the
scheme. **Proposed (flag for `security-auditor`):** a per-session capability token
minted by the composition root when it builds a `HarnessSession`, scoping that
session to its own `incident_id` and the tool set its trust tier permits
(`read_only_context` sessions get the read tools; `analyze_incident` requires the
external-orchestrator capability, subtask 04). A tool call presenting a token
scoped to a different incident or lacking the tool capability is a loud
non-retriable failure. A durable cross-process token scheme is deferred to ADR
0007's worker-token design; this milestone's scheme is in-process.

### Threat model

Author `docs/security/2026-10-DD-aegis-mcp-tool-surface.md`: enumerate the new
surface (four tools, transport, token scheme), the redaction fail-closed posture,
the `analyze_incident` recursion gate, and residual risks. This is the artifact the
`security-auditor` reviews; a CRITICAL finding blocks merge.

## Constraints

- Redaction is **fail-closed**: an un-redactable result is dropped with a loud
  error, never forwarded on a best-effort basis (C8).
- The redaction pattern set is single-sourced with `SensitiveFilter` (no second,
  drifting copy) (C12).
- Untrusted payload never reaches a shell/SQL/`eval`/AI prompt un-parameterised
  (`../CLAUDE.md` §3).

## Acceptance criteria

- [ ] Every tool result passes through `redact(...)` centrally; no tool can bypass
      it (C8).
- [ ] Redaction is fail-closed, idempotent, deterministic, and single-sourced with
      `SensitiveFilter` (C8, C12).
- [ ] A per-session capability token scopes each session to its `incident_id` + its
      trust-tier tool set; cross-incident / missing-capability calls fail loud.
- [ ] The authz scheme and `analyze_incident` recursion gate are recorded as flagged
      open items for the `security-auditor` gate.
- [ ] The threat model `docs/security/2026-10-DD-aegis-mcp-tool-surface.md` exists
      and is reviewed; no CRITICAL open at merge.
- [ ] A hostile-fixture suite (seeded secrets/PII in history, evidence, and event
      log) confirms zero leakage across all four tools (Task 08.0).
- [ ] `ruff` clean; coverage ≥90% on the MCP surface (ADR Coverage).
