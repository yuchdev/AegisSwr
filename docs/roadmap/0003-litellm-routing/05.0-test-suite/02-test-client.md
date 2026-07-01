# 02 - test_client.py

**Parent task:** 05.0 Test Suite
**State:** ⬜ Not started
**Depends on:** 03.0 (LiteLLM client)
**Blocks:** -

## Objective

Write `tests/router/test_client.py` - full coverage of `LiteLLMClient.complete()`
plus the litellm isolation enforcement test. `litellm.acompletion` is always
mocked; no network calls.

## Test list

```python
@pytest.fixture
def mock_litellm_success(mocker):
    """Mock litellm.acompletion returning a synthetic successful response."""

@pytest.fixture
def mock_litellm_failure(mocker):
    """Mock litellm.acompletion raising litellm.exceptions.APIError."""

async def test_complete_returns_completion_response(mock_litellm_success):
    """Successful call returns CompletionResponse with all fields populated."""

async def test_complete_measures_latency_ms(mock_litellm_success):
    """latency_ms is positive and > 0."""

async def test_complete_wraps_litellm_exception_as_router_exception(mock_litellm_failure):
    """litellm.APIError is caught and re-raised as RouterException with __cause__ set."""

async def test_complete_populates_cost_usd_when_available(mock_litellm_success, mocker):
    """cost_usd is populated from litellm.completion_cost() when it returns a value."""

async def test_complete_sets_cost_usd_none_when_cost_unavailable(mock_litellm_success, mocker):
    """cost_usd is None when litellm.completion_cost() raises - no exception propagated."""

async def test_complete_sets_cost_usd_none_when_cost_raises(mock_litellm_success, mocker):
    """cost_usd is None when litellm.completion_cost() raises - no exception propagated."""

def test_litellm_is_only_imported_in_client():
    """
    Grep test: assert 'litellm' string appears in client.py and
    nowhere else under aegis/ (excluding tests/).
    """
    import pathlib
    violations = [
        str(py) for py in pathlib.Path("aegis").rglob("*.py")
        if py.parts[-1] != "client.py" or py.parts[-2] != "router"
        if "litellm" in py.read_text(encoding="utf-8")
    ]
    assert violations == [], f"litellm referenced outside router/client.py: {violations}"
```

## Mock fixture shape

```python
def _make_mock_response(content="test output", input_tokens=10, output_tokens=5):
    """Return a Mock shaped like a litellm ModelResponse."""
    mock = MagicMock()
    mock.model = "anthropic/claude-haiku-4-5-20251001"
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = input_tokens
    mock.usage.completion_tokens = output_tokens
    return mock
```

## Constraints

- `litellm.acompletion` must be patched via `mocker.patch("litellm.acompletion")`.
- No real network calls.
- The isolation grep test scans `aegis/` only (not `tests/`).

## Success criteria

- [ ] All 8 test functions present and passing.
- [ ] `test_complete_wraps_litellm_exception_as_router_exception` verifies
      `exc.__cause__` is the original litellm exception.
- [ ] `test_litellm_is_only_imported_in_client` passes (no violations in
      the initial implementation).
