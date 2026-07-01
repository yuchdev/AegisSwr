# 02 – `LogBackend` ABC extension: multi-service query contract

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Not started
**Depends on:** 01 (for `LogBackendSettings` fields)
**Blocks:** 06, 07, 08

## Objective

The existing `LogBackend.query_window(service: str, ...)` ABC is a single-service
interface. Incident forensics regularly needs logs from *multiple* subsystems
(e.g. `auth-api`, `order-service`, `db-proxy`) for the same incident window.
Making callers loop sequentially is slow; Fluent adapters can fan out tag queries
concurrently.

This subtask:
1. Adds `query_window_multi` as an abstract method on `LogBackend` with a
   default implementation that fans out to `query_window` concurrently via
   `asyncio.gather`.
2. Provides a typed result container (`MultiServiceLogResult`) so callers can
   inspect per-service line counts and errors without losing provenance.
3. Updates both existing adapters (`FileLogAdapter`, `FluentAdapter`) to inherit
   the default unless they can provide a more efficient implementation.

## Files

- **Modify** `src/aegis_swr/backends/base.py`
- **Modify** `src/aegis_swr/backends/log/file_adapter.py` (no logic change; add docstring note)
- **Modify** `src/aegis_swr/backends/log/fluent_adapter.py` (update stub docstring)
- **Modify** `src/aegis_swr/core/data_adapter.py` (Stage 4 gains multi-service call path)

## Classes / symbols

### `MultiServiceLogResult`

A lightweight dataclass (not Pydantic - no serialisation needed) that holds the
combined result of a multi-service query.

```python
from dataclasses import dataclass, field

@dataclass
class MultiServiceLogResult:
    """Combined result of a multi-service log window query.

    :ivar lines: Flat list of all log lines, sorted by timestamp ascending.
    :ivar per_service: Mapping from service name to its individual lines
        (before merge-sort). Useful for provenance and per-service line counts.
    :ivar errors: Mapping from service name to the exception raised, if any.
        A service that fails is excluded from *lines* and *per_service* rather
        than aborting the entire query (fail-open per service).
    """
    lines: list[str] = field(default_factory=list)
    per_service: dict[str, list[str]] = field(default_factory=dict)
    errors: dict[str, Exception] = field(default_factory=dict)
```

### `LogBackend` additions

```python
async def query_window_multi(
    self,
    services: list[str],
    start_time: datetime,
    end_time: datetime,
    severity_levels: Optional[list[str]] = None,
) -> MultiServiceLogResult:
    """Query multiple services concurrently and return merged results.

    Default implementation fans out to :meth:`query_window` via
    ``asyncio.gather``, collects per-service lines, merges them into a
    single timestamp-sorted list, and captures per-service errors (fail-open:
    a failed service contributes nothing but an entry in ``result.errors``).

    Override in adapters that can issue a more efficient single-round-trip
    batch query (e.g. a Fluent HTTP endpoint that accepts a tag list).

    :param services: Service / subsystem names to query (maps to Fluent tags
        via ``{fluent_tag_prefix}.{service}``).
    :param start_time: Inclusive window start.
    :param end_time: Inclusive window end.
    :param severity_levels: Optional severity filter forwarded to each
        ``query_window`` call.
    :return: :class:`MultiServiceLogResult` with merged lines and per-service
        provenance.
    """
```

**Default body contract** (to be implemented here, not just declared):

```python
import asyncio

tasks = {
    svc: asyncio.create_task(
        self.query_window(svc, start_time, end_time, severity_levels)
    )
    for svc in services
}
result = MultiServiceLogResult()
for svc, task in tasks.items():
    try:
        lines = await task
        result.per_service[svc] = lines
    except Exception as exc:  # noqa: BLE001
        result.errors[svc] = exc
        logger.warning(f"LogBackend: query_window failed for service {svc!r}: {exc}")

# Merge and sort by timestamp prefix (stable sort; lines without timestamps go last)
all_lines = [ln for lines in result.per_service.values() for ln in lines]
result.lines = _sort_log_lines(all_lines)
return result
```

`_sort_log_lines(lines: list[str]) -> list[str]` is a module-level helper in
`backends/base.py` that uses `_parse_timestamp` from `core/data_adapter.py`
(re-exported or duplicated) to key the sort; lines without a parseable timestamp
are appended after all timestamped lines (stable relative order within that group).

### `DataAdapter` Stage 4 update

When `log_backend` is set and `source.metadata.get("services")` is a non-empty
list *or* `settings.backends.log.fluent_services` is non-empty, call
`query_window_multi` instead of `query_window`. The merged `result.lines` are
fed into the existing Drain3 clustering path. Per-service errors are logged as
warnings but do not abort the pipeline.

```python
# Stage 4 (existing): single-service path
if log_backend and service and incident_timestamp:
    lines = await log_backend.query_window(service, t_start, t_end, severities)

# New: multi-service path (takes precedence when services list is available)
if log_backend and services and incident_timestamp:
    result = await log_backend.query_window_multi(services, t_start, t_end, severities)
    if result.errors:
        for svc, err in result.errors.items():
            logger.warning(f"Stage 4: log query failed for {svc!r}: {err}")
    lines = result.lines
```

The multi-service service list is resolved as:
`source.metadata.get("services") or settings.backends.log.fluent_services or ([service] if service else [])`.

## Constraints

- `MultiServiceLogResult` lives in `backends/base.py` alongside the ABC (no
  separate module needed).
- The default `query_window_multi` must not introduce `asyncio` import at module
  level if it is not already present; use `import asyncio` inside the method or
  at module top.
- `_sort_log_lines` reuses `_parse_timestamp` from `core/data_adapter.py` - do
  not duplicate the regex. The simplest approach is to import the function
  directly; it is already module-level.
- `FileLogAdapter` does not need to override `query_window_multi`; the default
  fan-out is correct.
- The stub `FluentAdapter` should document that its eventual override will issue
  a single batch HTTP request when the server supports it.

## Tests

**Unit** (`tests/unit/test_log_backends.py`):

- `test_query_window_multi_merges_lines` - create a `FileLogAdapter` with two
  service log files; call `query_window_multi(["svc-a", "svc-b"], ...)` and
  assert `result.lines` contains lines from both, `result.per_service` has
  both keys.
- `test_query_window_multi_fail_open` - patch `query_window` on one service to
  raise `IOError`; assert that the other service's lines still appear in
  `result.lines`, and the failed service appears in `result.errors`.
- `test_query_window_multi_sort_order` - two services each returning one line
  with distinct timestamps; assert `result.lines` is sorted ascending.
- `test_query_window_multi_no_timestamp_lines_appended_last` - a line without a
  timestamp should appear after all timestamped lines.
- `test_data_adapter_uses_multi_when_services_list_provided` - patch
  `log_backend.query_window_multi` on a mock adapter; confirm Stage 4 calls
  `query_window_multi` (not `query_window`) when `source.metadata["services"]`
  is set.

## Success criteria

- [ ] `MultiServiceLogResult` dataclass exists in `backends/base.py` with
      `lines`, `per_service`, `errors` fields as specified.
- [ ] `LogBackend.query_window_multi` is abstract with the default implementation
      above.
- [ ] `FileLogAdapter` and `FluentAdapter` inherit the default without override.
- [ ] `DataAdapter.process` calls `query_window_multi` when a services list is
      available.
- [ ] All unit tests above pass; `mypy --strict` clean.
