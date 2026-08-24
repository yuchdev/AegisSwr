# 03 – Fluentd record normalization model

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Not started
**Depends on:** none (protocol-agnostic)
**Blocks:** 06, 07, 08

## Objective

Fluentd and Fluent Bit deliver log records as structured JSON objects, not plain
text lines. The shape varies:

- **Fluentd msgpack event stream**: `[tag, time, record]` where `time` is a Unix
  integer (v1) or `EventTime` (v2 msgpack extension type), and `record` is an
  arbitrary JSON object.
- **Fluentd HTTP output**: `[{"tag":…,"time":…,"record":{…}}, …]` JSON array.
- **Fluent Bit JSON output**: `[{"date":…, <flat record fields>}, …]`.

This subtask defines a canonical `FluentRecord` model and a `FluentRecordParser`
that normalises any of these shapes into a plain string log line that the rest of
the Aegis pipeline (Drain3 clustering, severity filtering, `_parse_timestamp`)
can consume without modification.

## Files

- **Create** `src/aegis_swr/backends/log/fluent_record.py`

## Classes / symbols

### `FluentRecord` (Pydantic v2 `BaseModel`)

```python
class FluentRecord(BaseModel):
    """Normalised representation of a single Fluentd / Fluent Bit event.

    :ivar tag: Full event tag (e.g. ``aegis.auth-api``).
    :ivar timestamp: UTC-aware event time.
    :ivar fields: Raw record payload (preserves all original fields).
    :ivar raw_message: The extracted or synthesised log line text.
    """
    tag: str
    timestamp: datetime
    fields: dict[str, Any]
    raw_message: str
```

### `FluentRecordParser`

A stateless utility class (no `__init__` arguments) with class methods only.

```python
class FluentRecordParser:
    """Parses and normalises raw Fluentd / Fluent Bit payloads.

    All methods are classmethods. No network I/O or side effects.
    """

    @classmethod
    def from_http_batch(cls, raw: list[dict[str, Any]]) -> list[FluentRecord]:
        """Parse a list of records as returned by a Fluentd HTTP output plugin.

        Accepts both the ``{"tag":…,"time":…,"record":{…}}`` envelope format
        and the flat Fluent Bit JSON output (``{"date":…, <fields>}``).
        """

    @classmethod
    def from_msgpack_event(
        cls, tag: str, time_value: int | dict[str, Any], record: dict[str, Any]
    ) -> FluentRecord:
        """Parse a single msgpack forward-protocol event triple.

        *time_value* is either a Unix int (Fluentd v1) or a dict carrying
        ``{"type": "EventTime", "second": …, "nanosecond": …}`` (Fluentd v2
        after msgpack extension type decoding).
        """

    @classmethod
    def to_log_line(cls, record: FluentRecord) -> str:
        """Render a FluentRecord as a single plain-text log line.

        Output format (stable, parseable by ``_parse_timestamp``):

        ``<ISO-8601 UTC timestamp> [<tag>] <SEVERITY> <message>``

        e.g. ``2026-05-30T14:00:01Z [aegis.auth-api] ERROR db write failed``

        Field extraction precedence for the message body:
        1. ``record.fields["message"]`` (most Fluentd configs)
        2. ``record.fields["msg"]`` (Zap, logrus)
        3. ``record.fields["log"]`` (Docker/container runtimes)
        4. ``json.dumps(record.fields)`` (fallback - whole payload as JSON)

        Severity token extraction (placed before the message body):
        1. ``record.fields.get("level")`` or ``record.fields.get("severity")``
        2. ``record.fields.get("log_level")``
        3. ``record.fields.get("stream")`` mapped to ``INFO`` (stdout) /
           ``ERROR`` (stderr) for Docker log drivers
        4. Empty string when none of the above is present (the Data Adapter's
           existing ``_severity_rank`` then defaults to INFO rank).
        """

    @classmethod
    def filter_by_window(
        cls,
        records: list[FluentRecord],
        start_time: datetime,
        end_time: datetime,
    ) -> list[FluentRecord]:
        """Return only records whose timestamp falls within [start, end]."""

    @classmethod
    def filter_by_severity(
        cls,
        records: list[FluentRecord],
        severity_levels: list[str],
    ) -> list[FluentRecord]:
        """Return records whose severity token is in *severity_levels*.

        Comparison is case-insensitive. Records with no detectable severity
        are *kept* (same fail-open behaviour as ``FileLogAdapter``).
        """
```

### Timestamp parsing rules

| Input shape | Parser action |
|-------------|---------------|
| `time` is a plain `int` | `datetime.fromtimestamp(time, tz=UTC)` |
| `time` is a `float` | `datetime.fromtimestamp(time, tz=UTC)` |
| `time` is a `str` | `datetime.fromisoformat(time)` (strip trailing `Z` first) |
| `time` is `{"type":"EventTime","second":…,"nanosecond":…}` | `datetime.fromtimestamp(second + nanosecond / 1e9, tz=UTC)` |
| Fluent Bit flat: `date` field present | Same rules applied to `date` |
| None of the above | Raise `FluentRecordParseError` with the raw value |

All produced timestamps are timezone-aware UTC.

### `FluentRecordParseError`

Defined in `core/exceptions.py` (see subtask 04). Raised by `FluentRecordParser`
when a record cannot be normalised (unrecognisable timestamp format, missing
required fields). The adapter catches this and logs a `WARNING` per record,
skipping the unparseable record.

## Constraints

- `FluentRecord` uses `from __future__ import annotations` and `Optional[T]`
  only (not `T | None`).
- `FluentRecordParser` is pure Python with no I/O - fully unit-testable without
  any network or Fluent stack.
- The module **must not** import from `core/data_adapter.py` to avoid a circular
  dependency (`data_adapter` imports from `backends/`). Severity and timestamp
  normalisation logic is local to this module.
- `to_log_line` output format must be parseable by `_parse_timestamp` in
  `core/data_adapter.py` (it produces `YYYY-MM-DDTHH:MM:SS`).

## Tests

**Unit** (`tests/unit/test_fluent_record.py`):

- `test_from_http_batch_standard_envelope` - parse a list of
  `{"tag":"aegis.auth","time":1748606401,"record":{"message":"ok","level":"INFO"}}`
  dicts; assert tag, timestamp (UTC), severity, and message are extracted.
- `test_from_http_batch_fluent_bit_flat` - parse `[{"date":1748606401.5,"msg":"ping","level":"DEBUG"}]`
  (no `tag`/`time` envelope); assert timestamp is correct.
- `test_from_msgpack_event_int_time` - v1 Unix int timestamp → correct UTC datetime.
- `test_from_msgpack_event_eventtime` - v2 `{"type":"EventTime","second":…,"nanosecond":…}` → correct datetime.
- `test_to_log_line_message_field_precedence` - record with `message`, `msg`,
  `log` all set; assert `message` wins.
- `test_to_log_line_fallback_json_dump` - record with no message/msg/log;
  assert output is JSON.
- `test_to_log_line_docker_stream_mapping` - `stream=stdout` → `INFO`; `stream=stderr` → `ERROR`.
- `test_filter_by_window` - 3 records; 2 inside window, 1 outside; assert 2 returned.
- `test_filter_by_severity_case_insensitive` - filter `["error"]`; assert `level=ERROR` line kept, `level=INFO` dropped.
- `test_filter_by_severity_no_level_kept` - record with no level field is *kept*.
- `test_parse_error_on_bad_timestamp` - passing a record with `time="not-a-date"`
  to `from_http_batch` raises `FluentRecordParseError`.

## Success criteria

- [ ] `FluentRecord` model defined with all four fields, correct types, docstrings.
- [ ] `FluentRecordParser` classmethods implemented per spec.
- [ ] `to_log_line` output is parseable by `_parse_timestamp` for all standard
      timestamp formats.
- [ ] All unit tests above pass with zero network calls.
- [ ] `ruff check src/ tests/` - clean.
