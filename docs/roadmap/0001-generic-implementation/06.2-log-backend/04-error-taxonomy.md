# 04 – Error taxonomy and fail-open behaviour

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 06, 07, 08

## Objective

Define the exception hierarchy that `FluentAdapter` and its sub-components raise,
and document the exact fail-open contract at each layer. The existing Data Adapter
Stage 4 already wraps the `LogBackend` call with a broad `except` - this subtask
makes the failure taxonomy explicit so:

1. Distinct error categories can be tested and observed in logs.
2. The adapter does not leak raw network exceptions (which may contain hostnames,
   tokens, or server error bodies) into `IncidentBrief` fields.
3. Future alerting / observability can distinguish "Fluent unreachable" from
   "parse error" without inspecting log text.

## Files

- **Modify** `src/aegis_swr/core/exceptions.py`

## Exception hierarchy

```
AegisSWRError
└── LogBackendError           # base for all log-backend failures
    ├── FluentConnectionError     # TCP connect, TLS handshake, DNS failures
    ├── FluentTimeoutError        # read timeout, query deadline exceeded
    ├── FluentAuthError           # 401/403 from HTTP endpoint; auth token rejected
    ├── FluentProtocolError       # unexpected HTTP status (5xx); msgpack framing error
    └── FluentRecordParseError    # individual record cannot be normalised
```

### Docstrings and redaction contract

```python
class LogBackendError(AegisSWRError):
    """Base class for all log-ingestion backend failures.

    Sub-classes must NOT include raw server response bodies, authentication
    tokens, or hostname/port details in the ``args[0]`` message. Use the
    ``cause`` attribute for the wrapped exception (available to developers in
    logs) and keep the public message generic.

    :param message: Short, redaction-safe description of the failure.
    :param cause: Original exception, if any.
    """
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause: Optional[Exception] = cause


class FluentConnectionError(LogBackendError):
    """TCP / TLS connect failed or the host could not be resolved.

    :param host: Fluent host (logged at DEBUG level only, not in the message).
    :param port: Fluent port.
    :param cause: Underlying OSError / SSLError.
    """

class FluentTimeoutError(LogBackendError):
    """Query deadline or per-request read timeout exceeded."""

class FluentAuthError(LogBackendError):
    """HTTP endpoint rejected the auth token (401 / 403)."""

class FluentProtocolError(LogBackendError):
    """Unexpected HTTP status code or msgpack framing error."""

class FluentRecordParseError(LogBackendError):
    """A single Fluent event record cannot be normalised to a log line.

    :param raw: The raw dict/value that could not be parsed.
    """
    def __init__(
        self, message: str, raw: Optional[Any] = None, cause: Optional[Exception] = None
    ):
        super().__init__(message, cause)
        self.raw: Optional[Any] = raw
```

## Fail-open contract by layer

| Layer | Raises | Caller behaviour |
|-------|--------|-----------------|
| `FluentRecordParser.from_*` | `FluentRecordParseError` per unparseable record | Parser logs `WARNING` and skips that record; other records still returned |
| `FluentAdapter.query_window` | Any `LogBackendError` | Caller (`DataAdapter` Stage 4) logs `WARNING`, returns `[]` (fail-open to file-only) |
| `LogBackend.query_window_multi` (default) | Catches all exceptions per service | Service's lines omitted; `result.errors[svc]` set; other services unaffected |
| `DataAdapter._process_logs` | Never propagates `LogBackendError` | Wraps in `try/except LogBackendError`; logs `WARNING`; continues with file-only lines |

**Redaction rule:** `FluentConnectionError` and `FluentAuthError` must not embed the auth
token string in `args[0]`. The `cause` attribute holds the original exception
and is logged at `DEBUG` level only. Any server response body that contains
error detail is truncated to 200 characters before being included in the
`FluentProtocolError` message.

## Constraints

- All new classes inherit from `AegisSWRError` (already the project base).
- `AegisSWRError` does not yet have a `cause` parameter; add it to the base if
  not present, or keep `cause` only on `LogBackendError`. Either is acceptable;
  consistency with the existing hierarchy takes precedence.
- Use `Optional[T]` throughout; no `T | None`.
- `FluentRecordParseError.raw` stores the raw value for debugging but must not
  be logged at WARNING or above - it may contain PII from the log record.

## Tests

**Unit** (`tests/unit/test_exceptions.py` or extend existing):

- `test_fluent_connection_error_is_log_backend_error` - `isinstance(FluentConnectionError("x"), LogBackendError)` is `True`.
- `test_fluent_auth_error_message_does_not_embed_token` - construct
  `FluentAuthError("rejected", cause=Exception("token=abc"))` and assert
  `str(error)` does not contain `"abc"`.
- `test_fluent_record_parse_error_carries_raw` - construct with `raw={"time": "bad"}`;
  assert `error.raw == {"time": "bad"}`.
- `test_full_hierarchy` - all five sub-classes are subclasses of both
  `LogBackendError` and `AegisSWRError`.

## Success criteria

- [ ] All five new exception classes exist in `core/exceptions.py` with docstrings.
- [ ] `LogBackendError.__init__` accepts `message` and `cause`; `cause` is not
      included in the string representation automatically.
- [ ] The hierarchy table above is respected (each class is a subclass of the
      stated parent).
- [ ] `FluentRecordParseError` carries `raw` attribute.
- [ ] All unit tests above pass; `mypy --strict` clean.
