# 01 — Config reference + migration docs

**Parent task:** 10.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** Tasks 01.0–07.0
**Contracts:** C1, C3, C8, C9, C11

## Objective

Author the operator-facing documentation for the sole-gateway posture, the trust
tiers, the MCP tool surface, and the autonomy stages, plus a migration note for
deployments moving off the deleted direct providers.

## Scope

- `docs/config/harness-gateway.md` (NEW): the sole-gateway posture (Aegis holds no
  model API key; keys live inside each harness), the no-key boot story, and the
  role → harness-session binding table (C1, C3). Include the **migration note**:
  deployments that set `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/AWS creds and selected a
  provider via `AISettings.provider` must move to a harness backend (set the
  relevant presence signal + tier selector); the direct providers and
  `claude_cli_provider` are deleted; the "Claude Code as just an LLM" case is the
  `no_tools` persona.
- `docs/config/harness-selection.md` (UPDATE): extend the existing Milestone-0005
  selection doc with the **two trust tiers**, the per-tier selector env vars
  (`AEGIS_PAYLOAD_TIER_BACKEND`, `AEGIS_TRUSTED_TIER_BACKEND`, the
  `AEGIS_CODE_INTEL_BACKEND` alias), the per-tier truth table, and the payload-tier
  sandbox mandate (C9). State the consequence: a host-only (no Docker) deployment
  runs only trusted-source-tier work.
- `docs/config/mcp-tool-surface.md` (NEW): the four tools, their inputs/outputs, the
  redaction boundary, the capability-token authz, and the `analyze_incident`
  recursion gate (C8).
- `docs/config/autonomy-stages.md` (NEW): the four-stage ramp, the opt-in flags
  (default Stage 0), the per-stage gates (`incident-analyst`, `security-auditor`,
  `/playbook-validate`), and the explicit "Stage 1 candidate patch is never
  executed; Stage 2 is a stub; Stage 3 is a future ADR" scope (C11).

## Constraints

- Absolute-from-repo-root links; `check_doc_links.py` clean.
- No secret/example key appears in any doc; the no-key posture is the point.

## Acceptance criteria

- [ ] `harness-gateway.md`, `mcp-tool-surface.md`, `autonomy-stages.md` created;
      `harness-selection.md` updated with the two tiers (C1, C3, C8, C9, C11).
- [ ] The migration note tells provider-based deployments exactly what to change.
- [ ] `check_doc_links.py` clean on all touched files.
- [ ] No secret/example key in any doc.
