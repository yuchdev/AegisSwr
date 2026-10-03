# 03 — On-call dashboard runbook

**Parent task:** [05.0 Cost & Latency Telemetry for Harness Events](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Metrics sink + EventBus wiring](01-metrics-sink-eventbus.md)
(the runbook documents 01's concrete metric names)
**Blocks:** none

## Objective

`docs/runbooks/` currently contains only its index `README.md` — its own closing
line says *"populate with first runbooks as incidents are resolved"* and no
runbook content file exists yet. This subtask writes the **first** actual runbook
content file: how an on-call engineer reads the cost/latency telemetry this task
unlocks. Scaffold it from the project template via `/runbook-write` so it matches
the five mandatory sections the runbooks index defines (`docs/runbooks/README.md`
"What a runbook must contain").

## Deliverable

`docs/runbooks/cost-latency-telemetry.md`, following the index's required shape:

1. **Trigger** — what opens this runbook: a cost-per-incident spike, a
   backend-latency SLO breach on the `aegis_call_latency_seconds` histogram, or a
   climbing `aegis_truncated_total` (responses hitting the token cap).
2. **Triage steps** — ordered, copy-paste-safe queries against the exporter
   subtask 01 writes: token burn by `backend` label over 30 days
   (`aegis_tokens_total`), p95 latency by backend (`aegis_call_latency_seconds`),
   failure ratio (`aegis_calls_total{outcome="failed"}` vs `completed`). Name the
   exact metric + label set so the queries are concrete, not illustrative.
3. **Escalation path** — when a cost/latency anomaly is a backend regression vs a
   workload change, and who to page (ties into the `pagerduty` MCP context seeding
   in `.claude/CLAUDE.md` §10).
4. **Rollback** — how to disable telemetry fast if the sink itself misbehaves:
   unset `AEGIS__BACKENDS__METRICS__PROVIDER` (back to `none`), which drops the
   subscription on next start with zero investigation impact (subtask 02's
   off-by-default guarantee).
5. **Post-mortem link** — where to file the follow-up (`docs/post-mortems/`).

## Constraints

- The runbook must state the payload-safety guarantee explicitly: the dashboard
  shows counts, token figures, latencies, and bounded backend labels — **never**
  `run_id`, incident content, or any correlatable identifier (`.claude/CLAUDE.md`
  §3). An on-call reader must not expect to pivot from a metric to a specific
  incident's payload; that is by design.
- Every metric name/label referenced must match subtask 01's implementation
  exactly — if 01 renames a metric, this file updates in lockstep (they should
  land together or 03 immediately after).
- Update `docs/README.md`'s index so the new runbook is discoverable (the docs
  mandate, `.claude/CLAUDE.md` §6), and run `/link-check` so the new
  cross-references resolve (Task 06.0's cadence will catch future drift).

## Test plan

- Not code — a documentation deliverable. "Tests" are:
  - `python scripts/check_doc_links.py docs/runbooks/cost-latency-telemetry.md`
    exits 0 (the `doc_link_check` hook / Task 06.0 gate).
  - A `docs-updater`/`feature-reviewer` pass confirming every metric name and
    query matches subtask 01's shipped code (no invented metric names).
  - The five mandatory sections from `docs/runbooks/README.md` are all present.
</content>
