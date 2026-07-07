# 08 – `FluentAdapter` full implementation

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Blocked - requires answers to [05-design-clarifications.md](05-design-clarifications.md) and completion of 06 and/or 07
**Depends on:** 01, 02, 03, 04, 06 (HTTP path) or 07 (forward path)
**Blocks:** 09, 10

---

## Objective

Replace the current `FluentAdapter` stub (which raises `NotImplementedError`) with
a production implementation that:

1. Selects the correct protocol client (`FluentHttpClient` or
   `FluentForwardClient`) based on `settings.fluent_protocol`.
2. Constructs the full Fluentd tag from `fluent_tag_prefix` + service name.
3. Calls the chosen client, parses the raw records via `FluentRecordParser`,
   applies window and severity filters, converts to log lines, and returns them.
4. Implements the efficient `query_window_multi` override when the server
   supports batch queries (Q4 answer).
5. Maps all exceptions to the hierarchy from subtask 04 and fails open per
   subtask 04's contract.

## Files

- **Modify** `src/aegis_swr/backends/log/fluent_adapter.py` (replace stub body)

## Class: `FluentAdapter(LogBackend)`

```python
class FluentAdapter(LogBackend):
    """Production Fluentd / Fluent Bit log backend.

    Queries a Fluentd HTTP endpoint or forward-protocol port for log lines
    within a configurable time window, filtered by service tag and severity.

    The protocol client is selected by ``settings.fluent_protocol``:
    - ``"http"`` → :class:`~.fluent_http_client.FluentHttpClient`
    - ``"forward"`` → :class:`~.fluent_forward_client.FluentForwardClient`

    :param settings: :class:`~aegis_swr.config.settings.LogBackendSettings`
        providing all connection and query parameters.
    """

    def __init__(self, settings: LogBackendSettings):
        self._settings = settings
        _validate_fluent_settings(settings)  # raises ValueError if host/port missing

    async def query_window(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
    ) -> list[str]:
        """Query one service tag and return normalised log lines.

        Builds the full tag from ``settings.fluent_tag_prefix`` and *service*,
        queries the configured protocol client, parses records via
        :class:`~.fluent_record.FluentRecordParser`, and returns plain-text lines.

        Fails open: on any :class:`~aegis_swr.core.exceptions.LogBackendError`,
        logs a WARNING and returns ``[]``.
        """

    async def query_window_multi(
        self,
        services: list[str],
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
    ) -> MultiServiceLogResult:
        """Query multiple services.

        If Q4 confirms the server supports batch queries and
        ``settings.fluent_protocol == "http"``, override the default fan-out
        with a single ``FluentHttpClient.query_batch`` call.
        Otherwise delegate to the default fan-out from :class:`LogBackend`.
        """
```

### Tag construction

```python
def _build_tag(self, service: str) -> str:
    prefix = self._settings.fluent_tag_prefix
    # Sanitise service name per Q6 decision (strip path separators, spaces)
    safe_service = _sanitise_service_name(service)
    if prefix:
        return f"{prefix}.{safe_service}"
    return safe_service

def _sanitise_service_name(name: str) -> str:
    """Strip characters not valid in a Fluentd tag component.

    Fluentd tags use '.' as separator; replace '/', '\\', spaces with '-'.
    Reject names that are empty after sanitisation.
    """
```

### Protocol client lifecycle

`FluentAdapter` creates a new client per `query_window` call and uses it as an
async context manager. This avoids holding a persistent connection (which could
be idle for hours between incident analyses) and simplifies timeout enforcement:

```python
async def query_window(self, service, start_time, end_time, severity_levels=None):
    tag = self._build_tag(service)
    levels = severity_levels or self._settings.default_severity_levels
    try:
        async with self._make_client() as client:
            raw_records = await client.query(
                tag, start_time, end_time, levels,
                max_lines=self._settings.fluent_max_lines_per_service,
            )
    except LogBackendError:
        raise
    except Exception as exc:
        raise FluentConnectionError("Fluent query failed", cause=exc) from exc

    records = FluentRecordParser.from_http_batch(raw_records)  # or from_msgpack
    filtered = FluentRecordParser.filter_by_window(records, start_time, end_time)
    if levels:
        filtered = FluentRecordParser.filter_by_severity(filtered, levels)
    return [FluentRecordParser.to_log_line(r) for r in filtered]

def _make_client(self):
    if self._settings.fluent_protocol == "http":
        return FluentHttpClient(self._settings)
    return FluentForwardClient(self._settings)
```

### Pre-flight validation

```python
def _validate_fluent_settings(settings: LogBackendSettings):
    if not settings.fluent_host:
        raise ValueError("FluentAdapter requires fluent_host to be set")
    if not settings.fluent_port:
        raise ValueError("FluentAdapter requires fluent_port to be set")
```

## Constraints

- The stub's `NotImplementedError` is removed entirely.
- The constructor warning log (`"FluentAdapter is a stub"`) is replaced with an
  `INFO` log confirming the protocol and host that will be used.
- `query_window` always returns a `list[str]`, never raises (fail-open contract).
- `query_window_multi` batch override is conditional on Q4 answers; the default
  fan-out from subtask 02 is always the fallback.
- All exceptions caught and re-raised as `LogBackendError` subclasses; raw
  network/library exceptions never escape.

## Tests

**Unit** (`tests/unit/test_log_backends.py` - extend existing test module):

- `test_fluent_adapter_query_window_happy_path` - patch `FluentHttpClient` to
  return a list of raw record dicts; assert returned log lines contain expected
  text.
- `test_fluent_adapter_selects_http_client` - `fluent_protocol="http"` → creates
  `FluentHttpClient` (verify via mock).
- `test_fluent_adapter_selects_forward_client` - `fluent_protocol="forward"` →
  creates `FluentForwardClient`.
- `test_fluent_adapter_fail_open_on_connection_error` - patch client to raise
  `FluentConnectionError`; assert `query_window` returns `[]`.
- `test_fluent_adapter_fail_open_on_timeout` - same for `FluentTimeoutError`.
- `test_fluent_adapter_tag_constructed_correctly` - `fluent_tag_prefix="aegis"`,
  service `"auth-api"` → tag `"aegis.auth-api"`.
- `test_fluent_adapter_tag_prefix_none` - `fluent_tag_prefix=None`, service
  `"auth-api"` → tag `"auth-api"`.
- `test_fluent_adapter_missing_host_raises_value_error` - constructor raises
  `ValueError` when `fluent_host` is not set.
- `test_fluent_adapter_service_name_sanitised` - service with `/` in name is
  sanitised before tag construction.
- `test_fluent_adapter_multi_batch_override` - if server returns batch result,
  `query_window_multi` calls `query_batch` not N × `query`.

## Success criteria

- [ ] `FluentAdapter.query_window` is fully implemented (no `NotImplementedError`).
- [ ] Protocol selection driven by `settings.fluent_protocol`.
- [ ] Tag construction uses `fluent_tag_prefix` + sanitised service name.
- [ ] Fail-open: all `LogBackendError` subclasses return `[]` with a `WARNING` log.
- [ ] No raw network exceptions escape `query_window`.
- [ ] `query_window_multi` batch override implemented if Q4 confirms server support.
- [ ] All unit tests above pass; `replace_optional.py --check` clean.
