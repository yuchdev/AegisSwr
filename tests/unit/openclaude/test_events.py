"""Unit tests for the seven OpenClaude lifecycle/stream event dataclasses.

These cover the contract C8 taxonomy in
:mod:`aegis_swr.openclaude.events`: exact field shapes and ``event_type``
sentinels, frozen + keyword-only construction, timezone-aware UTC timestamps,
the C9 payload-free invariant (no field carries tool arguments, tool output,
response text, or a raw error message), the single-source ``token_estimate``
rule, and - crucially - that each event round-trips through the live
:class:`aegis_swr.core.events.EventBus`, proving the ``DomainEvent`` subclassing
decision actually dispatches on the shipping bus.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.events import (
    OpenClaudeConnected,
    OpenClaudeDisconnected,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

#: One representative, fully keyword-constructed instance per event class,
#: paired with its expected ``event_type`` string. Every value is an id, count,
#: estimate, flag, or short status string - never payload text.
_INSTANCES: list[tuple[DomainEvent, str]] = [
    (OpenClaudeConnected(run_id="r1", grpc_url="127.0.0.1:50051", mode="managed"), "openclaude.connected"),
    (OpenClaudeDisconnected(run_id="r1", reason="context_exit"), "openclaude.disconnected"),
    (OpenClaudeToolCall(run_id="r1", tool="Grep", arg_count=2), "openclaude.tool_call"),
    (OpenClaudeToolResult(run_id="r1", tool="Grep", ok=True, result_size=128), "openclaude.tool_result"),
    (OpenClaudePermissionDenied(run_id="r1", tool="Bash", denied_binary="curl"), "openclaude.permission_denied"),
    (
        OpenClaudeStreamCompleted(run_id="r1", token_estimate=42, frame_count=9, truncated=False),
        "openclaude.stream_completed",
    ),
    (
        OpenClaudeStreamError(run_id="r1", error_type="grpc_status", code="UNAVAILABLE", frame_count=3),
        "openclaude.stream_error",
    ),
]

_ALL_CLASSES = [
    OpenClaudeConnected,
    OpenClaudeDisconnected,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
]

#: Fully specified keyword constructor kwargs per class, used to drive
#: parametrised construction/frozen tests uniformly.
_KWARGS: dict[type, dict[str, object]] = {
    OpenClaudeConnected: {"run_id": "r1", "grpc_url": "127.0.0.1:50051", "mode": "managed"},
    OpenClaudeDisconnected: {"run_id": "r1", "reason": "context_exit"},
    OpenClaudeToolCall: {"run_id": "r1", "tool": "Grep", "arg_count": 2},
    OpenClaudeToolResult: {"run_id": "r1", "tool": "Grep", "ok": True, "result_size": 128},
    OpenClaudePermissionDenied: {"run_id": "r1", "tool": "Bash", "denied_binary": "curl"},
    OpenClaudeStreamCompleted: {"run_id": "r1", "token_estimate": 42, "frame_count": 9, "truncated": False},
    OpenClaudeStreamError: {"run_id": "r1", "error_type": "grpc_status", "code": "UNAVAILABLE", "frame_count": 3},
}

#: Field-name tokens that would signal a payload/args/response-text leak (C9).
_FORBIDDEN_FIELD_TOKENS = (
    "payload",
    "arg",  # substring of "args"/"arguments" AND "arg_count"; the latter is exempted below
    "content",
    "message",
    "response",
    "text",
    "body",
    "output",
    "command",
    "cmdline",
    "stdout",
    "stderr",
)


# ---------------------------------------------------------------------------
# Structural contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_is_domain_event_subclass(cls: type) -> None:
    """Every event subclasses :class:`DomainEvent` so the live bus dispatches it."""
    assert issubclass(cls, DomainEvent)


@pytest.mark.parametrize("event, event_type", _INSTANCES)
def test_event_type_sentinel_matches_c8(event: DomainEvent, event_type: str) -> None:
    """Each class exposes the exact C8 ``event_type`` string as a ``ClassVar``."""
    assert event.event_type == event_type
    # ``event_type`` is a ClassVar sentinel, never an instance dataclass field.
    field_names = {f.name for f in dataclasses.fields(event)}
    assert "event_type" not in field_names


def test_event_type_strings_are_unique() -> None:
    """No two events share an ``event_type`` discriminator."""
    types = [event_type for _event, event_type in _INSTANCES]
    assert len(set(types)) == len(types)


def test_expected_field_shapes() -> None:
    """Each class declares exactly the C8 fields with the expected annotations."""
    expected: dict[type, dict[str, type]] = {
        OpenClaudeConnected: {"run_id": str, "grpc_url": str, "mode": str, "timestamp": datetime},
        OpenClaudeDisconnected: {"run_id": str, "reason": str, "timestamp": datetime},
        OpenClaudeToolCall: {"run_id": str, "tool": str, "arg_count": int, "timestamp": datetime},
        OpenClaudeToolResult: {
            "run_id": str,
            "tool": str,
            "ok": bool,
            "result_size": int,
            "timestamp": datetime,
        },
        OpenClaudePermissionDenied: {
            "run_id": str,
            "tool": str,
            "denied_binary": str,
            "timestamp": datetime,
        },
        OpenClaudeStreamCompleted: {
            "run_id": str,
            "token_estimate": int,
            "frame_count": int,
            "truncated": bool,
            "timestamp": datetime,
        },
        OpenClaudeStreamError: {
            "run_id": str,
            "error_type": str,
            "code": str,
            "frame_count": int,
            "timestamp": datetime,
        },
    }
    hint_map = {str: "str", int: "int", bool: "bool", datetime: "datetime"}
    for cls, fields in expected.items():
        resolved = {f.name: f.type for f in dataclasses.fields(cls)}
        assert resolved.keys() == fields.keys(), cls.__name__
        # ``from __future__ import annotations`` keeps field types as strings.
        for name, py_type in fields.items():
            assert resolved[name] == hint_map[py_type], f"{cls.__name__}.{name}"


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_no_field_is_typed_any(cls: type) -> None:
    """No field annotation is ``Any`` - only str/int/bool/datetime allowed (C8)."""
    allowed = {"str", "int", "bool", "datetime"}
    for f in dataclasses.fields(cls):
        assert f.type in allowed, f"{cls.__name__}.{f.name} -> {f.type}"


# ---------------------------------------------------------------------------
# Construction semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_frozen_assignment_raises(cls: type) -> None:
    """Instances are immutable: attribute assignment raises ``FrozenInstanceError``."""
    event = cls(**_KWARGS[cls])
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.run_id = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_positional_construction_raises(cls: type) -> None:
    """``kw_only=True`` means positional construction raises ``TypeError``."""
    positional = list(_KWARGS[cls].values())
    with pytest.raises(TypeError):
        cls(*positional)


@pytest.mark.parametrize("event, _event_type", _INSTANCES)
def test_run_id_and_tz_aware_utc_timestamp(event: DomainEvent, _event_type: str) -> None:
    """Every event carries ``run_id: str`` and a tz-aware UTC ``timestamp``."""
    assert isinstance(event.run_id, str)
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo is not None
    # tz-aware AND UTC: a zero offset on a non-None tzinfo is what we require.
    assert event.timestamp.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# C9 payload-free invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_no_payload_bearing_fields(cls: type) -> None:
    """No field name hints at tool args, tool output, response text, or raw errors (C9)."""
    for f in dataclasses.fields(cls):
        name = f.name.lower()
        # ``arg_count`` is a count, not the arguments themselves - explicitly allowed.
        if name == "arg_count":
            continue
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name, f"{cls.__name__}.{f.name} looks payload-bearing ({token})"


def test_token_estimate_only_on_stream_completed() -> None:
    """``token_estimate`` lives on :class:`OpenClaudeStreamCompleted` alone (C5/C8)."""
    carriers = [cls for cls in _ALL_CLASSES if "token_estimate" in {f.name for f in dataclasses.fields(cls)}]
    assert carriers == [OpenClaudeStreamCompleted]


# ---------------------------------------------------------------------------
# Live EventBus round-trip - proves the DomainEvent-subclass decision works
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event, event_type", _INSTANCES)
def test_roundtrip_via_domain_event_subscription(event: DomainEvent, event_type: str) -> None:
    """A ``DomainEvent`` subscriber receives every OpenClaude event and can filter by type."""
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(DomainEvent, received.append)

    bus.publish(event)

    assert received == [event]
    assert received[0].event_type == event_type


@pytest.mark.parametrize("event, _event_type", _INSTANCES)
def test_roundtrip_via_specific_subscription(event: DomainEvent, _event_type: str) -> None:
    """A subscriber to the concrete class receives exactly that published instance."""
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(type(event), received.append)

    bus.publish(event)

    assert received == [event]


def test_specific_subscription_does_not_cross_deliver() -> None:
    """Subscribing to one event class never receives a different OpenClaude event."""
    bus = EventBus()
    connected: list[DomainEvent] = []
    bus.subscribe(OpenClaudeConnected, connected.append)

    bus.publish(OpenClaudeToolCall(run_id="r1", tool="Grep", arg_count=1))

    assert connected == []
