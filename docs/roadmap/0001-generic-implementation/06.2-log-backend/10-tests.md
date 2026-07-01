# 10 – Unit, mock and integration tests

**Parent milestone:** 6.2 Log Backend – Fluentd Stack
**State:** ⬜ Blocked - depends on 08, 09
**Depends on:** 02, 03, 04, 08, 09
**Blocks:** nothing (terminal subtask)

---

## Objective

Consolidate and extend the test suite for the entire Fluent backend stack.
Subtasks 01–09 each specify their own per-unit tests; this subtask covers:

1. **Cross-component integration tests** that exercise the full path from
   `DataAdapter.process` → `FluentAdapter.query_window` → record parse →
   log line merge.
2. **Mock HTTP server tests** that exercise the `FluentHttpClient` against a
   controlled in-process HTTP server (protocol contract verification, no real
   Fluentd required).
3. **Docker Compose integration tests** against a real Fluent stack (conditional
   on Q8 answer - skip if no test instance is available).
4. **Regression tests** that confirm `FileLogAdapter` is unaffected by the new
   multi-service changes.
5. **Data Adapter Stage 4 tests** for the multi-service wiring.

## Files

- **Modify** `tests/unit/test_log_backends.py` (extend with Fluent adapter tests)
- **Create** `tests/unit/test_fluent_record.py` (record normalisation - see subtask 03)
- **Create** `tests/unit/fixtures/fluent_http_batch.json` (mock HTTP response body)
- **Create** `tests/unit/fixtures/fluent_msgpack_events.bin` (binary forward frames)
- **Create** `tests/integration/test_fluent_backend.py`
- **Modify** `tests/integration/test_data_adapter.py` (Stage 4 multi-service path)
- **Modify** `docker-compose.test.yml` (optional - add Fluent Bit test service if Q8 = Docker)

## Test inventory

### Unit: `test_log_backends.py` additions

These tests expand the existing file and fluent stub tests.

| Test name | What it verifies |
|-----------|-----------------|
| `test_fluent_adapter_protocol_http_selected` | `fluent_protocol="http"` → `FluentHttpClient` instantiated |
| `test_fluent_adapter_protocol_forward_selected` | `fluent_protocol="forward"` → `FluentForwardClient` |
| `test_fluent_adapter_window_applied_after_query` | Records outside the window stripped even if server returns them |
| `test_fluent_adapter_severity_filter_applied` | Only `ERROR`/`CRITICAL` lines returned when levels set |
| `test_fluent_adapter_max_lines_cap_enforced` | > `max_lines_per_service` records from server → capped at limit |
| `test_fluent_adapter_tag_prefix_concatenation` | Tag built as `{prefix}.{service}` |
| `test_fluent_adapter_missing_host_raises_at_construction` | `ValueError` when `fluent_host=None` |
| `test_fluent_adapter_connection_error_returns_empty` | `FluentConnectionError` → `[]` returned |
| `test_fluent_adapter_timeout_returns_empty` | `FluentTimeoutError` → `[]` returned |
| `test_fluent_adapter_auth_error_logs_warning` | `FluentAuthError` → `WARNING` logged |
| `test_fluent_adapter_multi_happy_path` | `query_window_multi(["a","b"])` → lines from both services |
| `test_fluent_adapter_multi_one_service_fails_others_succeed` | fail-open per service in multi |
| `test_file_adapter_unaffected_by_multi_changes` | Existing `FileLogAdapter` tests still pass |

### Unit: `test_fluent_record.py`

See [subtask 03](03-record-normalization.md#tests) for the full list (11 test cases).
Ensure they are written in this dedicated module, not in `test_log_backends.py`.

### Unit: `test_data_adapter.py` - Stage 4 multi-service

| Test name | What it verifies |
|-----------|-----------------|
| `test_stage4_multi_service_called_when_services_in_metadata` | `query_window_multi` called when `source.metadata["services"]` set |
| `test_stage4_single_service_path_unchanged` | Existing `query_window` path still used when `services` absent |
| `test_stage4_multi_error_graceful` | `result.errors` non-empty → warning logged, brief still produced |
| `test_stage4_merged_lines_fed_to_drain3` | Merged multi-service lines pass through Drain3 clustering |

### Mock HTTP server integration: `test_fluent_backend.py`

These tests use `pytest-httpserver` (or equivalent) to run a real in-process
HTTP server that returns controlled Fluentd JSON payloads. **No external Fluentd
required.**

```python
@pytest.fixture
def fluent_server(httpserver):
    """Configure a mock Fluentd HTTP endpoint."""
    httpserver.expect_request(
        "/api/logs/query",
        method="POST",
    ).respond_with_json([
        {
            "tag": "aegis.auth-api",
            "time": 1748606401,
            "record": {"message": "db write failed", "level": "ERROR"},
        },
        {
            "tag": "aegis.auth-api",
            "time": 1748607000,
            "record": {"message": "connection ok", "level": "INFO"},
        },
    ])
    return httpserver
```

| Test name | What it verifies |
|-----------|-----------------|
| `test_http_client_parses_real_json_response` | Full round-trip against mock server → records parsed |
| `test_http_client_auth_header_sent` | `Authorization: Bearer <token>` header present |
| `test_http_client_propagates_404_as_protocol_error` | Mock 404 → `FluentProtocolError` |
| `test_http_client_propagates_401_as_auth_error` | Mock 401 → `FluentAuthError` |
| `test_full_adapter_against_mock_server` | `FluentAdapter.query_window` end-to-end against mock server → plain-text lines |

### Docker Compose integration: conditional on Q8

If Q8 confirms a Docker Compose test instance is available, add a `pytest` mark:

```python
@pytest.mark.integration
@pytest.mark.requires_fluent
```

And a `docker-compose.test.yml` service:

```yaml
fluent-bit-test:
  image: fluent/fluent-bit:3
  ports:
    - "9880:9880"
  command: ["/fluent-bit/bin/fluent-bit", "-c", "/fluent-bit/etc/fluent-bit.conf"]
  volumes:
    - ./tests/fixtures/fluent-bit-test.conf:/fluent-bit/etc/fluent-bit.conf:ro
```

These tests are skipped in CI unless `AEGIS_TEST_FLUENT=1` is set.

## Coverage targets

After subtask 10, the following coverage targets must be met:

| Module | Line coverage |
|--------|--------------|
| `backends/log/fluent_adapter.py` | ≥ 90 % |
| `backends/log/fluent_http_client.py` | ≥ 85 % |
| `backends/log/fluent_forward_client.py` | ≥ 85 % |
| `backends/log/fluent_record.py` | ≥ 95 % |
| `backends/log/file_adapter.py` | Unchanged (already covered) |

Run with:

```bash
poetry run pytest tests/unit/test_log_backends.py tests/unit/test_fluent_record.py \
    tests/integration/test_fluent_backend.py \
    --cov=aegis_swr.backends.log --cov-report=term-missing -q
```

## pyproject.toml additions

Depending on Q5 answers, add one or more test dependencies:

```toml
[tool.poetry.dev-dependencies]
pytest-httpserver = "^1.0"   # mock HTTP server for FluentHttpClient tests
# pytest-asyncio already present
```

## Success criteria

- [ ] All unit tests in `test_log_backends.py`, `test_fluent_record.py`, and
      `test_data_adapter.py` additions pass with zero network calls.
- [ ] Mock HTTP server tests pass with zero real Fluentd instances.
- [ ] Docker Compose integration tests pass (or are correctly skipped when
      `AEGIS_TEST_FLUENT` is unset).
- [ ] Coverage targets above met.
- [ ] No existing `FileLogAdapter` tests broken.
- [ ] `pytest tests/unit/ -q --cov=aegis_swr --cov-report=term-missing` green.
