# Five-whys facilitation guide (blameless)

Backs the "Five why's" step of `/post-mortem`. The goal is to walk from the
observable symptom to a **systemic** root cause, attaching evidence at each step,
without ever landing on a person.

## Method

1. State the symptom as an observable fact ("the investigation emitted a
   LOW-confidence report with no HITL request").
2. Ask "why" and answer with a **contributing factor**, backed by evidence (a log
   line, a commit, a config value, an `RCAReport` field). No evidence → it's a
   guess; mark it as one and go verify.
3. Repeat until the answer is a **system/process** property you can change (a
   missing timeout, an absent test, a routing bug), not "someone forgot".
4. A chain can branch — a symptom may have two independent contributing factors.
   Record both; don't force a single line.
5. Stop when the next "why" would only be "human error". That means you haven't
   reached the systemic cause yet — ask what let the human error reach production.

## Blameless reframing

| Blameful (avoid) | Blameless (use) |
|------------------|-----------------|
| "X deployed a bad config" | "the config change had no validation gate before deploy" |
| "the on-call missed the page" | "the escalation had no timeout, so no second page fired" |
| "the reviewer approved a bug" | "the review had no test covering the escalation branch" |

Each right-hand answer points at an action item; each left-hand one points at a
person and produces nothing.

## Turning whys into action items

Every terminal (systemic) cause should yield at least one action item with an
owner and a tracking issue, routed per the skill: code → `python-expert`, tests →
`testing-expert`, docs/runbooks → `docs-updater`, design → `app-architect`.

## Aegis evidence sources

- `git log --since=<window>` around the incident (what changed).
- Stored `RCAReport`s (filesystem JSON or SQLite): `confidence_level`,
  `consensus_rounds`, `skeptic_challenges`, `hitl_request`.
- `DomainEvent` history if captured (when consensus stalled).
- Runbook/playbook gaps that slowed triage or remediation.
