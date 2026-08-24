# 06 - `test_events.py`

**Parent task:** 07.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01 (fixtures — `mock_event_bus`), 05.0 subtask 01 (seven event
dataclasses), 05.0 subtask 03 (EventBus registry).
**Blocks:** none

## Objective

Verify the seven `OpenClaude*` event dataclasses of contract C8: each
instantiates with keyword-only construction, each is `frozen=True` (mutation
raises `FrozenInstanceError`), each carries `run_id`, a UTC `timestamp`, and a
`ClassVar[str]` `event_type` sentinel, and each round-trips through the recording
`mock_event_bus`. `OpenClaudeStreamCompleted` is checked specifically for its
`token_estimate` and frame-count fields, and it is confirmed to be the **only**
event carrying the token estimate.

## File: `tests/openclaude/unit/test_events.py`

```python
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from aegis.openclaude.events import (
    OpenClaudeConnected,
    OpenClaudeDisconnected,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
)

ALL_EVENT_TYPES = [
    OpenClaudeConnected,
    OpenClaudeDisconnected,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
]


def _instance(cls):
    """Build a minimal valid instance of each event class with dummy fields."""
    ...


@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_instantiates(cls):
    """Each of the seven event classes constructs without error (keyword-only)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_is_frozen(cls):
    """Mutating any field raises dataclasses.FrozenInstanceError (frozen=True)."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_carries_run_id_timestamp_and_event_type(cls):
    """Each instance exposes run_id, a UTC timestamp, and a ClassVar event_type sentinel."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_type_sentinel_matches_c8(cls):
    """event_type equals the C8 string (e.g. 'openclaude.connected')."""

@pytest.mark.parametrize("cls", ALL_EVENT_TYPES)
def test_event_round_trips_through_bus(cls, mock_event_bus):
    """Emitting the event puts exactly that instance on mock_event_bus.captured."""

def test_stream_completed_carries_token_estimate_and_frame_counts():
    """OpenClaudeStreamCompleted carries token_estimate + frame/tool-call counts correctly."""

def test_only_stream_completed_carries_token_estimate():
    """No other of the seven events has a token_estimate field (C8 non-duplication)."""

def test_no_event_has_any_typed_field():
    """No event field is annotated `Any` and none carries raw payload/response text (C9)."""
```

## Test cases

| Test | Contract verified |
|------|-------------------|
| `test_event_instantiates` | C8: all seven classes construct with keyword-only args |
| `test_event_is_frozen` | C8/05.0: `frozen=True` — mutation raises `dataclasses.FrozenInstanceError` |
| `test_event_carries_run_id_timestamp_and_event_type` | C8: every event has `run_id`, UTC `timestamp`, and a `ClassVar[str]` `event_type` |
| `test_event_type_sentinel_matches_c8` | C8 taxonomy: `event_type` equals the exact string (`openclaude.connected`, `.disconnected`, `.tool_call`, `.tool_result`, `.permission_denied`, `.stream_completed`, `.stream_error`) |
| `test_event_round_trips_through_bus` | 05.0/03: each event emits and is captured on `mock_event_bus.captured` without registry error |
| `test_stream_completed_carries_token_estimate_and_frame_counts` | C8/C5: `OpenClaudeStreamCompleted.token_estimate` and its frame-count / tool-call-count fields carry the passed values |
| `test_only_stream_completed_carries_token_estimate` | C8: token estimate is **not** duplicated on any other event |
| `test_no_event_has_any_typed_field` | 05.0/C9: no `Any`-typed field; payloads carry only ids, counts, estimates, status strings — no raw incident payload / unredacted response text |

## Constraints

- All tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary on
  `PATH`; events are constructed directly, no gRPC / process involved. No
  `grpc` / `_pb2` import.
- Use the shared `mock_event_bus` fixture from subtask 01 for the round-trip
  test; do not create a bespoke bus.
- `timestamp` must be timezone-aware UTC; assert `ts.tzinfo is not None` and the
  offset is UTC.
- `test_no_event_has_any_typed_field` introspects
  `typing.get_type_hints(cls)` and asserts no hint is `typing.Any`.
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).

## Success criteria

- [ ] All 8 test functions (5 parametrised over 7 classes + 3 specific) present
      and passing.
- [ ] `test_event_type_sentinel_matches_c8` asserts all seven `event_type`
      strings exactly per the C8 table.
- [ ] `test_event_is_frozen` asserts `dataclasses.FrozenInstanceError` for every
      class.
- [ ] `test_stream_completed_carries_token_estimate_and_frame_counts` asserts
      the `token_estimate` and frame-count field values match the constructor
      inputs.
- [ ] `test_only_stream_completed_carries_token_estimate` asserts the other six
      classes have no `token_estimate` field.
- [ ] No `grpc` / `_pb2` import in this file.
- [ ] `ruff check src/ tests/` - clean.
