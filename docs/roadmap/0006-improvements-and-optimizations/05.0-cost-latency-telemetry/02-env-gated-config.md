# 02 — Env-gated selection (presence-signal, off by default)

**Parent task:** [05.0 Cost & Latency Telemetry for Harness Events](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Metrics sink + EventBus wiring](01-metrics-sink-eventbus.md)
**Blocks:** none

## Objective

The metrics sink must be strictly opt-in: with no signal set, the orchestrator
constructs no sink, registers no subscription, and behaves exactly as today. Add
the settings + presence-signal gating that selects the sink, mirroring the C2
selection convention Milestone 0005 established — the same pattern the harness
backends use, where a presence-signal env var (`OPENCLAUDE_GRPC_URL`,
`CLAUDE_CODE_ENABLED`, `OPENHANDS_SERVER_URL`, seen across `ci.yml`) turns a
backend on and its absence leaves it off.

## Implementation approach

1. Add a `MetricsSettings(BaseSettings)` to `config/settings.py` following the
   exact shape of the sibling backend settings there — `extra="ignore"`, a
   validated `provider` field, defaults off:

   ```python
   class MetricsSettings(BaseSettings):
       """Opt-in telemetry sink for harness cost/latency events.

       Off unless `provider` is set to a real exporter. Mirrors the presence-
       signal selection convention (C2): absent config => null sink, no
       EventBus subscription, no behavioural change.
       """

       model_config = SettingsConfigDict(extra="ignore")

       provider: str = "none"   # none | prometheus_textfile | statsd

       textfile_path: Optional[str] = None     # prometheus_textfile
       statsd_host: Optional[str] = None        # statsd
       statsd_port: Optional[int] = None        # statsd

       @field_validator("provider")
       @classmethod
       def validate_provider(cls, v: str) -> str:
           allowed = {"none", "prometheus_textfile", "statsd"}
           if v not in allowed:
               raise ValueError(f"metrics provider must be one of {allowed}")
           return v
   ```

   Wire it into `BackendsSettings` (settings.py:551-565) as
   `metrics: MetricsSettings = Field(default_factory=MetricsSettings)`, so it is
   reachable as `settings.backends.metrics` and configurable via
   `AEGIS__BACKENDS__METRICS__PROVIDER=...` (the existing `env_prefix="AEGIS__"`
   / `env_nested_delimiter="__"` convention, settings.py:710-714) **and** via
   `config.json`.

2. `build_metrics_sink(settings)` (subtask 01's factory) returns the `null` sink
   when `provider == "none"` (or the required host/path for the chosen provider
   is absent — a present-but-unconfigured signal is treated as off, logged once).

3. In `orchestrator.py`, construct the sink via the factory and register
   `bus.subscribe(DomainEvent, sink.handle)` **only** when the resolved sink is
   not the null sink; hold the returned unsubscribe for teardown. The null path
   adds one `if` and no subscription — zero behavioural change when off.

## Security / convention notes

- No secret fields here (host/path/port are not credentials), but any future
  authenticated exporter URL must go through `_SECRET_KEYS`/`redacted_dump`
  (settings.py:54, 747-751) so it never prints in `settings.redacted_dump()`.
- Never read `os.environ` directly in the sink or orchestrator for this signal —
  it flows through `MetricsSettings` like every other config value (the same
  rule Task 01.0's `X013` rule will mechanise).

## Exclusions

- Does not add the exporters themselves (subtask 01) or the runbook (subtask 03).
- Does not enable metrics in CI or any default config — it ships off.

## Test plan

- `test_metrics_off_by_default.py`: with no `AEGIS__BACKENDS__METRICS__*` env and
  default `config.json`, assert `build_metrics_sink` returns the null sink and the
  orchestrator registers **no** `DomainEvent` subscription (spy on
  `EventBus.subscribe`).
- `test_metrics_provider_selection.py`: `provider="prometheus_textfile"` +
  `textfile_path` set yields the textfile sink; `provider="statsd"` without
  `statsd_host` falls back to null with a single warning.
- `test_provider_validation.py`: an unknown provider raises `ValueError` at
  settings construction (mirrors `StorageSettings.validate_provider`,
  settings.py:485-492).
- Integration test (mocked external): with the signal set, a full orchestrator
  run registers the subscription and the fake exporter receives the completion
  metrics.
</content>
