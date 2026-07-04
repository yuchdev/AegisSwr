# Post-Mortem - INC-2026-0611 - 2026-06-11

<!-- Worked example for /post-mortem. Shows the template filled with a blameless
     five-whys chain and owned action items. Fictional incident. -->

- Severity: P1 | Duration: 2h 14m | Detected by: consensus-stall alert | Mode: crash_dump

## Summary

A recurring `use_after_free` crash in the render worker produced repeated
LOW-confidence RCA reports. Because the reports were low-confidence, on-call
initially dismissed them; no `HITLRequest` was surfaced to prompt a human, so the
crash recurred for two hours before escalation.

## Impact

~4% of render requests failed over the window. No data loss. One customer report.

## Timeline (UTC)

| Time | Event | Source |
|------|-------|--------|
| 09:02 | First `use_after_free` crash ingested | RCAReport store |
| 09:03 | Investigation converged LOW; no HITL request | RCAReport `confidence_level` |
| 09:05–11:00 | 6 more identical crashes, each LOW, each dismissed | store + Slack |
| 11:12 | On-call notices recurrence pattern manually | Slack |
| 11:16 | Node drained, service rolled back | deploy log |

## Root cause (five-whys)

1. Why did the crash recur for 2h? → The LOW-confidence reports were dismissed and
   nothing forced a human decision.
2. Why was nothing forced? → No `HITLRequest` was attached — the run *converged*
   at LOW rather than hitting the max-rounds HITL path.
3. Why did it converge at LOW? → The Skeptic confirmed at exactly 0.65 with a
   low consensus score, satisfying `skeptic_confirmed` but producing a weak report.
4. Why did a weak-but-confirmed report ship without escalation? → The escalation
   rule keyed only on the max-rounds path, not on `confidence_level == LOW`.
5. Why was that gap not caught? → No test covered "converged AND LOW" — the
   escalation tests only exercised the max-rounds branch. **(systemic root cause)**

## What went well

- The consensus-stall alert eventually surfaced the pattern.
- Rollback playbook was fast once triggered.

## What went wrong / contributing factors

- Escalation logic had a blind spot for converged-LOW outcomes.
- Recurrence was only noticed by a human eyeballing Slack (dedup did not escalate).

## Action items

| # | Action | Owner | Agent | Tracking |
|---|--------|-------|-------|----------|
| 1 | Escalate to HITL when `confidence_level == LOW` even on convergence | Y. Cherkasov | python-expert | INC-611-1 |
| 2 | Add regression test for "converged AND LOW" escalation | — | testing-expert | INC-611-2 |
| 3 | Runbook: recurring-LOW pattern → manual escalation until #1 ships | — | docs-updater | INC-611-3 |
