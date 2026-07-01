# 03 - test_router.py

**Parent task:** 05.0 Test Suite
**State:** ⬜ Not started
**Depends on:** 04.0 (ModelRouter complete)
**Blocks:** -

## Objective

Write `tests/router/test_router.py` - full coverage of `ModelRouter.complete()`
retry, fallback, event emission, and error behavior. `LiteLLMClient` is always
mocked; events are captured via a real `EventBus` with a list-collecting
subscriber.

## Test list

```python
@pytest.fixture
def mock_client_success(mocker):
    """LiteLLMClient.complete returns a valid CompletionResponse."""

@pytest.fixture
def mock_client_always_fails(mocker):
    """LiteLLMClient.complete always raises RouterException."""

@pytest.fixture
def mock_client_fails_then_succeeds(mocker):
    """LiteLLMClient.complete raises RouterException once, then succeeds."""

@pytest.fixture
def capturing_bus():
    """Real EventBus with a list-collecting subscriber for assertions."""

async def test_complete_success_emits_started_and_completed(mock_client_success, capturing_bus):
    """Successful call emits RouterCallStarted then RouterCallCompleted."""

async def test_complete_success_returns_response(mock_client_success, capturing_bus):
    """Successful call returns the CompletionResponse from the client."""

async def test_complete_retries_on_failure(mock_client_fails_then_succeeds, capturing_bus):
    """First failure triggers retry; second succeeds; RouterCallFailed emitted once."""

async def test_complete_fallback_used_when_primary_exhausted(mock_client_always_fails, capturing_bus):
    """Primary exhaustion emits RouterFallbackUsed and fallback is attempted."""

async def test_complete_raises_all_providers_exhausted(mock_client_always_fails, capturing_bus):
    """AllProvidersExhausted raised when every model in the chain fails."""

async def test_all_providers_exhausted_includes_full_tried_list(mock_client_always_fails, capturing_bus):
    """AllProvidersExhausted.tried contains primary + all fallback model names."""

async def test_run_id_propagated_to_all_events(mock_client_success, capturing_bus):
    """Every RouterEvent for a call carries the same run_id."""

async def test_backoff_uses_asyncio_sleep(mock_client_fails_then_succeeds, mocker):
    """asyncio.sleep is called for backoff; time.sleep is never called."""

async def test_unknown_role_raises_key_error(mock_client_success, capturing_bus):
    """complete() with an unknown role raises KeyError before any model call."""

async def test_non_retriable_error_skips_retry(mocker, capturing_bus):
    """Context-length error goes directly to fallback without retrying."""
```

## Capturing bus fixture

```python
from aegis.event_bus import EventBus

@pytest.fixture
def capturing_bus():
    bus = EventBus()
    events = []
    bus.subscribe(lambda e: events.append(e))
    bus.events = events   # expose for assertions
    return bus
```

## Constraints

- `LiteLLMClient` must be mocked at the class level, not at the litellm module
  level (the router never imports litellm directly).
- `asyncio.sleep` is mocked with `mocker.patch("asyncio.sleep", new_callable=AsyncMock)`.
- Router is constructed with a minimal `RouterConfig` (one primary model +
  one fallback) to keep the fixtures focused.

## Success criteria

- [ ] All 10 test functions present and passing.
- [ ] `test_run_id_propagated_to_all_events` asserts every captured event's
      `.run_id` equals the run_id passed to `complete()`.
- [ ] `test_all_providers_exhausted_includes_full_tried_list` verifies
      `exc.tried == [primary_model, fallback_model]`.
