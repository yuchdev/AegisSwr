# Post-Mortems

Blameless post-mortems for resolved Aegis SWR incidents.

Use `/post-mortem [incident-id]` to scaffold a new post-mortem. The skill
reconstructs a timeline from git log and incident data, runs five-whys, and
produces action items with owners.

## Naming convention

`<YYYY-MM-DD>-<slug>.md` - e.g. `2025-09-12-consensus-deadlock.md`.

## Required sections

1. **Summary** - one paragraph: what happened, impact, duration.
2. **Timeline** - UTC-stamped sequence of events.
3. **Root cause** - the five-whys analysis result.
4. **Contributing factors** - systemic issues beyond the immediate cause.
5. **Impact** - who was affected, for how long, severity.
6. **Action items** - each with an owner, due date, and linked issue.
7. **What went well** - practices that limited impact or accelerated recovery.

## Principles

- Blameless: focus on systems and processes, not individuals.
- Every P0/P1 incident that requires a human page requires a post-mortem.
- Action items must be filed as GitHub issues within 48 hours of the post-mortem.

<!-- SME REVIEW NEEDED: file first post-mortem after first production incident. -->
