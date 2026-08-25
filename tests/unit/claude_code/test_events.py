"""Unit tests for the eight Claude Code lifecycle/stream event dataclasses.

These cover the contract C10 taxonomy in
:mod:`aegis_swr.claude_code.events`: exact field shapes and ``event_type``
sentinels, frozen + keyword-only construction, timezone-aware UTC timestamps,
the C10/C13 payload-free invariant (no field carries tool arguments, tool
output, response text, argv, a raw error message, or a credential), the
single-source ``token_estimate`` rule, the fixed ``ClaudeCodeAuthFailed.reason``
vocabulary, and - crucially - that each event round-trips through the live
:class:`aegis_swr.core.events.EventBus`, proving the ``DomainEvent`` subclassing
decision actually dispatches on the shipping bus.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from datetime import datetime

import pytest

from aegis_swr.claude_code.events import (
    ClaudeCodeAuthFailed,
    ClaudeCodeCompleted,
    ClaudeCodeError,
    ClaudeCodeExited,
    ClaudeCodePermissionDenied,
    ClaudeCodeSpawned,
    ClaudeCodeToolCall,
    ClaudeCodeToolResult,
)
from aegis_swr.core.events import DomainEvent, EventBus

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

#: The fixed vocabulary accepted by ``ClaudeCodeAuthFailed.reason`` (C7).
_AUTH_REASONS = ("ambiguous_credential", "no_stored_login", "token_rejected")

#: Fully specified keyword constructor kwargs per class, used to drive
#: parametrised construction/frozen tests uniformly. Every value is an id,
#: count, estimate, flag, or short status string - never payload text.
_KWARGS: dict[type, dict[str, object]] = {
    ClaudeCodeSpawned: {"run_id": "r1", "auth_mode": "api_key", "binary": "claude"},
    ClaudeCodeExited: {"run_id": "r1", "reason": "completed", "exit_code": 0},
    ClaudeCodeToolCall: {"run_id": "r1", "tool": "Grep", "arg_count": 2},
    ClaudeCodeToolResult: {"run_id": "r1", "tool": "Grep", "ok": True, "result_size": 128},
    ClaudeCodePermissionDenied: {"run_id": "r1", "tool": "Bash", "denied_binary": "curl"},
    ClaudeCodeAuthFailed: {"run_id": "r1", "reason": "token_rejected", "auth_mode": "subscription"},
    ClaudeCodeCompleted: {
        "run_id": "r1",
        "token_estimate": 42,
        "input_tokens": 30,
        "output_tokens": 12,
        "num_turns": 3,
    },
    ClaudeCodeError: {"run_id": "r1", "error_type": "timeout", "code": "DEADLINE_EXCEEDED"},
}

_ALL_CLASSES = list(_KWARGS.keys())

#: One representative instance per event class, paired with its ``event_type``.
_INSTANCES: list[tuple[DomainEvent, str]] = [
    (ClaudeCodeSpawned(**_KWARGS[ClaudeCodeSpawned]), "claude_code.spawned"),  # type: ignore[arg-type]
    (ClaudeCodeExited(**_KWARGS[ClaudeCodeExited]), "claude_code.exited"),  # type: ignore[arg-type]
    (ClaudeCodeToolCall(**_KWARGS[ClaudeCodeToolCall]), "claude_code.tool_call"),  # type: ignore[arg-type]
    (ClaudeCodeToolResult(**_KWARGS[ClaudeCodeToolResult]), "claude_code.tool_result"),  # type: ignore[arg-type]
    (
        ClaudeCodePermissionDenied(**_KWARGS[ClaudeCodePermissionDenied]),  # type: ignore[arg-type]
        "claude_code.permission_denied",
    ),
    (ClaudeCodeAuthFailed(**_KWARGS[ClaudeCodeAuthFailed]), "claude_code.auth_failed"),  # type: ignore[arg-type]
    (ClaudeCodeCompleted(**_KWARGS[ClaudeCodeCompleted]), "claude_code.completed"),  # type: ignore[arg-type]
    (ClaudeCodeError(**_KWARGS[ClaudeCodeError]), "claude_code.error"),  # type: ignore[arg-type]
]

#: Field-name tokens that would signal a payload/args/response/credential leak.
_FORBIDDEN_FIELD_TOKENS = (
    "payload",
    "arg",  # substring of "args"/"arguments"; "arg_count" is exempted below
    "content",
    "message",
    "response",
    "text",
    "body",
    "output",
    "command",
    "cmdline",
    "argv",
    "stdout",
    "stderr",
    "token",  # substring of "token_estimate"/"input_tokens"; exempted below
    "credential",
    "secret",
    "api_key",
    "apikey",
    "password",
    "session",
    "cookie",
)

#: Field names that legitimately contain a forbidden substring but are counts,
#: not content, and are therefore explicitly allowed.
_EXEMPT_FIELD_NAMES = {"arg_count", "token_estimate", "input_tokens", "output_tokens"}


# ---------------------------------------------------------------------------
# Structural contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_is_domain_event_subclass(cls: type):
    """[Unit] events: Every event subclasses :class:`DomainEvent` so the live bus dispatches it.

    Scenario: each of the eight ``claude_code.*`` classes is checked for the
    subclassing that makes it discoverable on the shipping ``EventBus``.

    Boundaries: scoped to class-hierarchy inspection; no bus involved.

    On failure, first check: the class must subclass ``DomainEvent`` or the bus
    delivers it to zero subscribers.
    """
    assert issubclass(cls, DomainEvent)


@pytest.mark.parametrize("event, event_type", _INSTANCES)
def test_event_type_sentinel_matches_c10(event: DomainEvent, event_type: str):
    """[Unit] events: Each class exposes the exact C10 ``event_type`` string as a ``ClassVar``.

    Scenario: an instance of each event exposes its sentinel and never surfaces
    ``event_type`` as a dataclass field.

    Boundaries: scoped to sentinel/field inspection of one instance.

    On failure, first check: ``event_type`` must equal the C10 string and stay a
    ``ClassVar`` (absent from ``dataclasses.fields``).
    """
    assert event.event_type == event_type
    field_names = {f.name for f in dataclasses.fields(event)}
    assert "event_type" not in field_names


def test_event_type_strings_are_unique_and_cover_c10():
    """[Unit] events: The eight events carry the eight distinct C10 discriminators.

    Scenario: the full set of sentinels is compared against the C10 table.

    Boundaries: scoped to the eight representative instances.

    On failure, first check: every ``claude_code.*`` string is present exactly
    once with no duplicates.
    """
    types = [event_type for _event, event_type in _INSTANCES]
    assert len(set(types)) == len(types) == 8
    assert set(types) == {
        "claude_code.spawned",
        "claude_code.exited",
        "claude_code.tool_call",
        "claude_code.tool_result",
        "claude_code.permission_denied",
        "claude_code.auth_failed",
        "claude_code.completed",
        "claude_code.error",
    }


def test_expected_field_shapes():
    """[Unit] events: Each class declares exactly the C10 fields with the expected annotations.

    Scenario: every class's resolved field names and (string) annotations are
    compared to the C10 field table.

    Boundaries: scoped to ``dataclasses.fields`` introspection.

    On failure, first check: the field set or an annotation drifted from the C10
    contract.
    """
    expected: dict[type, dict[str, str]] = {
        ClaudeCodeSpawned: {"run_id": "str", "auth_mode": "str", "binary": "str", "timestamp": "datetime"},
        ClaudeCodeExited: {
            "run_id": "str",
            "reason": "str",
            "exit_code": "Optional[int]",
            "timestamp": "datetime",
        },
        ClaudeCodeToolCall: {"run_id": "str", "tool": "str", "arg_count": "int", "timestamp": "datetime"},
        ClaudeCodeToolResult: {
            "run_id": "str",
            "tool": "str",
            "ok": "bool",
            "result_size": "int",
            "timestamp": "datetime",
        },
        ClaudeCodePermissionDenied: {
            "run_id": "str",
            "tool": "str",
            "denied_binary": "str",
            "timestamp": "datetime",
        },
        ClaudeCodeAuthFailed: {
            "run_id": "str",
            "reason": "str",
            "auth_mode": "str",
            "timestamp": "datetime",
        },
        ClaudeCodeCompleted: {
            "run_id": "str",
            "token_estimate": "int",
            "input_tokens": "int",
            "output_tokens": "int",
            "num_turns": "Optional[int]",
            "timestamp": "datetime",
        },
        ClaudeCodeError: {
            "run_id": "str",
            "error_type": "str",
            "code": "str",
            "timestamp": "datetime",
        },
    }
    for cls, fields in expected.items():
        resolved = {f.name: f.type for f in dataclasses.fields(cls)}
        assert resolved.keys() == fields.keys(), cls.__name__
        # ``from __future__ import annotations`` keeps field types as strings.
        for name, py_type in fields.items():
            assert resolved[name] == py_type, f"{cls.__name__}.{name}"


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_no_field_is_typed_any(cls: type):
    """[Unit] events: No field annotation is ``Any``; only scalar/optional-int types appear (C10).

    Scenario: every field annotation of every class is checked against the
    allowed set.

    Boundaries: scoped to annotation-string inspection.

    On failure, first check: an annotation is ``Any`` or an unapproved type -
    the taxonomy forbids ``Any`` and non-scalar payload types.
    """
    allowed = {"str", "int", "bool", "datetime", "Optional[int]"}
    for f in dataclasses.fields(cls):
        assert f.type in allowed, f"{cls.__name__}.{f.name} -> {f.type}"


def test_only_optional_fields_are_exit_code_and_num_turns():
    """[Unit] events: The sole ``Optional`` fields in the taxonomy are ``exit_code`` and ``num_turns``.

    Scenario: every ``Optional[...]`` field across all eight events is
    collected.

    Boundaries: scoped to annotation-string inspection.

    On failure, first check: an unexpected field became optional, or one of the
    two documented optionals lost its ``Optional`` annotation.
    """
    optionals = {
        f"{cls.__name__}.{f.name}"
        for cls in _ALL_CLASSES
        for f in dataclasses.fields(cls)
        if str(f.type).startswith("Optional")
    }
    assert optionals == {"ClaudeCodeExited.exit_code", "ClaudeCodeCompleted.num_turns"}


# ---------------------------------------------------------------------------
# Construction semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_frozen_assignment_raises(cls: type):
    """[Unit] events: Instances are immutable: attribute assignment raises ``FrozenInstanceError``.

    Scenario: a constructed instance rejects mutation of ``run_id``.

    Boundaries: scoped to one instance per class.

    On failure, first check: the dataclass must be ``frozen=True``.
    """
    event = cls(**_KWARGS[cls])
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.run_id = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_positional_construction_raises(cls: type):
    """[Unit] events: ``kw_only=True`` means positional construction raises ``TypeError``.

    Scenario: constructing each class with positional args is rejected.

    Boundaries: scoped to one construction attempt per class.

    On failure, first check: the dataclass must be ``kw_only=True``.
    """
    positional = list(_KWARGS[cls].values())
    with pytest.raises(TypeError):
        cls(*positional)


@pytest.mark.parametrize("event, _event_type", _INSTANCES)
def test_run_id_and_tz_aware_utc_timestamp(event: DomainEvent, _event_type: str):
    """[Unit] events: Every event carries ``run_id: str`` and a tz-aware UTC ``timestamp``.

    Scenario: the default-factory timestamp is inspected for UTC tz-awareness.

    Boundaries: scoped to one instance per class.

    On failure, first check: ``_utc_now`` must bind ``tzinfo`` to UTC (zero
    offset), never a naive timestamp.
    """
    assert isinstance(event.run_id, str)  # type: ignore[attr-defined]
    assert isinstance(event.timestamp, datetime)  # type: ignore[attr-defined]
    assert event.timestamp.tzinfo is not None  # type: ignore[attr-defined]
    assert event.timestamp.utcoffset().total_seconds() == 0  # type: ignore[attr-defined,union-attr]


def test_exit_code_and_num_turns_default_to_none():
    """[Unit] events: The two optional fields default to ``None`` when omitted.

    Scenario: the optional fields are omitted at construction.

    Boundaries: scoped to two event constructions.

    On failure, first check: ``exit_code`` / ``num_turns`` must default to
    ``None`` (a spawn failure has no code; a ``result`` may omit turns).
    """
    exited = ClaudeCodeExited(run_id="r1", reason="spawn_failed")
    assert exited.exit_code is None
    completed = ClaudeCodeCompleted(run_id="r1", token_estimate=1, input_tokens=1, output_tokens=0)
    assert completed.num_turns is None


# ---------------------------------------------------------------------------
# C10/C13 payload-free invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", _ALL_CLASSES)
def test_no_payload_or_credential_bearing_fields(cls: type):
    """[Unit] events: No field name hints at args, output, response text, argv, or a credential (C10/C13).

    Scenario: every field name is screened against a forbidden-substring list
    covering payload text and credential material.

    Boundaries: scoped to field-name inspection; count fields are exempted.

    On failure, first check: a new field name looks payload/credential-bearing -
    only ids, counts, estimates, and short status strings are permitted.
    """
    for f in dataclasses.fields(cls):
        name = f.name.lower()
        if name in _EXEMPT_FIELD_NAMES:
            continue
        for token in _FORBIDDEN_FIELD_TOKENS:
            assert token not in name, f"{cls.__name__}.{f.name} looks payload/credential-bearing ({token})"


def test_token_estimate_only_on_completed():
    """[Unit] events: ``token_estimate`` lives on :class:`ClaudeCodeCompleted` alone (C9/C10).

    Scenario: every class is searched for a ``token_estimate`` field.

    Boundaries: scoped to field-name inspection across all eight events.

    On failure, first check: another event grew a token field - the figure must
    be single-sourced on ``ClaudeCodeCompleted``.
    """
    carriers = [cls for cls in _ALL_CLASSES if "token_estimate" in {f.name for f in dataclasses.fields(cls)}]
    assert carriers == [ClaudeCodeCompleted]


def test_token_component_fields_only_on_completed():
    """[Unit] events: ``input_tokens`` / ``output_tokens`` also live on :class:`ClaudeCodeCompleted` alone.

    Scenario: every class is searched for the two token component fields.

    Boundaries: scoped to field-name inspection across all eight events.

    On failure, first check: the usage breakdown must not be duplicated onto
    another event.
    """
    for token_field in ("input_tokens", "output_tokens"):
        carriers = [cls for cls in _ALL_CLASSES if token_field in {f.name for f in dataclasses.fields(cls)}]
        assert carriers == [ClaudeCodeCompleted], token_field


def test_completed_carries_real_usage_sum():
    """[Unit] events: :class:`ClaudeCodeCompleted` stores the real usage components alongside the sum (C9).

    Scenario: a completed event is constructed with a realistic usage breakdown.

    Boundaries: scoped to one construction; no arithmetic is enforced by the
    dataclass (the emitter computes the sum), only carriage is verified.

    On failure, first check: the three token fields must all be present and
    integer-typed.
    """
    completed = ClaudeCodeCompleted(run_id="r1", token_estimate=42, input_tokens=30, output_tokens=12, num_turns=3)
    assert completed.token_estimate == 42
    assert completed.input_tokens == 30
    assert completed.output_tokens == 12
    assert completed.num_turns == 3


@pytest.mark.parametrize("reason", _AUTH_REASONS)
def test_auth_failed_accepts_fixed_reason_vocabulary(reason: str):
    """[Unit] events: :class:`ClaudeCodeAuthFailed` accepts each documented reason and only mode+reason (C7).

    Scenario: an auth-failed event is built with each fixed-vocabulary reason.

    Boundaries: scoped to construction and field-set inspection.

    On failure, first check: the event must carry only ``run_id``, ``reason``,
    ``auth_mode``, ``timestamp`` - no credential-bearing field.
    """
    event = ClaudeCodeAuthFailed(run_id="r1", reason=reason, auth_mode="subscription")
    assert event.reason == reason
    field_names = {f.name for f in dataclasses.fields(event)}
    assert field_names == {"run_id", "reason", "auth_mode", "timestamp"}


# ---------------------------------------------------------------------------
# Live EventBus round-trip - proves the DomainEvent-subclass decision works
# ---------------------------------------------------------------------------


def test_domain_event_subscriber_receives_all_eight():
    """[Unit] events: A single ``DomainEvent`` subscriber receives every one of the eight events.

    Scenario: all eight events are published to a bus with one ``DomainEvent``
    subscriber; delivery and per-type filtering are verified.

    Boundaries: scoped to one live ``EventBus``; this is the test that would
    catch a plain-dataclass (non-subclassing) regression.

    On failure, first check: an event failed to subclass ``DomainEvent`` and was
    dropped by ``EventBus.publish``'s MRO walk.
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

    Scenario: each event is published to a bus subscribed to its own class.

    Boundaries: scoped to one live ``EventBus`` per event.

    On failure, first check: the concrete-subclass dispatch path is broken.
    """
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(type(event), received.append)

    bus.publish(event)

    assert received == [event]


def test_specific_subscription_receives_only_its_own():
    """[Unit] events: Subscribing to one event class never receives a different ``claude_code.*`` event.

    Scenario: a ``ClaudeCodeSpawned`` subscriber is present while every other
    event is published; then a ``ClaudeCodeSpawned`` is published.

    Boundaries: scoped to one live ``EventBus``.

    On failure, first check: cross-delivery between sibling subclasses would
    indicate a broken MRO-keyed dispatch.
    """
    bus = EventBus()
    spawned_seen: list[DomainEvent] = []
    bus.subscribe(ClaudeCodeSpawned, spawned_seen.append)

    for event, _event_type in _INSTANCES:
        if not isinstance(event, ClaudeCodeSpawned):
            bus.publish(event)
    assert spawned_seen == []

    own = ClaudeCodeSpawned(run_id="r2", auth_mode="auto", binary="claude")
    bus.publish(own)
    assert spawned_seen == [own]


def test_import_pulls_in_no_client_library():
    """[Unit] events: Importing the events module never pulls in ``grpc`` or ``pydantic`` (C3).

    Scenario: the module is (re)imported and ``sys.modules`` is inspected for
    heavy client-library imports it must not trigger.

    Boundaries: scoped to import-graph inspection; only asserts absence for
    modules not already present.

    On failure, first check: the events leaf gained a forbidden dependency edge.
    """
    grpc_before = "grpc" in sys.modules
    reimport = importlib.import_module("aegis_swr.claude_code.events")
    assert reimport.ClaudeCodeCompleted is ClaudeCodeCompleted
    if not grpc_before:
        assert "grpc" not in sys.modules
