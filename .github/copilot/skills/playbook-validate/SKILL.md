---
name: playbook-validate
description: User-invoked as /playbook-validate <path>. Validates an Aegis remediation playbook or consensus-weight file (e.g. agents.example.json or a playbook YAML/JSON) for step ordering, required fields, idempotency, and rollback coverage. Use before a playbook is trusted to run automated remediation.
allowed-tools: Read, Grep, Glob, Bash
invocation: /playbook-validate <path>
# Ported from Claude (.claude/skills/playbook-validate/SKILL.md) on 2026-07-03
---

# Playbook Validate

Validate the playbook file at the path the user supplied (`$ARGUMENTS`). A
playbook drives automated or semi-automated remediation during an incident, so
a malformed one is a safety hazard.

## Resources

- **`.github/copilot/skills/playbook-validate/references/playbook-schema.md`** — the full
  field vocabulary, the blocking-error vs warning rules, and the ordering heuristic.
- **`.github/copilot/skills/playbook-validate/examples/valid-playbook.yaml`** — passes every rule (expect **VALID**).
- **`.github/copilot/skills/playbook-validate/examples/invalid-playbook.annotated.yaml`** — breaks four rules (expect **INVALID**).

## Checks

1. **Required fields** - each playbook has: `id`, `name`, `trigger`, `steps`, `owner`, `severity`.
   Each step has: `id`, `description`, `action`, `idempotent` (bool), `rollback`,
   `requires_authorisation` (bool), `timeout`.
2. **Step ordering** - steps form a sane sequence: detect/confirm → contain → remediate → verify.
3. **Idempotency** - every step declares `idempotent`.
4. **Rollback** - every state-changing step has a `rollback`.
5. **Authorisation** - any production-affecting step sets `requires_authorisation: true`.
6. **Weight files** - if validating `agents.example.json`-style consensus weights: each fault class's
   agent weights sum to ~1.0 (±0.01) and no single agent exceeds a sane ceiling.

## Output

```
## Playbook Validation - <file>
**Verdict: VALID | INVALID**
### Errors (blocking)
- <field/step> - <problem>
### Warnings
- <improvement>
### Coverage
- steps: N | with rollback: N | idempotent: N | needs-auth: N
```

## Completion checklist

- [ ] Every playbook-level required field checked
- [ ] Every step checked for all 7 required fields
- [ ] Step ordering validated
- [ ] Every state-changing step has a rollback
- [ ] Every step has a bounded timeout
- [ ] Weight files: each fault class sums to `1.0 ± 0.01`
- [ ] Verdict defaults to INVALID on any missing required field or missing rollback
