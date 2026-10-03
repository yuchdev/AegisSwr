# Task 05.0 — Cost & Latency Telemetry for Harness Events

**Parent milestone:** [Milestone 0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
**Status:** ⬜ Not started

## Scope

Each harness backend already emits a terminal `*.completed` event carrying a
token figure, but today those events land only on the in-process `EventBus` for
the live view and are, at most, logged. There is nowhere an operator can go
after the fact to answer "cost per incident over the last 30 days" or "which
backend family is slowest under load" without grepping structured logs. This
task adds an **opt-in metrics sink** subscribed to the same `EventBus`, gated
behind its own presence-signal env var, plus the on-call runbook the resulting
dashboard needs. The data already exists at the event-emission boundary — this
task persists it somewhere queryable.

### Re-verification note — built against the amended, existing events

`plan.md`'s original Task 05.0 named `RouterCallCompleted` (a LiteLLM Model
Router event). The inline **2026-10-03 amendment** in plan.md redirects this
task to the *existing* per-backend `*.completed` events, because
[ADR 0006](/docs/adr/0006-harness-as-sole-llm-gateway.md) retires the router
(Milestone 0003 Tasks 03.0–07.0 are superseded). This decomposition is written
against the events that actually ship today. Confirmed present:

| Backend | Completed event (class / `event_type`) | Token field | Other payload-safe fields | File |
|---------|----------------------------------------|-------------|---------------------------|------|
| OpenClaude | `OpenClaudeStreamCompleted` / `openclaude.stream_completed` | `token_estimate` (boundary estimate, C5) | `frame_count`, `truncated` | `openclaude/events.py:148-171` |
| Claude Code | `ClaudeCodeCompleted` / `claude_code.completed` | `token_estimate` (real `input+output`, C9) | `input_tokens`, `output_tokens`, `num_turns` | `claude_code/events.py:202-233` |
| OpenHands | `OpenHandsCompleted` / `openhands.completed` | `token_estimate` (real or boundary; `usage_reported` says which) | `usage_reported`, `event_count`, `truncated` | `openhands/events.py:155-183` |

All three subclass `aegis_swr.core.events.DomainEvent` and carry a
timezone-aware `run_id` + `timestamp`; none carries raw payload (C10/C13). A
future **Milestone 0007** (harness-as-sole-LLM-gateway, not yet implemented)
will add more per-role `*.completed`/adapter-completion events under the same
taxonomy — the sink must be built to consume the *family*, not three hard-coded
classes, so 0007's events are picked up for free.

### Design note — latency is *derived*, not carried

The `*.completed` events carry a token figure and a `timestamp`, but **no
duration field**. "Latency" must therefore be computed by correlating a
session's start event with its completion on the shared `run_id`:
`claude_code.spawned`→`claude_code.completed`,
`openclaude.connected`→`openclaude.stream_completed`,
`openhands.connected`→`openhands.completed`. The sink keys partial state on
`run_id` and emits a latency metric when the matching completion arrives. This
is the non-obvious judgment call in this task and is why subtask 01 subscribes to
the start events too, not just the completions.

## Subtasks

| #  | Name                                                      | Document                                                          | Status         |
|----|----------------------------------------------------------|------------------------------------------------------------------|----------------|
| 01 | Metrics-sink abstraction + EventBus subscription wiring  | [Metrics sink + EventBus wiring](01-metrics-sink-eventbus.md)     | ⬜ Not started |
| 02 | Env-gated selection (presence-signal, off by default)    | [Env-gated metrics config](02-env-gated-config.md)               | ⬜ Not started |
| 03 | On-call dashboard runbook                                | [Telemetry dashboard runbook](03-telemetry-runbook.md)           | ⬜ Not started |

**Sequencing.** 01 defines the sink and its `EventBus` subscription; 02 adds the
presence-signal gating and factory selection that decides *whether* 01's sink is
constructed and wired; 03 documents operating it. 01 → 02 → 03. 03 can be
drafted in parallel once 01's metric names are fixed.

## Key constraints

- **Payload safety is absolute.** The sink reads only the numeric/flag/id fields
  listed above and short backend/role labels — never a field that could carry
  incident text. Metric *label* values must be bounded-cardinality status
  strings (backend name, mode), never `run_id` as a label (that is unbounded and
  would also leak correlation). `run_id` is used for in-memory start/complete
  correlation only, then discarded — it is not exported
  (`.claude/CLAUDE.md` §3; `config/settings.py:_SECRET_KEYS`/`redacted_dump`
  style).
- **Opt-in and off by default.** Absent its presence-signal env var, no sink is
  constructed, no subscription is registered, and behaviour is byte-for-byte
  what it is today — mirroring the C2 selection convention Milestone 0005
  established (presence-signal env vars like `OPENCLAUDE_GRPC_URL` /
  `CLAUDE_CODE_ENABLED` select a backend).
- **A failing sink must never abort an investigation.** It subscribes via
  `EventBus.subscribe`, whose dispatch already wraps each callback in
  try/except and logs-and-skips (`core/events.py:186-190`) — the sink must not
  defeat that by doing blocking I/O on the dispatch thread; writes go to a
  textfile/UDP that cannot stall the pipeline.
- **Factory-Strategy**, like every other backend family: an abstract
  `MetricsSink` base, concrete strategies (e.g. Prometheus textfile, StatsD/UDP,
  a no-op null sink), and a factory keyed off settings.
- This task adds a new consumer only — it does **not** modify the event classes,
  the `EventBus`, or any backend's emission logic.

## Files created or modified by this task

```
src/aegis_swr/backends/metrics/        ← NEW family (Factory-Strategy)
├── __init__.py
├── base.py                            ← MetricsSink ABC: handle(event) contract
├── prometheus_textfile.py             ← concrete strategy (textfile exporter)
├── statsd.py                          ← concrete strategy (UDP; non-blocking)
├── null.py                            ← no-op sink (off-by-default path)
└── factory.py                         ← build_metrics_sink(settings) selector

src/aegis_swr/config/settings.py       ← new MetricsSettings (presence-signal
                                          field + provider validator); wired into
                                          BackendsSettings

src/aegis_swr/core/orchestrator.py     ← constructs the sink via the factory and
                                          registers its EventBus subscription when
                                          the presence signal is set (else skipped)

docs/runbooks/cost-latency-telemetry.md   ← NEW: the first runbook content file
                                             (docs/runbooks/ currently holds only
                                             the index README)

tests/unit/backends/metrics/           ← NEW: sink unit tests (payload-safety,
                                          latency correlation, off-by-default)
```
</content>
