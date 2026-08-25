"""Unit tests for the seven OpenHands lifecycle/stream event dataclasses.

These cover the contract C10 OpenHands taxonomy in
:mod:`aegis_swr.openhands.events`: exact field shapes and ``event_type``
sentinels, frozen + keyword-only construction, timezone-aware UTC timestamps,
the C13 payload-free invariant (no field carries action arguments, observation
output, a sandbox command line, a raw error message, or a ``server_url`` value
outside the connect event), the single-source ``token_estimate`` rule and its C9
``usage_reported`` provenance flag, the deliberate absence of an ``auth_failed``
event (n/a per C10), and - crucially - that each event round-trips through the
live :class:`aegis_swr.core.events.EventBus`, proving the ``DomainEvent``
subclassing decision actually dispatches on the shipping bus.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from datetime import datetime

import pytest

from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openhands import events as events_module
from aegis_swr.openhands.events import (
    OpenHandsAction,
    OpenHandsCompleted,
    OpenHandsConnected,
    OpenHandsDisconnected,
    OpenHandsError,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

#: One representative, fully keyword-constructed instance per event class,
#: paired with its expected ``event_type`` string. Every value is an id, count,
#: size, flag, or short status string - never payload text.
_INSTANCES: list[tuple[DomainEvent, str]] = [
    (OpenHandsConnected(run_id="r1", server_url="http://localhost:3000", mode="managed"), "openhands.connected"),
    (OpenHandsDisconnected(run_id="r1", reason="context_exit"), "openhands.disconnected"),
    (OpenHandsAction(run_id="r1", action="read", arg_count=2), "openhands.action"),
    (OpenHandsObservation(run_id="r1", observation="read", ok=True, content_size=128), "openhands.observation"),
    (
        OpenHandsPermissionDenied(run_id="r1", action="run", denied_binary="curl"),
        "openhands.permission_denied",
    ),
    (
        OpenHandsCompleted(run_id="r1", token_estimate=42, usage_reported=True, event_count=9, truncated=False),
        "openhands.completed",
    ),
    (
        OpenHandsError(run_id="r1", error_type="stream_error", code="UNAVAILABLE", event_count=3),
        "openhands.error",
    ),
]

_ALL_CLASSES = [
    OpenHandsConnected,
    OpenHandsDisconnected,
    OpenHandsAction,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
    OpenHandsCompleted,
    OpenHandsError,
]

#: Fully specified keyword constructor kwargs per class, used to drive
#: parametrised construction/frozen tests uniformly.
_KWARGS: dict[type, dict[str, object]] = {
    OpenHandsConnected: {"run_id": "r1", "server_url": "http://localhost:3000", "mode": "managed"},
    OpenHandsDisconnected: {"run_id": "r1", "reason": "context_exit"},
    OpenHandsAction: {"run_id": "r1", "action": "read", "arg_count": 2},
    OpenHandsObservation: {"run_id": "r1", "observation": "read", "ok": True, "content_size": 128},
    OpenHandsPermissionDenied: {"run_id": "r1", "action": "run", "denied_binary": "curl"},
    OpenHandsCompleted: {
        "run_id": "r1",
        "token_estimate": 42,
        "usage_reported": True,
        "event_count": 9,
        "truncated": False,
    },
    OpenHandsError: {"run_id": "r1", "error_type": "stream_error", "code": "UNAVAILABLE", "event_count": 3},
}

#: Field-name tokens that would signal a payload/args/observation-text leak (C13).
_FORBIDDEN_FIELD_TOKENS = (
    "payload",
    "arg",  # substring of "args"/"arguments" AND "arg_count"; the latter is exempted below
    "content",  # substring of "content_size" (a byte count); exempted below
    "message",
    "response",
    "text",
    "body",
    "output",
    "command",
    "cmdline",
    "stdout",
    "stderr",
    "task",
)

#: Field names that contain a forbidden token but are provably a count/size, not
#: the payload itself, so they are explicitly exempt from the token audit.
_COUNT_SIZE_EXEMPTIONS = {"arg_count", "content_size"}


# ---------------------------------------------------------------------------
# Structural contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_is_domain_event_subclass(cls: type):
    """[Unit] events: Every OpenHands event subclasses :class:`DomainEvent` so the live bus dispatches it.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: every event subclasses :class:`DomainEvent` so the live bus dispatches it.
    """
    assert issubclass(cls, DomainEvent)


def test_exactly_seven_event_classes():
    """[Unit] events: The taxonomy is exactly the seven C10 OpenHands events - no more, no fewer.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the taxonomy is exactly the seven C10 OpenHands events.
    """
    exported = {
        name
        for name in dir(events_module)
        if name.startswith("OpenHands") and isinstance(getattr(events_module, name), type)
    }
    assert exported == {cls.__name__ for cls in _ALL_CLASSES}
    assert len(_ALL_CLASSES) == 7


@pytest.mark.parametrize("event, event_type", _INSTANCES)
def test_event_type_sentinel_matches_c10(event: DomainEvent, event_type: str):
    """[Unit] events: Each class exposes the exact C10 ``event_type`` string as a ``ClassVar``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: each class exposes the exact C10 ``event_type`` string as a ``ClassVar``.
    """
    assert event.event_type == event_type
    # ``event_type`` is a ClassVar sentinel, never an instance dataclass field.
    field_names = {f.name for f in dataclasses.fields(event)}
    assert "event_type" not in field_names


def test_event_type_strings_are_unique():
    """[Unit] events: No two OpenHands events share an ``event_type`` discriminator.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no two events share an ``event_type`` discriminator.
    """
    types = [event_type for _event, event_type in _INSTANCES]
    assert len(set(types)) == len(types)


def test_no_auth_failed_event_exists():
    """[Unit] events: OpenHands has no ``auth_failed`` event - that concept is n/a per C10.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no OpenHands event class or ``event_type`` names ``auth_failed``.
    """
    # No class named for it.
    assert not hasattr(events_module, "OpenHandsAuthFailed")
    # No event_type carries the auth_failed discriminator (unlike Claude Code).
    all_event_types = {cls.event_type for cls in _ALL_CLASSES}
    assert "openhands.auth_failed" not in all_event_types
    assert all(not et.endswith("auth_failed") for et in all_event_types)


def test_expected_field_shapes():
    """[Unit] events: Each class declares exactly the C10 fields with the expected annotations.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: each class declares exactly the C10 fields with the expected annotations.
    """
    expected: dict[type, dict[str, type]] = {
        OpenHandsConnected: {"run_id": str, "server_url": str, "mode": str, "timestamp": datetime},
        OpenHandsDisconnected: {"run_id": str, "reason": str, "timestamp": datetime},
        OpenHandsAction: {"run_id": str, "action": str, "arg_count": int, "timestamp": datetime},
        OpenHandsObservation: {
            "run_id": str,
            "observation": str,
            "ok": bool,
            "content_size": int,
            "timestamp": datetime,
        },
        OpenHandsPermissionDenied: {
            "run_id": str,
            "action": str,
            "denied_binary": str,
            "timestamp": datetime,
        },
        OpenHandsCompleted: {
            "run_id": str,
            "token_estimate": int,
            "usage_reported": bool,
            "event_count": int,
            "truncated": bool,
            "timestamp": datetime,
        },
        OpenHandsError: {
            "run_id": str,
            "error_type": str,
            "code": str,
            "event_count": int,
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
def test_no_field_is_typed_any(cls: type):
    """[Unit] events: No field annotation is ``Any`` - only str/int/bool/datetime allowed (C10).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no field annotation is ``Any`` - only str/int/bool/datetime allowed (C10).
    """
    allowed = {"str", "int", "bool", "datetime"}
    for f in dataclasses.fields(cls):
        assert f.type in allowed, f"{cls.__name__}.{f.name} -> {f.type}"


# ---------------------------------------------------------------------------
# Construction semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_frozen_assignment_raises(cls: type):
    """[Unit] events: Instances are immutable: attribute assignment raises ``FrozenInstanceError``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: instances are immutable: attribute assignment raises ``FrozenInstanceError``.
    """
    event = cls(**_KWARGS[cls])
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.run_id = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_positional_construction_raises(cls: type):
    """[Unit] events: ``kw_only=True`` means positional construction raises ``TypeError``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``kw_only=True`` means positional construction raises ``TypeError``.
    """
    positional = list(_KWARGS[cls].values())
    with pytest.raises(TypeError):
        cls(*positional)


@pytest.mark.parametrize("event, _event_type", _INSTANCES)
def test_run_id_and_tz_aware_utc_timestamp(event: DomainEvent, _event_type: str):
    """[Unit] events: Every event carries ``run_id: str`` and a tz-aware UTC ``timestamp``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: every event carries ``run_id: str`` and a tz-aware UTC ``timestamp``.
    """
    assert isinstance(event.run_id, str)
    assert isinstance(event.timestamp, datetime)
    assert event.timestamp.tzinfo is not None
    # tz-aware AND UTC: a zero offset on a non-None tzinfo is what we require.
    assert event.timestamp.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# C13 payload-free invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_no_payload_bearing_fields(cls: type):
    """[Unit] events: No field name hints at action args, observation output, a command line, or a raw error (C13).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no field name hints at action args, observation output, a command line, or a raw error.
    """
    for f in dataclasses.fields(cls):
        name = f.name.lower()
        # ``arg_count``/``content_size`` are counts/sizes, not content - explicitly allowed.
        if name in _COUNT_SIZE_EXEMPTIONS:
            continue
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name, f"{cls.__name__}.{f.name} looks payload-bearing ({token})"


def test_token_estimate_only_on_completed():
    """[Unit] events: ``token_estimate`` lives on :class:`OpenHandsCompleted` alone (C9/C10).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``token_estimate`` lives on :class:`OpenHandsCompleted` alone (C9/C10).
    """
    carriers = [cls for cls in _ALL_CLASSES if "token_estimate" in {f.name for f in dataclasses.fields(cls)}]
    assert carriers == [OpenHandsCompleted]


def test_usage_reported_provenance_flag_distinguishes_c9_sources():
    """[Unit] events: ``usage_reported`` distinguishes server-reported usage from the boundary estimate (C9).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``usage_reported`` records the C9 provenance of ``token_estimate`` without the payload.
    """
    server_reported = OpenHandsCompleted(
        run_id="r1", token_estimate=1024, usage_reported=True, event_count=5, truncated=False
    )
    boundary_estimate = OpenHandsCompleted(
        run_id="r1", token_estimate=1, usage_reported=False, event_count=5, truncated=False
    )
    assert server_reported.usage_reported is True
    assert boundary_estimate.usage_reported is False
    # The provenance flag never carries the usage payload itself - only the token figure and the flag.
    completed_fields = {f.name for f in dataclasses.fields(OpenHandsCompleted)}
    assert completed_fields == {"run_id", "token_estimate", "usage_reported", "event_count", "truncated", "timestamp"}


def test_server_url_only_on_connected():
    """[Unit] events: A ``server_url`` value is carried only by :class:`OpenHandsConnected` (config, not payload).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no action/observation/error event carries a ``server_url`` value (C13).
    """
    carriers = [cls for cls in _ALL_CLASSES if "server_url" in {f.name for f in dataclasses.fields(cls)}]
    assert carriers == [OpenHandsConnected]


def test_import_pulls_in_no_client_library():
    """[Unit] events: Importing the leaf events module pulls in no OpenHands client library (C3).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: importing ``events`` never imports ``httpx``, ``websockets``, or ``grpc`` (C3).
    """
    forbidden = ("httpx", "websockets", "grpc")
    absent_before = {name for name in forbidden if name not in sys.modules}
    reimported = importlib.import_module("aegis_swr.openhands.events")
    assert reimported is events_module
    for name in absent_before:
        assert name not in sys.modules


# ---------------------------------------------------------------------------
# Live EventBus round-trip - proves the DomainEvent-subclass decision works
# ---------------------------------------------------------------------------


def test_roundtrip_all_seven_via_domain_event_subscription():
    """[Unit] events: One ``DomainEvent`` subscriber receives all seven OpenHands events in order.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a ``DomainEvent`` subscriber receives every OpenHands event (the plain-dataclass trap).
    """
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(DomainEvent, received.append)

    for event, _event_type in _INSTANCES:
        bus.publish(event)

    assert received == [event for event, _ in _INSTANCES]
    assert [e.event_type for e in received] == [event_type for _, event_type in _INSTANCES]


@pytest.mark.parametrize("event, _event_type", _INSTANCES)
def test_roundtrip_via_specific_subscription(event: DomainEvent, _event_type: str):
    """[Unit] events: A subscriber to the concrete class receives exactly that published instance.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a subscriber to the concrete class receives exactly that published instance.
    """
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(type(event), received.append)

    bus.publish(event)

    assert received == [event]


def test_specific_subscription_receives_only_its_own_event():
    """[Unit] events: A concrete-class subscriber never receives a different OpenHands event.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: subscribing to one event class never receives a different OpenHands event.
    """
    bus = EventBus()
    connected: list[DomainEvent] = []
    bus.subscribe(OpenHandsConnected, connected.append)

    for event, _event_type in _INSTANCES:
        bus.publish(event)

    connected_instances = [event for event, _ in _INSTANCES if isinstance(event, OpenHandsConnected)]
    assert connected == connected_instances
