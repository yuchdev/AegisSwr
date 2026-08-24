# 06 – Fluent HTTP query client

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Blocked - requires answers to [05-design-clarifications.md](05-design-clarifications.md) Q1, Q2, Q3, Q5
**Depends on:** 01, 03, 04, 05
**Blocks:** 08

> **This subtask applies when Q2 selects option B or C (HTTP pull mechanism).**
> If Q2 selects option E (msgpack forward protocol) instead, implement subtask 07
> and skip this one. If both protocols are needed, implement both.

---

## Objective

Implement `FluentHttpClient`, an async HTTP client that issues time-range log
queries to a Fluentd HTTP endpoint or a sidecar proxy. The client is decoupled
from `FluentAdapter` so it can be unit-tested with a mock HTTP server without
instantiating the full adapter.

## Files

- **Create** `src/aegis_swr/backends/log/fluent_http_client.py`

## Classes / symbols

### `FluentHttpClient`

```python
class FluentHttpClient:
    """Async HTTP client for Fluentd / sidecar log query endpoints.

    Connects to ``{scheme}://{host}:{port}{query_path}`` and issues
    POST requests with a JSON body encoding the tag, time range, severity
    levels, and result cap.

    All network I/O uses ``httpx.AsyncClient`` (or ``aiohttp`` - TBD per Q5).
    The client is a context manager; callers use ``async with FluentHttpClient(settings)``.

    :param settings: :class:`~aegis_swr.config.settings.LogBackendSettings`
        supplying host, port, path, timeout, TLS, and auth configuration.
    """

    def __init__(self, settings: LogBackendSettings): ...

    async def __aenter__(self) -> "FluentHttpClient": ...
    async def __aexit__(self, *args: Any): ...

    async def query(
        self,
        tag: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
        max_lines: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Issue a single tag query and return raw Fluentd record dicts.

        :param tag: Full tag string (e.g. ``aegis.auth-api``).
        :param start_time: UTC window start (inclusive).
        :param end_time: UTC window end (inclusive).
        :param severity_levels: Optional level filter forwarded as a hint to
            the server; client-side filtering via
            :class:`~.fluent_record.FluentRecordParser` is always applied as a
            safety net.
        :param max_lines: Hard cap on returned records. Defaults to
            ``settings.fluent_max_lines_per_service``.
        :return: List of raw record dicts; parsing delegated to the caller
            (``FluentAdapter`` calls ``FluentRecordParser.from_http_batch``).
        :raises FluentConnectionError: TCP connect or DNS failure.
        :raises FluentTimeoutError: Read or connect timeout exceeded.
        :raises FluentAuthError: HTTP 401 or 403.
        :raises FluentProtocolError: HTTP 4xx (other than 401/403) or 5xx.
        """

    async def query_batch(
        self,
        tags: list[str],
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Query multiple tags in a single request (batch endpoint).

        Returns a mapping from tag to its records.
        Only implement if Q4 confirms the server supports batch queries;
        otherwise this method delegates to ``asyncio.gather`` over ``query``.
        """
```

### Request/response contract (TBD - fill in after Q2/Q3 answers)

The exact JSON body shape depends on Q2 (sidecar vs Fluentd HTTP plugin). Placeholder:

```jsonc
// POST {query_path}
{
  "tag":   "aegis.auth-api",
  "start": "2026-05-30T14:00:00Z",
  "end":   "2026-05-30T14:10:00Z",
  "levels": ["ERROR", "CRITICAL"],  // optional
  "limit":  5000
}

// 200 OK
[
  {"tag": "aegis.auth-api", "time": 1748606401, "record": {...}},
  ...
]
```

### Error mapping (HTTP status → exception)

| HTTP status | Exception raised |
|-------------|-----------------|
| `401`, `403` | `FluentAuthError` |
| `408`, `504` | `FluentTimeoutError` |
| `4xx` (other) | `FluentProtocolError` |
| `5xx` | `FluentProtocolError` |
| Network error | `FluentConnectionError` |
| Read timeout | `FluentTimeoutError` |

### TLS and auth injection (TBD - fill in after Q3 answers)

```python
# Bearer token (if fluent_auth_token set)
headers["Authorization"] = f"Bearer {settings.fluent_auth_token}"

# mTLS (if fluent_tls_client_cert + fluent_tls_client_key set)
ssl_context = ssl.create_default_context(cafile=settings.fluent_tls_ca_cert)
ssl_context.load_cert_chain(
    certfile=settings.fluent_tls_client_cert,
    keyfile=settings.fluent_tls_client_key,
)
```

`fluent_auth_token` must not appear in any log line (it is a `SensitiveFilter` key).

## Constraints

- All I/O is async; no blocking calls on the event loop.
- The HTTP library (httpx or aiohttp - Q5 TBD) must be added to `pyproject.toml`.
- Timeouts: connect = `settings.fluent_connect_timeout_seconds`,
  read = `settings.fluent_query_timeout_seconds`.
- The client must close the underlying HTTP session in `__aexit__` (RAII).
- Error messages must never embed `fluent_auth_token` or TLS key content.

## Tests

**Unit** (mock HTTP server via `pytest-httpx` or `aioresponses` - TBD per Q5):

- `test_query_happy_path` - mock server returns 200 JSON batch; assert records returned.
- `test_query_401_raises_fluent_auth_error`.
- `test_query_500_raises_fluent_protocol_error`.
- `test_query_timeout_raises_fluent_timeout_error`.
- `test_query_connect_error_raises_fluent_connection_error`.
- `test_bearer_token_in_header` - assert `Authorization` header set when token configured.
- `test_tls_ca_cert_used` - assert custom CA bundle path passed to client (mock ssl).
- `test_context_manager_closes_session`.

**Integration** (TBD - requires Q8 answer on Docker Compose availability):

- `test_query_against_test_fluent_instance` - real network call against a
  Docker Compose Fluentd/Fluent Bit if available.

## Success criteria

- [ ] `FluentHttpClient` implements async context manager and `query` method.
- [ ] All HTTP error status codes map to the correct exception class.
- [ ] Auth token never appears in log output.
- [ ] TLS cert loading conditional on settings fields.
- [ ] All unit tests pass with zero real network calls.
- [ ] `ruff check src/ tests/` - clean.
