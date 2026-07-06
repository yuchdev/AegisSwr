"""Unit tests for the view adapters (state transitions, not pixels).

These exercise ``WarRoomView`` by driving a real ``EventBus`` with a headless
``Console`` (``StringIO`` file, ``auto_refresh=False`` so no background thread)
and asserting on the view's internal state - agent lifecycle, consensus
history, evidence stream contents - plus the pure formatting helpers.
"""

from __future__ import annotations

import io
import struct
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.text import Text

from aegis_swr.core.events import (
    AgentSpoke,
    ConsensusEvaluated,
    EventBus,
    EvidenceExtracted,
    HumanInputRequired,
    InvestigationCompleted,
    InvestigationStarted,
)
from aegis_swr.core.schemas import (
    AgentTurn,
    ConfidenceLevel,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    RCAReport,
)
from aegis_swr.views.rich_view import (
    AGENT_SEQUENCE,
    AgentState,
    RichView,
    WarRoomView,
    _build_diagnosis,
    _fmt_elapsed,
    _fmt_stamp,
    _spinner_char,
    _truncate,
    make_view,
    render_verdict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headless_console(width: int = 120, height: int = 40) -> Console:
    return Console(file=io.StringIO(), force_terminal=True, width=width, height=height)


def _crash_source() -> IncidentSource:
    return IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path="C:/dumps/CrashUi.dmp")


def _report(*, hitl: bool = False) -> RCAReport:
    from aegis_swr.core.schemas import HITLRequest

    return RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        root_cause="UAF in CImage::Load",
        confidence_score=0.87,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(root_cause="UAF", confidence=0.87),
        consensus_rounds=2,
        hitl_request=HITLRequest(question="more data?", context_summary="deadlock")
        if hitl
        else None,
    )


def _evidence_brief() -> dict:
    return {
        "fault_class": "access_violation",
        "faulting_module": "ImageScope.exe",
        "faulting_function": "CImage::Load",
        "symbol_resolution_score": 0.92,
        "stack_frames": [
            {"function": "CImage::Load+0x3f"},
            {"function": "CImageView::OnPaint"},
            {"function": "RenderThread::Run"},
            {"function": "should_not_appear"},
        ],
    }


def _run_round(bus: EventBus, turn_number: int, confidence: float):
    for node, name in AGENT_SEQUENCE:
        bus.publish(
            AgentSpoke(
                node=node,
                turn=AgentTurn(
                    agent=name,
                    turn_number=turn_number,
                    message=f"finding from {name}",
                    confidence_score=confidence,
                ),
            )
        )


def _plain(renderable) -> str:
    """Plain text of a stored stream entry - a ``Text`` or a ``Padding`` of one.

    Sub-detail lines are wrapped in ``rich.padding.Padding`` (indented, no
    gutter); unwrap to reach the inner ``Text``.
    """
    inner = getattr(renderable, "renderable", renderable)
    return inner.plain


def _evidence_text(view: WarRoomView) -> str:
    return " | ".join(_plain(entry.text) for entry in view._evidence_log.lines)


def _process_text(view: WarRoomView) -> str:
    return " | ".join(_plain(entry.text) for entry in view._process_log.lines)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_spinner_char_cycles_through_all_frames():
    """
    [Unit] views: verifies spinner char cycles through all frames.

    Scenario:
        Given test inputs and fixtures for spinner char cycles through all frames
        When test_spinner_char_cycles_through_all_frames executes the target flow
        Then the expected outcome for spinner char cycles through all frames is confirmed.

    Boundaries:
        - Focus: spinner char cycles through all frames
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to spinner char cycles through all frames
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    from aegis_swr.views.rich_view import SPINNER_FRAMES

    seen = {_spinner_char(t / 10) for t in range(len(SPINNER_FRAMES))}
    assert seen == set(SPINNER_FRAMES)


def test_fmt_elapsed_is_h_mm_ss():
    """
    [Unit] views: verifies fmt elapsed is h mm ss.

    Scenario:
        Given test inputs and fixtures for fmt elapsed is h mm ss
        When test_fmt_elapsed_is_h_mm_ss executes the target flow
        Then the expected outcome for fmt elapsed is h mm ss is confirmed.

    Boundaries:
        - Focus: fmt elapsed is h mm ss
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fmt elapsed is h mm ss
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    assert _fmt_elapsed(0) == "0:00:00"
    assert _fmt_elapsed(102) == "0:01:42"
    assert _fmt_elapsed(3723) == "1:02:03"


def test_fmt_stamp_is_mm_ss():
    """
    [Unit] views: verifies fmt stamp is mm ss.

    Scenario:
        Given test inputs and fixtures for fmt stamp is mm ss
        When test_fmt_stamp_is_mm_ss executes the target flow
        Then the expected outcome for fmt stamp is mm ss is confirmed.

    Boundaries:
        - Focus: fmt stamp is mm ss
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to fmt stamp is mm ss
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    assert _fmt_stamp(0) == "00:00"
    assert _fmt_stamp(108) == "01:48"


def test_truncate_appends_ellipsis():
    """
    [Unit] views: verifies truncate appends ellipsis.

    Scenario:
        Given test inputs and fixtures for truncate appends ellipsis
        When test_truncate_appends_ellipsis executes the target flow
        Then the expected outcome for truncate appends ellipsis is confirmed.

    Boundaries:
        - Focus: truncate appends ellipsis
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to truncate appends ellipsis
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    assert _truncate("short", 20) == "short"
    assert _truncate("a very long finding line", 10) == "a very lo…"
    assert _truncate("x", 1) == ""


def test_agent_state_defaults():
    """
    [Unit] views: verifies agent state defaults.

    Scenario:
        Given test inputs and fixtures for agent state defaults
        When test_agent_state_defaults executes the target flow
        Then the expected outcome for agent state defaults is confirmed.

    Boundaries:
        - Focus: agent state defaults
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to agent state defaults
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    state = AgentState()
    assert state.status == "STANDBY"
    assert state.confidence == 0.0
    assert state.finding == ""


# ---------------------------------------------------------------------------
# make_view selection
# ---------------------------------------------------------------------------


def test_make_view_wide_terminal_is_warroom():
    """
    [Unit] views: verifies make view wide terminal is warroom.

    Scenario:
        Given test inputs and fixtures for make view wide terminal is warroom
        When test_make_view_wide_terminal_is_warroom executes the target flow
        Then the expected outcome for make view wide terminal is warroom is confirmed.

    Boundaries:
        - Focus: make view wide terminal is warroom
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to make view wide terminal is warroom
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = make_view(_headless_console(width=120))
    assert isinstance(view, WarRoomView)


def test_make_view_narrow_terminal_is_richview():
    """
    [Unit] views: verifies make view narrow terminal is richview.

    Scenario:
        Given test inputs and fixtures for make view narrow terminal is richview
        When test_make_view_narrow_terminal_is_richview executes the target flow
        Then the expected outcome for make view narrow terminal is richview is confirmed.

    Boundaries:
        - Focus: make view narrow terminal is richview
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to make view narrow terminal is richview
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = make_view(_headless_console(width=70))
    assert isinstance(view, RichView)


# ---------------------------------------------------------------------------
# WarRoomView event flow
# ---------------------------------------------------------------------------


def test_started_resets_state_and_records_stage_marker():
    """
    [Unit] views: verifies started resets state and records stage marker.

    Scenario:
        Given test inputs and fixtures for started resets state and records stage marker
        When test_started_resets_state_and_records_stage_marker executes the target flow
        Then the expected outcome for started resets state and records stage marker is confirmed.

    Boundaries:
        - Focus: started resets state and records stage marker
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to started resets state and records stage marker
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))

    assert view._incident_label == "CrashUi.dmp"
    assert view._mode == "crash_dump"
    assert view._round == 1
    assert all(s.status == "STANDBY" for s in view._agents.values())
    assert "CDB extraction started" in _evidence_text(view)
    view._stop_live()


def test_evidence_extracted_populates_stream_and_wakes_first_agent():
    """
    [Unit] views: verifies evidence extracted populates stream and wakes first agent.

    Scenario:
        Given test inputs and fixtures for evidence extracted populates stream and wakes first agent
        When test_evidence_extracted_populates_stream_and_wakes_first_agent executes the target flow
        Then the expected outcome for evidence extracted populates stream and wakes first agent is confirmed.

    Boundaries:
        - Focus: evidence extracted populates stream and wakes first agent
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence extracted populates stream and wakes first agent
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))

    text = _evidence_text(view)
    assert "fault_class" in text
    assert "ACCESS_VIOLATION" in text
    assert "ImageScope.exe" in text
    assert "stack[0]" in text
    # Only the top three frames are shown.
    assert "should_not_appear" not in text
    assert view._agents["OS Kernel Agent"].status == "ANALYZING"
    view._stop_live()


def test_agent_spoke_marks_done_and_wakes_next():
    """
    [Unit] views: verifies agent spoke marks done and wakes next.

    Scenario:
        Given test inputs and fixtures for agent spoke marks done and wakes next
        When test_agent_spoke_marks_done_and_wakes_next executes the target flow
        Then the expected outcome for agent spoke marks done and wakes next is confirmed.

    Boundaries:
        - Focus: agent spoke marks done and wakes next
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to agent spoke marks done and wakes next
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    bus.publish(
        AgentSpoke(
            node="os_kernel_node",
            turn=AgentTurn(
                agent="OS Kernel Agent",
                turn_number=1,
                message="UAF on freed heap page",
                confidence_score=0.82,
            ),
        )
    )

    assert view._agents["OS Kernel Agent"].status == "DONE"
    assert view._agents["OS Kernel Agent"].confidence == 0.82
    assert view._agents["OS Kernel Agent"].finding == "UAF on freed heap page"
    # Next agent in sequence woken.
    assert view._agents["Code Analyst Agent"].status == "ANALYZING"
    # Agent communication is process, not evidence.
    assert "OS Kernel » UAF on freed heap page" in _process_text(view)
    assert "OS Kernel »" not in _evidence_text(view)
    view._stop_live()


def test_skeptic_is_last_and_wakes_no_one():
    """
    [Unit] views: verifies skeptic is last and wakes no one.

    Scenario:
        Given test inputs and fixtures for skeptic is last and wakes no one
        When test_skeptic_is_last_and_wakes_no_one executes the target flow
        Then the expected outcome for skeptic is last and wakes no one is confirmed.

    Boundaries:
        - Focus: skeptic is last and wakes no one
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic is last and wakes no one
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.8)

    # All four spoke; none left ANALYZING from the round itself (consensus has
    # not fired yet, so the skeptic's "next" is None).
    assert view._agents["Skeptic Agent"].status == "DONE"
    view._stop_live()


def test_consensus_appends_row_and_resets_agents():
    """
    [Unit] views: verifies consensus appends row and resets agents.

    Scenario:
        Given test inputs and fixtures for consensus appends row and resets agents
        When test_consensus_appends_row_and_resets_agents executes the target flow
        Then the expected outcome for consensus appends row and resets agents is confirmed.

    Boundaries:
        - Focus: consensus appends row and resets agents
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to consensus appends row and resets agents
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.8)
    bus.publish(ConsensusEvaluated(score=0.61, round_number=2))

    assert len(view._consensus_history) == 1
    assert view._consensus_history[0]["round"] == 1
    assert view._consensus_history[0]["score"] == 0.61
    assert view._consensus_history[0]["converged"] is None
    assert "consensus R1" in _process_text(view)
    assert "consensus R1" not in _evidence_text(view)
    view._stop_live()


def test_full_two_round_run_resolves_convergence_markers():
    """
    [Unit] views: verifies full two round run resolves convergence markers.

    Scenario:
        Given test inputs and fixtures for full two round run resolves convergence markers
        When test_full_two_round_run_resolves_convergence_markers executes the target flow
        Then the expected outcome for full two round run resolves convergence markers is confirmed.

    Boundaries:
        - Focus: full two round run resolves convergence markers
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to full two round run resolves convergence markers
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.6)
    bus.publish(ConsensusEvaluated(score=0.61, round_number=2))
    _run_round(bus, turn_number=2, confidence=0.87)
    bus.publish(ConsensusEvaluated(score=0.87, round_number=3))
    bus.publish(InvestigationCompleted(report=_report()))

    assert view._finished is True
    assert view._round == 2
    assert [r["converged"] for r in view._consensus_history] == [False, True]
    assert all(s.status == "DONE" for s in view._agents.values())
    assert "investigation complete" in _process_text(view)
    # A re-deliberation note was recorded when round 2 began.
    assert "re-deliberating" in _process_text(view)
    view._stop_live()


def test_hitl_finish_marks_no_convergence():
    """
    [Unit] views: verifies hitl finish marks no convergence.

    Scenario:
        Given test inputs and fixtures for hitl finish marks no convergence
        When test_hitl_finish_marks_no_convergence executes the target flow
        Then the expected outcome for hitl finish marks no convergence is confirmed.

    Boundaries:
        - Focus: hitl finish marks no convergence
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to hitl finish marks no convergence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.3)
    bus.publish(ConsensusEvaluated(score=0.30, round_number=2))
    bus.publish(HumanInputRequired(report=_report(hitl=True)))

    assert view._finished is True
    assert view._consensus_history[0]["converged"] is False
    assert "human input required" in _process_text(view)
    view._stop_live()


def test_evidence_stream_is_capped():
    """
    [Unit] views: verifies evidence stream is capped.

    Scenario:
        Given test inputs and fixtures for evidence stream is capped
        When test_evidence_stream_is_capped executes the target flow
        Then the expected outcome for evidence stream is capped is confirmed.

    Boundaries:
        - Focus: evidence stream is capped
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence stream is capped
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    for _ in range(view._MAX_EVIDENCE + 50):
        view._add_evidence(view._plain("noise"))
    assert len(view._evidence_log.lines) == view._MAX_EVIDENCE
    view._stop_live()


def test_process_log_is_capped():
    """
    [Unit] views: verifies process log is capped.

    Scenario:
        Given test inputs and fixtures for process log is capped
        When test_process_log_is_capped executes the target flow
        Then the expected outcome for process log is capped is confirmed.

    Boundaries:
        - Focus: process log is capped
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process log is capped
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    for _ in range(view._MAX_EVIDENCE + 50):
        view._add_process(view._plain("chatter"))
    assert len(view._process_log.lines) == view._MAX_EVIDENCE
    view._stop_live()


def test_capping_keeps_reveal_pointer_in_bounds():
    # Trimming the front of the buffer must not leave the reveal pointer past
    # the lines that remain.
    """
    [Unit] views: verifies capping keeps reveal pointer in bounds.

    Scenario:
        Given test inputs and fixtures for capping keeps reveal pointer in bounds
        When test_capping_keeps_reveal_pointer_in_bounds executes the target flow
        Then the expected outcome for capping keeps reveal pointer in bounds is confirmed.

    Boundaries:
        - Focus: capping keeps reveal pointer in bounds
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to capping keeps reveal pointer in bounds
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    view._evidence_log._revealed = 10
    for _ in range(view._MAX_EVIDENCE + 50):
        view._add_evidence(view._plain("noise"))
    assert view._evidence_log._revealed <= len(view._evidence_log.lines)
    view._stop_live()


# ---------------------------------------------------------------------------
# Streaming reveal (scroll in real time, oldest off the top)
# ---------------------------------------------------------------------------


def test_evidence_reveals_gradually_not_all_at_once():
    # A burst of lines must not all surface in a single frame - they stream in.
    """
    [Unit] views: verifies evidence reveals gradually not all at once.

    Scenario:
        Given test inputs and fixtures for evidence reveals gradually not all at once
        When test_evidence_reveals_gradually_not_all_at_once executes the target flow
        Then the expected outcome for evidence reveals gradually not all at once is confirmed.

    Boundaries:
        - Focus: evidence reveals gradually not all at once
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence reveals gradually not all at once
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, _crash_source())
    log = view._evidence_log
    total = len(log.lines)
    assert total > 1
    # Reset the reveal clock to "now" so no time has elapsed for this frame.
    log._revealed = 0
    log._last_reveal = time.monotonic()
    view._render_evidence()
    assert log._revealed < total
    view._stop_live()


def test_evidence_reveal_catches_up_over_time():
    # Once enough time passes the whole buffer is surfaced.
    """
    [Unit] views: verifies evidence reveal catches up over time.

    Scenario:
        Given test inputs and fixtures for evidence reveal catches up over time
        When test_evidence_reveal_catches_up_over_time executes the target flow
        Then the expected outcome for evidence reveal catches up over time is confirmed.

    Boundaries:
        - Focus: evidence reveal catches up over time
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence reveal catches up over time
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, _crash_source())
    log = view._evidence_log
    total = len(log.lines)
    log._revealed = 0
    log._last_reveal = time.monotonic() - 1000  # far in the past
    view._render_evidence()
    assert log._revealed == total
    view._stop_live()


def test_finish_reveals_both_buffers():
    # Freezing the Live block must flush every buffered line in both logs so
    # the final tails (including the completion marker) are visible even if
    # pacing was still behind.
    """
    [Unit] views: verifies finish reveals both buffers.

    Scenario:
        Given test inputs and fixtures for finish reveals both buffers
        When test_finish_reveals_both_buffers executes the target flow
        Then the expected outcome for finish reveals both buffers is confirmed.

    Boundaries:
        - Focus: finish reveals both buffers
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to finish reveals both buffers
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.8)
    view._evidence_log._revealed = 0  # pretend pacing fell behind
    view._process_log._revealed = 0
    bus.publish(InvestigationCompleted(report=_report()))
    assert view._evidence_log._revealed == len(view._evidence_log.lines)
    assert view._process_log._revealed == len(view._process_log.lines)
    view._stop_live()


# ---------------------------------------------------------------------------
# Investigation Process - agent conversation (process, not evidence)
# ---------------------------------------------------------------------------


def test_conversation_lives_in_process_not_evidence():
    """
    [Unit] views: verifies conversation lives in process not evidence.

    Scenario:
        Given test inputs and fixtures for conversation lives in process not evidence
        When test_conversation_lives_in_process_not_evidence executes the target flow
        Then the expected outcome for conversation lives in process not evidence is confirmed.

    Boundaries:
        - Focus: conversation lives in process not evidence
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to conversation lives in process not evidence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.8)
    bus.publish(ConsensusEvaluated(score=0.87, round_number=2))

    process = _process_text(view)
    evidence = _evidence_text(view)
    # Every agent's communication and the consensus check are in the process.
    for _, name in AGENT_SEQUENCE:
        short = name.removesuffix(" Agent")
        assert f"{short} »" in process
    assert "consensus R1" in process
    # …and none of it leaked into the evidence stream.
    assert "»" not in evidence
    assert "consensus" not in evidence
    # The evidence stream still carries the extracted artifacts.
    assert "ACCESS_VIOLATION" in evidence
    view._stop_live()


def test_process_conversation_reveals_gradually():
    # The conversation scrolls in like the evidence stream - not all at once.
    """
    [Unit] views: verifies process conversation reveals gradually.

    Scenario:
        Given test inputs and fixtures for process conversation reveals gradually
        When test_process_conversation_reveals_gradually executes the target flow
        Then the expected outcome for process conversation reveals gradually is confirmed.

    Boundaries:
        - Focus: process conversation reveals gradually
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process conversation reveals gradually
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    _run_round(bus, turn_number=1, confidence=0.8)
    log = view._process_log
    total = len(log.lines)
    assert total > 1
    log._revealed = 0
    log._last_reveal = time.monotonic()
    view._render_process()
    assert log._revealed < total
    view._stop_live()


def _publish_multiline_turn(view: WarRoomView, message: str):
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(
        AgentSpoke(
            node="os_kernel_node",
            turn=AgentTurn(
                agent="OS Kernel Agent",
                turn_number=1,
                message=message,
                confidence_score=0.8,
            ),
        )
    )


def test_process_trace_surfaces_full_agent_reasoning():
    """
    [Unit] views: verifies process trace surfaces full agent reasoning.

    Scenario:
        Given test inputs and fixtures for process trace surfaces full agent reasoning
        When test_process_trace_surfaces_full_agent_reasoning executes the target flow
        Then the expected outcome for process trace surfaces full agent reasoning is confirmed.

    Boundaries:
        - Focus: process trace surfaces full agent reasoning
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process trace surfaces full agent reasoning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    multiline = "headline finding\nsupporting detail one\nsupporting detail two"

    # INFO keeps only the headline …
    info = WarRoomView(_headless_console(), auto_refresh=False)
    _publish_multiline_turn(info, multiline)
    assert "headline finding" in _process_text(info)
    assert "supporting detail two" not in _process_text(info)
    info._stop_live()

    # … process TRACE surfaces the agent's full reasoning. Crucially this is the
    # *process* channel - evidence stays at INFO, proving the two are independent.
    trace = WarRoomView(
        _headless_console(), auto_refresh=False, level="INFO", process_level="TRACE"
    )
    _publish_multiline_turn(trace, multiline)
    text = _process_text(trace)
    assert "headline finding" in text
    assert "supporting detail one" in text
    assert "supporting detail two" in text
    trace._stop_live()


# ---------------------------------------------------------------------------
# Evidence Stream verbosity: INFO summary vs TRACE detail
# ---------------------------------------------------------------------------


def _debug_brief() -> dict:
    """An incident brief carrying the fields the TRACE stream surfaces"""
    brief = _evidence_brief()
    brief.update(
        {
            "dump_hash": "sha256:abc123",
            "exception_code_raw": "0xC0000005",
            "exception_address": "0x00007ffd1234",
            "raw_text_excerpt": "EXCEPTION_ANALYSIS\nFAULTING_IP: CImage::Load+0x3f\nstale this",
            "log_summary": "line a\nline b\nline c",
            "ui_context": {
                "error_message": "Fatal error occurred",
                "ui_elements": ["Fatal", "error", "occurred"],
            },
        }
    )
    return brief


def _start(view: WarRoomView, source: IncidentSource):
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=source))
    bus.publish(EvidenceExtracted(brief=_debug_brief()))


def _write_pcap(path: Path) -> Path:
    header = struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
    record = struct.pack("<IIII", 1_700_000_000, 0, 4, 4) + b"\xde\xad\xbe\xef"
    path.write_bytes(header + record)
    return path


def test_info_level_omits_trace_detail():
    """
    [Unit] views: verifies info level omits trace detail.

    Scenario:
        Given test inputs and fixtures for info level omits trace detail
        When test_info_level_omits_trace_detail executes the target flow
        Then the expected outcome for info level omits trace detail is confirmed.

    Boundaries:
        - Focus: info level omits trace detail
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to info level omits trace detail
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)  # default INFO
    _start(view, _crash_source())
    text = _evidence_text(view)
    # INFO summary fields remain.
    assert "ACCESS_VIOLATION" in text
    assert "stack[0]" in text
    # TRACE-only detail is absent.
    assert "core dump analysis" not in text
    assert "EXCEPTION_ANALYSIS" not in text
    assert "stack[3]" not in text
    assert "should_not_appear" not in text
    assert all(entry.level == "INFO" for entry in view._evidence_log.lines)
    view._stop_live()


def test_trace_level_shows_core_dump_text_and_full_stack():
    """
    [Unit] views: verifies trace level shows core dump text and full stack.

    Scenario:
        Given test inputs and fixtures for trace level shows core dump text and full stack
        When test_trace_level_shows_core_dump_text_and_full_stack executes the target flow
        Then the expected outcome for trace level shows core dump text and full stack is confirmed.

    Boundaries:
        - Focus: trace level shows core dump text and full stack
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to trace level shows core dump text and full stack
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, _crash_source())
    text = _evidence_text(view)
    # Category 1: textual core-dump analysis.
    assert "core dump analysis" in text
    assert "EXCEPTION_ANALYSIS" in text
    # Very detailed fault metadata.
    assert "sha256:abc123" in text
    assert "0xC0000005" in text
    # Full stack beyond the INFO top-three.
    assert "stack[3]" in text
    assert "should_not_appear" in text
    assert any(entry.level == "TRACE" for entry in view._evidence_log.lines)
    view._stop_live()


def _long_excerpt_brief(n: int = 50) -> dict:
    """A brief whose core-dump analysis spans *n* lines."""
    brief = _debug_brief()
    brief["raw_text_excerpt"] = "\n".join(f"ANALYZE_LINE_{i:02d}" for i in range(n))
    return brief


def _start_with(view: WarRoomView, brief: dict, source: IncidentSource):
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=source))
    bus.publish(EvidenceExtracted(brief=brief))


def test_trace_streams_full_core_dump_output():
    """
    [Unit] views: verifies trace streams full core dump output.

    Scenario:
        Given test inputs and fixtures for trace streams full core dump output
        When test_trace_streams_full_core_dump_output executes the target flow
        Then the expected outcome for trace streams full core dump output is confirmed.

    Boundaries:
        - Focus: trace streams full core dump output
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to trace streams full core dump output
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start_with(view, _long_excerpt_brief(50), _crash_source())
    text = _evidence_text(view)
    # TRACE streams the *full* !analyze output (DEBUG collapsed into TRACE, so
    # there is no longer a capped intermediate level).
    assert "core dump analysis (cdb !analyze -v):" in text
    assert "ANALYZE_LINE_00" in text
    assert "ANALYZE_LINE_40" in text
    assert "ANALYZE_LINE_49" in text
    # Detail lines are tagged TRACE.
    assert any(entry.level == "TRACE" for entry in view._evidence_log.lines)
    assert "sha256:abc123" in text
    view._stop_live()


def test_evidence_trace_does_not_surface_agent_reasoning():
    # Evidence TRACE + process INFO: detailed evidence appears, but the agent's
    # extra reasoning lines stay hidden - the two channels are independent.
    """
    [Unit] views: verifies evidence trace does not surface agent reasoning.

    Scenario:
        Given test inputs and fixtures for evidence trace does not surface agent reasoning
        When test_evidence_trace_does_not_surface_agent_reasoning executes the target flow
        Then the expected outcome for evidence trace does not surface agent reasoning is confirmed.

    Boundaries:
        - Focus: evidence trace does not surface agent reasoning
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence trace does not surface agent reasoning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE", process_level="INFO")
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_debug_brief()))
    bus.publish(
        AgentSpoke(
            node="os_kernel_node",
            turn=AgentTurn(
                agent="OS Kernel Agent",
                turn_number=1,
                message="headline finding\nsecret reasoning detail",
                confidence_score=0.8,
            ),
        )
    )
    # Evidence detail is surfaced (evidence channel is TRACE) …
    assert "core dump analysis" in _evidence_text(view)
    # … but the agent's extra reasoning is not (process channel is INFO).
    assert "secret reasoning detail" not in _process_text(view)
    view._stop_live()


def test_evidence_transcript_trace_contains_full_record():
    """
    [Unit] views: verifies evidence transcript trace contains full record.

    Scenario:
        Given test inputs and fixtures for evidence transcript trace contains full record
        When test_evidence_transcript_trace_contains_full_record executes the target flow
        Then the expected outcome for evidence transcript trace contains full record is confirmed.

    Boundaries:
        - Focus: evidence transcript trace contains full record
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence transcript trace contains full record
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, _crash_source())
    transcript = view.evidence_transcript()
    assert "ACCESS_VIOLATION" in transcript
    assert "core dump analysis" in transcript  # TRACE detail present
    assert "EXCEPTION_ANALYSIS" in transcript
    view._stop_live()


def test_evidence_transcript_info_is_summary_only():
    """
    [Unit] views: verifies evidence transcript info is summary only.

    Scenario:
        Given test inputs and fixtures for evidence transcript info is summary only
        When test_evidence_transcript_info_is_summary_only executes the target flow
        Then the expected outcome for evidence transcript info is summary only is confirmed.

    Boundaries:
        - Focus: evidence transcript info is summary only
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to evidence transcript info is summary only
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False)  # default INFO
    _start(view, _crash_source())
    transcript = view.evidence_transcript()
    assert "ACCESS_VIOLATION" in transcript
    assert "core dump analysis" not in transcript  # no TRACE detail at INFO
    view._stop_live()


def test_persist_evidence_writes_transcript_file(tmp_path: Path):
    """
    [Unit] views: verifies persist evidence writes transcript file.

    Scenario:
        Given test inputs and fixtures for persist evidence writes transcript file
        When test_persist_evidence_writes_transcript_file executes the target flow
        Then the expected outcome for persist evidence writes transcript file is confirmed.

    Boundaries:
        - Focus: persist evidence writes transcript file
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to persist evidence writes transcript file
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    from aegis_swr.cli.formatters import _persist_evidence

    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, _crash_source())
    report = _report()
    path = _persist_evidence(view, str(tmp_path / "evidence"), report)
    assert path is not None and path.exists()
    assert path.name == f"evidence-{report.incident_id}.log"
    text = path.read_text(encoding="utf-8")
    assert "ACCESS_VIOLATION" in text
    assert "core dump analysis" in text
    view._stop_live()


def test_persist_evidence_is_noop_without_a_directory():
    """
    [Unit] views: verifies persist evidence is noop without a directory.

    Scenario:
        Given test inputs and fixtures for persist evidence is noop without a directory
        When test_persist_evidence_is_noop_without_a_directory executes the target flow
        Then the expected outcome for persist evidence is noop without a directory is confirmed.

    Boundaries:
        - Focus: persist evidence is noop without a directory
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to persist evidence is noop without a directory
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    from aegis_swr.cli.formatters import _persist_evidence

    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, _crash_source())
    assert _persist_evidence(view, None, _report()) is None
    view._stop_live()


def test_stream_log_visible_respects_level_rank():
    """
    [Unit] views: verifies stream log visible respects level rank.

    Scenario:
        Given test inputs and fixtures for stream log visible respects level rank
        When test_stream_log_visible_respects_level_rank executes the target flow
        Then the expected outcome for stream log visible respects level rank is confirmed.

    Boundaries:
        - Focus: stream log visible respects level rank
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to stream log visible respects level rank
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    from aegis_swr.views.rich_view import _StreamLog

    log = _StreamLog(max_lines=100, reveal_interval=0.0)
    log.reset(0.0)
    log.append(Text("info-line"), level="INFO")
    log.append(Text("trace-line"), level="TRACE")
    log.reveal_all()

    def shown(level: str) -> list[str]:
        lines = log.visible(now=1.0, finished=True, level=level, max_lines=100)
        return [_plain(r) for r in lines]

    # Two levels after the DEBUG->TRACE collapse: INFO shows only INFO-tagged
    # lines; TRACE shows everything.
    assert shown("INFO") == ["info-line"]
    assert shown("TRACE") == ["info-line", "trace-line"]


def test_make_view_accepts_trace_level():
    """
    [Unit] views: verifies make view accepts trace level.

    Scenario:
        Given test inputs and fixtures for make view accepts trace level
        When test_make_view_accepts_trace_level executes the target flow
        Then the expected outcome for make view accepts trace level is confirmed.

    Boundaries:
        - Focus: make view accepts trace level
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to make view accepts trace level
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = make_view(_headless_console(width=120), level="TRACE")
    assert view._evidence_level == "TRACE"


def test_trace_level_shows_log_window(tmp_path: Path):
    """
    [Unit] views: verifies trace level shows log window.

    Scenario:
        Given test inputs and fixtures for trace level shows log window
        When test_trace_level_shows_log_window executes the target flow
        Then the expected outcome for trace level shows log window is confirmed.

    Boundaries:
        - Focus: trace level shows log window
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to trace level shows log window
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    log = tmp_path / "app.log"
    log.write_text("2026-06-04T14:02:11 ERROR boom\n")
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        log_paths=[str(log)],
        incident_timestamp=datetime(2026, 6, 4, 14, 2, 11),
    )
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, source)
    text = _evidence_text(view)
    # Category 2: ±2 minute window for the analyzed log file.
    assert "app.log" in text
    assert "14:00:11" in text
    assert "14:04:11" in text
    assert "±2m" in text
    view._stop_live()


def test_trace_level_shows_screenshot_properties(tmp_path: Path):
    """
    [Unit] views: verifies trace level shows screenshot properties.

    Scenario:
        Given test inputs and fixtures for trace level shows screenshot properties
        When test_trace_level_shows_screenshot_properties executes the target flow
        Then the expected outcome for trace level shows screenshot properties is confirmed.

    Boundaries:
        - Focus: trace level shows screenshot properties
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to trace level shows screenshot properties
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    shot = tmp_path / "error.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        screenshot_paths=[str(shot)],
    )
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, source)
    text = _evidence_text(view)
    # Category 3: screenshot name + properties + OCR summary.
    assert "screenshot" in text
    assert "error.png" in text
    assert "48 B" in text
    assert "OCR" in text
    view._stop_live()


def test_trace_level_shows_network_capture_metadata(tmp_path: Path):
    """
    [Unit] views: verifies trace level shows network capture metadata.

    Scenario:
        Given test inputs and fixtures for trace level shows network capture metadata
        When test_trace_level_shows_network_capture_metadata executes the target flow
        Then the expected outcome for trace level shows network capture metadata is confirmed.

    Boundaries:
        - Focus: trace level shows network capture metadata
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to trace level shows network capture metadata
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    cap = _write_pcap(tmp_path / "traffic.pcap")
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        network_capture_paths=[str(cap)],
    )
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start(view, source)
    text = _evidence_text(view)
    # Category 4: network traffic capture metadata.
    assert "netcap" in text
    assert "traffic.pcap" in text
    assert "pcap v2.4" in text
    assert "ETHERNET" in text
    assert "packets 1" in text
    view._stop_live()


def test_make_view_debug_collapses_to_trace():
    # DEBUG is no longer a distinct level - it collapses into TRACE.
    """
    [Unit] views: verifies make view debug collapses to trace.

    Scenario:
        Given test inputs and fixtures for make view debug collapses to trace
        When test_make_view_debug_collapses_to_trace executes the target flow
        Then the expected outcome for make view debug collapses to trace is confirmed.

    Boundaries:
        - Focus: make view debug collapses to trace
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to make view debug collapses to trace
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = make_view(_headless_console(width=120), level="DEBUG")
    assert isinstance(view, WarRoomView)
    assert view._evidence_level == "TRACE"


def test_make_view_default_level_is_info():
    """
    [Unit] views: verifies make view default level is info.

    Scenario:
        Given test inputs and fixtures for make view default level is info
        When test_make_view_default_level_is_info executes the target flow
        Then the expected outcome for make view default level is info is confirmed.

    Boundaries:
        - Focus: make view default level is info
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to make view default level is info
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = make_view(_headless_console(width=120))
    assert isinstance(view, WarRoomView)
    assert view._evidence_level == "INFO"


def test_process_level_defaults_to_evidence_level():
    # The investigation-process channel defaults to the evidence level when not
    # supplied (log-subsystem split, plan Part III - Phase A threading).
    """
    [Unit] views: verifies process level defaults to evidence level.

    Scenario:
        Given test inputs and fixtures for process level defaults to evidence level
        When test_process_level_defaults_to_evidence_level executes the target flow
        Then the expected outcome for process level defaults to evidence level is confirmed.

    Boundaries:
        - Focus: process level defaults to evidence level
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to process level defaults to evidence level
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    assert view._process_level == "TRACE"


def test_make_view_threads_independent_process_level():
    # make_view forwards an explicit process_level distinct from the evidence
    # level; both channels are carried end-to-end without affecting each other.
    """
    [Unit] views: verifies make view threads independent process level.

    Scenario:
        Given test inputs and fixtures for make view threads independent process level
        When test_make_view_threads_independent_process_level executes the target flow
        Then the expected outcome for make view threads independent process level is confirmed.

    Boundaries:
        - Focus: make view threads independent process level
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to make view threads independent process level
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = make_view(_headless_console(width=120), level="INFO", process_level="TRACE")
    assert isinstance(view, WarRoomView)
    assert view._evidence_level == "INFO"
    assert view._process_level == "TRACE"


def test_trace_evidence_render_does_not_raise(tmp_path: Path):
    """
    [Unit] views: verifies trace evidence render does not raise.

    Scenario:
        Given test inputs and fixtures for trace evidence render does not raise
        When test_trace_evidence_render_does_not_raise executes the target flow
        Then the expected outcome for trace evidence render does not raise is confirmed.

    Boundaries:
        - Focus: trace evidence render does not raise
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to trace evidence render does not raise
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    cap = _write_pcap(tmp_path / "traffic.pcap")
    shot = tmp_path / "error.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    log = tmp_path / "app.log"
    log.write_text("2026-06-04T14:02:11 ERROR boom\n")
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        log_paths=[str(log)],
        screenshot_paths=[str(shot)],
        network_capture_paths=[str(cap)],
        incident_timestamp=datetime(2026, 6, 4, 14, 2, 11),
    )
    view = WarRoomView(_headless_console(height=50), auto_refresh=False, level="TRACE")
    _start(view, source)
    view._console.print(view._render_evidence())
    view._stop_live()


# ---------------------------------------------------------------------------
# Rendering smoke tests - helpers must return renderables without raising
# ---------------------------------------------------------------------------


def _populated_view(height: int = 40) -> WarRoomView:
    view = WarRoomView(_headless_console(height=height), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(EvidenceExtracted(brief=_evidence_brief()))
    _run_round(bus, turn_number=1, confidence=0.8)
    bus.publish(ConsensusEvaluated(score=0.87, round_number=2))
    return view


def test_render_helpers_do_not_raise():
    """
    [Unit] views: verifies render helpers do not raise.

    Scenario:
        Given test inputs and fixtures for render helpers do not raise
        When test_render_helpers_do_not_raise executes the target flow
        Then the expected outcome for render helpers do not raise is confirmed.

    Boundaries:
        - Focus: render helpers do not raise
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to render helpers do not raise
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = _populated_view()
    # Each pane renders to a real console without error.
    con = view._console
    for renderable in (
        view._render_header(),
        view._render_evidence(),
        view._render_agents(),
        view._render_process(),
        view._build_layout(),
    ):
        con.print(renderable)
    view._stop_live()


def test_render_agents_compact_mode_short_terminal():
    # Short terminal drops the finding line but must still render.
    """
    [Unit] views: verifies render agents compact mode short terminal.

    Scenario:
        Given test inputs and fixtures for render agents compact mode short terminal
        When test_render_agents_compact_mode_short_terminal executes the target flow
        Then the expected outcome for render agents compact mode short terminal is confirmed.

    Boundaries:
        - Focus: render agents compact mode short terminal
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to render agents compact mode short terminal
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    view = _populated_view(height=20)
    view._console.print(view._render_agents())
    view._stop_live()


# ---------------------------------------------------------------------------
# Final verdict - prototype-style single green frame
# ---------------------------------------------------------------------------


def _full_report(*, with_fix: bool = True) -> RCAReport:
    return RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        root_cause="Use-after-free in CImage::Load dereferences a freed bitmap buffer.",
        faulting_module="ImageScope.exe",
        faulting_function="CImage::Load",
        confidence_score=0.87,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(
            root_cause="UAF",
            confidence=0.87,
            evidence=[
                "Exception 0xC0000005 reading a freed heap block",
                "__fix__:diff:should be filtered out",
            ],
        ),
        consensus_rounds=2,
        mitigation_instructions=["Pin the buffer with shared_ptr.", "Add a regression test."],
        probabilistic_fix="- old\n+ new" if with_fix else None,
        fix_confidence=0.81 if with_fix else None,
    )


def test_build_diagnosis_has_prototype_sections():
    """
    [Unit] views: verifies build diagnosis has prototype sections.

    Scenario:
        Given test inputs and fixtures for build diagnosis has prototype sections
        When test_build_diagnosis_has_prototype_sections executes the target flow
        Then the expected outcome for build diagnosis has prototype sections is confirmed.

    Boundaries:
        - Focus: build diagnosis has prototype sections
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to build diagnosis has prototype sections
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    text = _build_diagnosis(_full_report())
    assert "## Root Cause Analysis (RCA)" in text
    assert "## Faulting Module" in text
    assert "## Recommendation" in text
    # Root-cause sentence and module are present and human-readable.
    assert "Use-after-free in CImage::Load" in text
    assert "ImageScope.exe" in text
    # Confidence narrative and Markdown structure for the verdict frame.
    assert "**Confidence:** HIGH (87%)" in text
    assert "2 debate rounds" in text
    assert "**Conclusion:**" in text  # rendered as Markdown, not flat prose


def test_build_diagnosis_filters_internal_fix_marker():
    """
    [Unit] views: verifies build diagnosis filters internal fix marker.

    Scenario:
        Given test inputs and fixtures for build diagnosis filters internal fix marker
        When test_build_diagnosis_filters_internal_fix_marker executes the target flow
        Then the expected outcome for build diagnosis filters internal fix marker is confirmed.

    Boundaries:
        - Focus: build diagnosis filters internal fix marker
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to build diagnosis filters internal fix marker
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    md = _build_diagnosis(_full_report())
    assert "__fix__" not in md
    assert "Exception 0xC0000005 reading a freed heap block" in md


def test_build_diagnosis_includes_fix_with_confidence():
    """
    [Unit] views: verifies build diagnosis includes fix with confidence.

    Scenario:
        Given test inputs and fixtures for build diagnosis includes fix with confidence
        When test_build_diagnosis_includes_fix_with_confidence executes the target flow
        Then the expected outcome for build diagnosis includes fix with confidence is confirmed.

    Boundaries:
        - Focus: build diagnosis includes fix with confidence
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to build diagnosis includes fix with confidence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    text = _build_diagnosis(_full_report(with_fix=True))
    assert "Probabilistic Fix - confidence 81%" in text
    # Fix is rendered inside a diff code fence so it colours nicely.
    assert "+ new" in text
    assert "```diff" in text


def test_build_diagnosis_default_recommendation_when_none():
    """
    [Unit] views: verifies build diagnosis default recommendation when none.

    Scenario:
        Given test inputs and fixtures for build diagnosis default recommendation when none
        When test_build_diagnosis_default_recommendation_when_none executes the target flow
        Then the expected outcome for build diagnosis default recommendation when none is confirmed.

    Boundaries:
        - Focus: build diagnosis default recommendation when none
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to build diagnosis default recommendation when none
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    report = _full_report(with_fix=False)
    report.mitigation_instructions = []
    text = _build_diagnosis(report)
    assert "## Recommendation" in text
    # Falls back to generic guidance as a numbered Markdown step.
    assert "Review the faulting module" in text
    assert "1. Review the faulting module" in text


def test_build_diagnosis_includes_agent_reasoning():
    # The detailed per-agent reasoning streams by transiently in the war room;
    # the report must reproduce it instead of distilling to a one-liner.
    """
    [Unit] views: verifies build diagnosis includes agent reasoning.

    Scenario:
        Given test inputs and fixtures for build diagnosis includes agent reasoning
        When test_build_diagnosis_includes_agent_reasoning executes the target flow
        Then the expected outcome for build diagnosis includes agent reasoning is confirmed.

    Boundaries:
        - Focus: build diagnosis includes agent reasoning
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to build diagnosis includes agent reasoning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    report = _full_report(with_fix=False)
    report.agent_dialogue = [
        AgentTurn(
            agent="OS Kernel Agent",
            turn_number=1,
            confidence_score=0.95,
            message="Null-pointer write inside a UI message callback.",
        ),
        AgentTurn(
            agent="Skeptic Agent",
            turn_number=1,
            confidence_score=0.60,
            message="Outdated first take that should be superseded.",
        ),
        AgentTurn(
            agent="Skeptic Agent",
            turn_number=2,
            confidence_score=0.90,
            message="Confirmed: deliberate crash injection in the test handler.",
        ),
    ]
    text = _build_diagnosis(report)
    assert "### Panel Findings" in text
    assert "**OS Kernel Agent** - 95% confident" in text
    assert "Null-pointer write inside a UI message callback." in text
    # Only the agent's final turn is kept; the superseded first take is dropped.
    assert "Confirmed: deliberate crash injection" in text
    assert "Outdated first take" not in text


def test_build_diagnosis_surfaces_alternatives_and_challenges():
    """
    [Unit] views: verifies build diagnosis surfaces alternatives and challenges.

    Scenario:
        Given test inputs and fixtures for build diagnosis surfaces alternatives and challenges
        When test_build_diagnosis_surfaces_alternatives_and_challenges executes the target flow
        Then the expected outcome for build diagnosis surfaces alternatives and challenges is confirmed.

    Boundaries:
        - Focus: build diagnosis surfaces alternatives and challenges
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to build diagnosis surfaces alternatives and challenges
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    report = _full_report(with_fix=False)
    report.alternative_hypotheses = [Hypothesis(root_cause="Heap corruption", confidence=0.2)]
    report.skeptic_challenges = ["No recurrence evidence in the available history."]
    text = _build_diagnosis(report)
    assert "### Alternative Hypotheses" in text
    assert "Heap corruption (20%)" in text
    assert "### Skeptic Challenges" in text
    assert "No recurrence evidence" in text


def test_render_verdict_emits_single_green_frame():
    """
    [Unit] views: verifies render verdict emits single green frame.

    Scenario:
        Given test inputs and fixtures for render verdict emits single green frame
        When test_render_verdict_emits_single_green_frame executes the target flow
        Then the expected outcome for render verdict emits single green frame is confirmed.

    Boundaries:
        - Focus: render verdict emits single green frame
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to render verdict emits single green frame
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    con = Console(force_terminal=True, width=100, file=io.StringIO())
    with con.capture() as cap:
        render_verdict(_full_report(), console=con, model="claude-opus-4-8")
    out = cap.get()
    assert "Root Cause Analysis Report" in out
    assert "Model: claude-opus-4-8" in out
    assert "Use-after-free in CImage::Load" in out
    assert "Recommendation" in out
    # The short incident-id JSON record is stamped inside the same frame.
    assert "Incident Record" in out
    assert "incident_id" in out


def test_render_verdict_hitl_shows_red_frame():
    """
    [Unit] views: verifies render verdict hitl shows red frame.

    Scenario:
        Given test inputs and fixtures for render verdict hitl shows red frame
        When test_render_verdict_hitl_shows_red_frame executes the target flow
        Then the expected outcome for render verdict hitl shows red frame is confirmed.

    Boundaries:
        - Focus: render verdict hitl shows red frame
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to render verdict hitl shows red frame
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by views
    """
    from aegis_swr.core.schemas import HITLRequest

    report = _full_report()
    report.hitl_request = HITLRequest(
        question="What is the DB pool size?",
        context_summary="The panel deadlocked.",
        requested_data=["pool size", "recent deploys"],
    )
    con = Console(force_terminal=True, width=100, file=io.StringIO())
    with con.capture() as cap:
        render_verdict(report, console=con, model="claude-opus-4-8")
    out = cap.get()
    assert "Human Input Required" in out
    assert "What is the DB pool size?" in out
    # The green diagnosis frame is NOT shown for a deadlock.
    assert "AI Root Cause Analysis" not in out
