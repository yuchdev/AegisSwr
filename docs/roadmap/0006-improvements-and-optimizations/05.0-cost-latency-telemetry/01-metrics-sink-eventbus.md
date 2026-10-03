# 01 — Metrics-sink abstraction + EventBus subscription wiring

**Parent task:** [05.0 Cost & Latency Telemetry for Harness Events](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** [02 — Env-gated metrics config](02-env-gated-config.md)

## Objective

The three terminal completion events carry token figures that never leave the
in-process bus. `OpenClaudeStreamCompleted` (openclaude/events.py:148-171)
carries `token_estimate`, `frame_count`, `truncated`; `ClaudeCodeCompleted`
(claude_code/events.py:202-233) carries `token_estimate`, `input_tokens`,
`output_tokens`, `num_turns`; `OpenHandsCompleted` (openhands/events.py:155-183)
carries `token_estimate`, `usage_reported`, `event_count`, `truncated`. All
subclass `DomainEvent` and carry `run_id` + `timestamp`. Build a Factory-Strategy
`MetricsSink` family and subscribe it to the `EventBus` so these figures — plus a
*derived* latency — are exported to a queryable sink.

## Interface contract (described, not implemented)

`src/aegis_swr/backends/metrics/base.py`:

```python
class MetricsSink(ABC):
    """Consumes DomainEvents off the EventBus and records numeric metrics.

    Implementations MUST be non-blocking on the dispatch thread and MUST read
    only numeric/flag/id/label fields — never a field carrying incident text.
    """

    @abstractmethod
    def handle(self, event: DomainEvent) -> None:
        """Record metrics for *event*; ignore events it does not care about."""

    def close(self) -> None:
        """Flush/close any underlying resource (RAII; default no-op)."""
```

Subscription is a single registration against the base class, because
`EventBus.publish` walks `type(event).__mro__` and delivers any `DomainEvent`
subclass to a `DomainEvent` subscriber (core/events.py:160-190):

```python
unsubscribe = bus.subscribe(DomainEvent, sink.handle)
```

Subscribing to `DomainEvent` (not to each concrete class) is what makes the sink
**forward-compatible** with Milestone 0007's future `*.completed` events — they
are `DomainEvent` subclasses too, so they arrive with no code change here. The
returned `unsubscribe` callable is stored for RAII teardown.

## Metrics emitted

Per completion event, keyed by a bounded-cardinality `backend` label
(`"openclaude"` / `"claude_code"` / `"openhands"`) and `mode` where available:

- `aegis_tokens_total` (counter) += `token_estimate`.
- `aegis_calls_total` (counter) += 1, labelled by backend and an `outcome`
  (`completed`) — pair with the `*.error` events for a `failed` outcome.
- `aegis_call_latency_seconds` (histogram) — the **derived** latency (see below).
- `aegis_truncated_total` (counter) — from `truncated` where the event has it.

### Latency correlation (the load-bearing design detail)

No completion event carries a duration. The sink keeps a small in-memory map
`run_id → start_timestamp`, populated from the start events
(`ClaudeCodeSpawned` claude_code/events.py:50-72, `OpenClaudeConnected`
openclaude/events.py:42-59, `OpenHandsConnected` openhands/events.py:35-55), and
on the matching completion computes
`(completion.timestamp - start.timestamp).total_seconds()`, emits the histogram
sample, and **deletes the `run_id` entry**. A completion with no recorded start
(e.g. an externally-managed sidecar connected before the sink existed) emits the
token/count metrics but skips latency rather than guessing. The map is bounded by
eviction on completion; add a size cap + oldest-eviction so a stream of
start-without-completion cannot grow it unboundedly.

## Payload-safety rules (enforced in code, asserted in tests)

- Export only the numeric/flag fields enumerated above and the fixed `backend`
  label. Never set `run_id` (or any free-form string) as a metric label —
  `run_id` is used for in-memory correlation only and is discarded after.
- Never call `str(event)` into a metric (a future field could carry text); read
  named numeric attributes explicitly.
- The textfile/UDP write must not block the dispatch thread; a StatsD sink uses
  a non-blocking UDP socket (RAII-managed), a Prometheus-textfile sink writes to
  a temp file and atomically renames.

## Exclusions

- Does not modify event classes, `EventBus`, or backend emission.
- Does not decide *whether* it runs — that gating is subtask 02. Subtask 01
  delivers the sink + a `build_metrics_sink(settings)` factory and the
  orchestrator wiring point; with no presence signal the factory returns the
  null sink (subtask 02 supplies the signal).

## Test plan

- `tests/unit/backends/metrics/test_sink_payload_safety.py`: feed each of the
  three completion events (and a fabricated future `DomainEvent` subclass with a
  text field) and assert the exported metric lines contain **only** the expected
  numeric values and the `backend` label — never any string field, never
  `run_id`.
- `test_latency_correlation.py`: publish `ClaudeCodeSpawned(run_id="r1", t0)`
  then `ClaudeCodeCompleted(run_id="r1", t1)` and assert one latency sample of
  `t1-t0`; publish a lone completion and assert token metrics but **no** latency
  sample; assert the `run_id` map is empty afterward.
- `test_sink_never_aborts.py`: a sink whose write raises must not propagate out
  of `EventBus.publish` (the bus already guards this — assert the investigation
  continues).
- All asserted against an in-memory/fake exporter; no real Prometheus/StatsD
  endpoint (mocked external per `.claude/CLAUDE.md` §4).
</content>
