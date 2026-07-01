# Runbooks

Operational runbooks for on-call engineers responding to Aegis SWR incidents.

Each runbook documents how to respond to a specific incident or fault class.
Use `/runbook-write <incident-type>` to scaffold a new runbook from the project
template.

## Naming convention

`<fault-class-slug>.md` - e.g. `access-violation.md`, `consensus-timeout.md`,
`hitl-escalation.md`.

## What a runbook must contain

1. **Trigger** - what alert or condition causes a human to open this runbook.
2. **Triage steps** - ordered, copy-paste-safe commands or UI actions.
3. **Escalation path** - when and how to page the next level.
4. **Rollback** - how to undo any remediation that made things worse.
5. **Post-mortem link** - after resolution, file a post-mortem in `docs/post-mortems/`.

<!-- SME REVIEW NEEDED: populate with first runbooks as incidents are resolved. -->
