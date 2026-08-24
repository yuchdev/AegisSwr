# 07 – Fluent msgpack forward protocol client

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Blocked - requires answers to [05-design-clarifications.md](05-design-clarifications.md) Q1, Q2, Q5
**Depends on:** 01, 03, 04, 05
**Blocks:** 08

> **This subtask applies when Q2 selects option E (msgpack forward protocol).**
> If Q2 selects HTTP (option B/C), implement subtask 06 and skip this one.
> If both protocols are needed, implement both.

---

## Objective

Implement `FluentForwardClient`, an async client that speaks the Fluentd Forward
Protocol v1 / v2 over TCP to retrieve a bounded window of log events from a
Fluentd input port. The forward protocol uses msgpack-encoded frames and
optionally supports event-time extension types (v2).

## Files

- **Create** `src/aegis_swr/backends/log/fluent_forward_client.py`

## Background: Fluentd forward protocol

The forward protocol is primarily designed for shipping events *to* Fluentd, not
reading from it. However, if Fluentd is configured as an aggregator and exposes a
queryable `in_forward` port backed by a custom `filter_grep`/`filter_record` chain,
it is possible to subscribe to a filtered tag stream.

The protocol frame types relevant to reading are:
- `Message` (type 0): `[tag, time, record]`
- `Forward` (type 1): `[tag, entries, option]` where `entries = [[time, record], ...]`
- `PackedForward` (type 2): `[tag, chunk, option]` (msgpack-packed entries)

**Note:** Standard Fluentd does not provide a "pull" query API over the forward
protocol. This client assumes a **custom Fluentd plugin** or a **Fluentd-compatible
proxy** that accepts a subscription request and streams matching events for a time
range before closing the connection. The exact subscription frame format is TBD
pending Q2 answers.

## Classes / symbols

### `FluentForwardClient`

```python
class FluentForwardClient:
    """Async msgpack forward-protocol client for Fluentd.

    Connects to ``host:port``, sends a subscription/query frame (format TBD
    per deployment), and reads back msgpack event frames until the server
    closes the connection or the deadline is reached.

    Wraps the synchronous ``msgpack`` library calls in ``asyncio.to_thread``
    so the event loop is never blocked. Uses ``asyncio.StreamReader`` /
    ``asyncio.StreamWriter`` for the TCP layer.

    :param settings: :class:`~aegis_swr.config.settings.LogBackendSettings`
        providing host, port, timeouts, and optional TLS.
    """

    def __init__(self, settings: LogBackendSettings): ...

    async def __aenter__(self) -> "FluentForwardClient": ...
    async def __aexit__(self, *args: Any): ...

    async def query(
        self,
        tag: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
        max_events: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Subscribe to a tag and collect events within the time window.

        :param tag: Full Fluentd tag (e.g. ``aegis.auth-api``).
        :param start_time: UTC window start.
        :param end_time: UTC window end.
        :param severity_levels: Optional severity hint sent in the subscription
            frame; client-side filtering is applied on arrival regardless.
        :param max_events: Hard cap.  Defaults to
            ``settings.fluent_max_lines_per_service``.
        :return: List of raw record dicts.
        :raises FluentConnectionError: TCP connect or TLS handshake failure.
        :raises FluentTimeoutError: Read deadline exceeded before connection closes.
        :raises FluentProtocolError: msgpack framing error or unexpected frame type.
        """
```

### Subscription request frame (TBD - fill in after Q2 answers)

The exact wire format for requesting a time-range slice is not standardised;
this will be defined once the target Fluentd plugin or proxy is confirmed. 
Placeholder binary frame shape (to be replaced):

```
msgpack([
  "query",            # custom command tag
  {
    "tag":   "aegis.auth-api",
    "start": 1748606400,   # Unix timestamp
    "end":   1748607000,
    "limit": 5000
  }
])
```

### Frame decoding

```python
# Decode a single Forward-protocol chunk from the stream
def _decode_frame(raw: bytes, tag: str) -> list[tuple[datetime, dict[str, Any]]]:
    """Decode a msgpack Forward frame into (timestamp, record) pairs.

    Handles Message (type 0), Forward (type 1), and PackedForward (type 2).
    EventTime extension type (fixext 8, ext type 0) is decoded to datetime.
    Unknown frame types raise FluentProtocolError.
    """
```

### TLS support (TBD - fill in after Q3 answers)

If `settings.fluent_tls_enabled` is True, wrap the `asyncio.StreamReader/Writer`
in an `ssl.SSLContext` created from `fluent_tls_ca_cert` and optionally
`fluent_tls_client_cert` / `fluent_tls_client_key`.

## Constraints

- `msgpack` must be added to `pyproject.toml` (if not already present).
- All msgpack decode calls wrapped in `asyncio.to_thread` since `msgpack.Unpacker`
  is synchronous.
- TCP connection closed in `__aexit__` (RAII); `asyncio.StreamWriter.close()` +
  `wait_closed()`.
- Must handle the Fluentd server closing the connection after sending all matching
  events (`StreamReader.at_eof()`).
- Hard cap: if `max_events` records are accumulated before EOF, stop reading and
  log a `WARNING` that the result was capped.

## Tests

**Unit** (mock TCP server via `asyncio.start_server` in a fixture or `asynctest`):

- `test_forward_message_frame_decoded` - send a `Message`-type msgpack frame;
  assert one `(datetime, dict)` pair returned.
- `test_forward_batch_frame_decoded` - send a `Forward`-type frame with 3 entries;
  assert 3 pairs returned.
- `test_eventtime_ext_decoded_to_utc_datetime`.
- `test_connect_error_raises_fluent_connection_error`.
- `test_read_timeout_raises_fluent_timeout_error`.
- `test_max_events_cap_stops_reading`.
- `test_context_manager_closes_writer`.

**Integration** (TBD - see Q8):

- `test_query_against_test_fluentd_forward_port` - real TCP connection to a
  Docker Compose Fluentd if available.

## Success criteria

- [ ] `FluentForwardClient` implements async context manager and `query` method.
- [ ] All three Forward frame types decoded correctly.
- [ ] EventTime extension type decoded to UTC datetime.
- [ ] Max-events hard cap enforced with a warning log.
- [ ] TLS conditional on settings fields.
- [ ] All unit tests pass with zero real network calls.
- [ ] `ruff check src/ tests/` - clean.
