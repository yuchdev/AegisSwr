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
    from aegis_swr.views.rich_view import SPINNER_FRAMES

    seen = {_spinner_char(t / 10) for t in range(len(SPINNER_FRAMES))}
    assert seen == set(SPINNER_FRAMES)


def test_fmt_elapsed_is_h_mm_ss():
    assert _fmt_elapsed(0) == "0:00:00"
    assert _fmt_elapsed(102) == "0:01:42"
    assert _fmt_elapsed(3723) == "1:02:03"


def test_fmt_stamp_is_mm_ss():
    assert _fmt_stamp(0) == "00:00"
    assert _fmt_stamp(108) == "01:48"


def test_truncate_appends_ellipsis():
    assert _truncate("short", 20) == "short"
    assert _truncate("a very long finding line", 10) == "a very lo…"
    assert _truncate("x", 1) == ""


def test_agent_state_defaults():
    state = AgentState()
    assert state.status == "STANDBY"
    assert state.confidence == 0.0
    assert state.finding == ""


# ---------------------------------------------------------------------------
# make_view selection
# ---------------------------------------------------------------------------


def test_make_view_wide_terminal_is_warroom():
    view = make_view(_headless_console(width=120))
    assert isinstance(view, WarRoomView)


def test_make_view_narrow_terminal_is_richview():
    view = make_view(_headless_console(width=70))
    assert isinstance(view, RichView)


# ---------------------------------------------------------------------------
# WarRoomView event flow
# ---------------------------------------------------------------------------


def test_started_resets_state_and_records_stage_marker():
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
    view = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    for _ in range(view._MAX_EVIDENCE + 50):
        view._add_evidence(view._plain("noise"))
    assert len(view._evidence_log.lines) == view._MAX_EVIDENCE
    view._stop_live()


def test_process_log_is_capped():
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
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
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
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
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


def test_debug_surfaces_full_agent_message_in_process():
    multiline = "headline finding\nsupporting detail one\nsupporting detail two"
    # INFO keeps only the headline …
    info = WarRoomView(_headless_console(), auto_refresh=False)
    bus = EventBus()
    info.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus.publish(
        AgentSpoke(
            node="os_kernel_node",
            turn=AgentTurn(
                agent="OS Kernel Agent",
                turn_number=1,
                message=multiline,
                confidence_score=0.8,
            ),
        )
    )
    assert "headline finding" in _process_text(info)
    assert "supporting detail two" not in _process_text(info)
    info._stop_live()

    # … DEBUG surfaces the agent's full reasoning.
    debug = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
    bus2 = EventBus()
    debug.attach(bus2)
    bus2.publish(InvestigationStarted(incident_id="abc", source=_crash_source()))
    bus2.publish(
        AgentSpoke(
            node="os_kernel_node",
            turn=AgentTurn(
                agent="OS Kernel Agent",
                turn_number=1,
                message=multiline,
                confidence_score=0.8,
            ),
        )
    )
    text = _process_text(debug)
    assert "headline finding" in text
    assert "supporting detail one" in text
    assert "supporting detail two" in text
    debug._stop_live()


# ---------------------------------------------------------------------------
# Evidence Stream verbosity: INFO summary vs DEBUG detail
# ---------------------------------------------------------------------------


def _debug_brief() -> dict:
    """An incident brief carrying the fields the DEBUG stream surfaces"""
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


def test_info_level_omits_debug_detail():
    view = WarRoomView(_headless_console(), auto_refresh=False)  # default INFO
    _start(view, _crash_source())
    text = _evidence_text(view)
    # INFO summary fields remain.
    assert "ACCESS_VIOLATION" in text
    assert "stack[0]" in text
    # DEBUG-only detail is absent.
    assert "core dump analysis" not in text
    assert "EXCEPTION_ANALYSIS" not in text
    assert "stack[3]" not in text
    assert "should_not_appear" not in text
    assert all(entry.level == "INFO" for entry in view._evidence_log.lines)
    view._stop_live()


def test_debug_level_shows_core_dump_text_and_full_stack():
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
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
    assert any(entry.level == "DEBUG" for entry in view._evidence_log.lines)
    view._stop_live()


def _long_excerpt_brief(n: int = 50) -> dict:
    """A brief whose core-dump analysis spans *n* lines (> the DEBUG cap)."""
    brief = _debug_brief()
    brief["raw_text_excerpt"] = "\n".join(f"ANALYZE_LINE_{i:02d}" for i in range(n))
    return brief


def _start_with(view: WarRoomView, brief: dict, source: IncidentSource):
    bus = EventBus()
    view.attach(bus)
    bus.publish(InvestigationStarted(incident_id="abc", source=source))
    bus.publish(EvidenceExtracted(brief=brief))


def test_debug_caps_core_dump_excerpt():
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
    _start_with(view, _long_excerpt_brief(50), _crash_source())
    text = _evidence_text(view)
    assert "core dump analysis (cdb !analyze -v):" in text
    assert "ANALYZE_LINE_00" in text
    assert "ANALYZE_LINE_39" in text     # last line within the 40-line cap
    assert "ANALYZE_LINE_40" not in text  # capped at DEBUG
    assert "ANALYZE_LINE_49" not in text
    view._stop_live()


def test_trace_streams_full_core_dump_output():
    view = WarRoomView(_headless_console(), auto_refresh=False, level="TRACE")
    _start_with(view, _long_excerpt_brief(50), _crash_source())
    text = _evidence_text(view)
    # The full !analyze output - beyond the DEBUG cap - is streamed.
    assert "core dump analysis (cdb !analyze -v, full):" in text
    assert "ANALYZE_LINE_40" in text
    assert "ANALYZE_LINE_49" in text
    # Full-output lines are tagged TRACE; DEBUG metadata still surfaces.
    assert any(entry.level == "TRACE" for entry in view._evidence_log.lines)
    assert "sha256:abc123" in text
    view._stop_live()


def test_stream_log_visible_respects_level_rank():
    from aegis_swr.views.rich_view import _StreamLog

    log = _StreamLog(max_lines=100, reveal_interval=0.0)
    log.reset(0.0)
    log.append(Text("info-line"), level="INFO")
    log.append(Text("debug-line"), level="DEBUG")
    log.append(Text("trace-line"), level="TRACE")
    log.reveal_all()

    def shown(level: str) -> list[str]:
        lines = log.visible(now=1.0, finished=True, level=level, max_lines=100)
        return [_plain(r) for r in lines]

    assert shown("INFO") == ["info-line"]
    assert shown("DEBUG") == ["info-line", "debug-line"]
    assert shown("TRACE") == ["info-line", "debug-line", "trace-line"]


def test_make_view_accepts_trace_level():
    view = make_view(_headless_console(width=120), level="TRACE")
    assert view._level == "TRACE"


def test_debug_level_shows_log_window(tmp_path: Path):
    log = tmp_path / "app.log"
    log.write_text("2026-06-04T14:02:11 ERROR boom\n")
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        log_paths=[str(log)],
        incident_timestamp=datetime(2026, 6, 4, 14, 2, 11),
    )
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
    _start(view, source)
    text = _evidence_text(view)
    # Category 2: ±2 minute window for the analyzed log file.
    assert "app.log" in text
    assert "14:00:11" in text
    assert "14:04:11" in text
    assert "±2m" in text
    view._stop_live()


def test_debug_level_shows_screenshot_properties(tmp_path: Path):
    shot = tmp_path / "error.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        screenshot_paths=[str(shot)],
    )
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
    _start(view, source)
    text = _evidence_text(view)
    # Category 3: screenshot name + properties + OCR summary.
    assert "screenshot" in text
    assert "error.png" in text
    assert "48 B" in text
    assert "OCR" in text
    view._stop_live()


def test_debug_level_shows_network_capture_metadata(tmp_path: Path):
    cap = _write_pcap(tmp_path / "traffic.pcap")
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path="C:/dumps/CrashUi.dmp",
        network_capture_paths=[str(cap)],
    )
    view = WarRoomView(_headless_console(), auto_refresh=False, level="DEBUG")
    _start(view, source)
    text = _evidence_text(view)
    # Category 4: network traffic capture metadata.
    assert "netcap" in text
    assert "traffic.pcap" in text
    assert "pcap v2.4" in text
    assert "ETHERNET" in text
    assert "packets 1" in text
    view._stop_live()


def test_make_view_debug_level_sets_verbosity():
    view = make_view(_headless_console(width=120), level="DEBUG")
    assert isinstance(view, WarRoomView)
    assert view._level == "DEBUG"


def test_make_view_default_level_is_info():
    view = make_view(_headless_console(width=120))
    assert isinstance(view, WarRoomView)
    assert view._level == "INFO"


def test_debug_evidence_render_does_not_raise(tmp_path: Path):
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
    view = WarRoomView(_headless_console(height=50), auto_refresh=False, level="DEBUG")
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
    md = _build_diagnosis(_full_report())
    assert "__fix__" not in md
    assert "Exception 0xC0000005 reading a freed heap block" in md


def test_build_diagnosis_includes_fix_with_confidence():
    text = _build_diagnosis(_full_report(with_fix=True))
    assert "Probabilistic Fix - confidence 81%" in text
    # Fix is rendered inside a diff code fence so it colours nicely.
    assert "+ new" in text
    assert "```diff" in text


def test_build_diagnosis_default_recommendation_when_none():
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
    report = _full_report(with_fix=False)
    report.alternative_hypotheses = [Hypothesis(root_cause="Heap corruption", confidence=0.2)]
    report.skeptic_challenges = ["No recurrence evidence in the available history."]
    text = _build_diagnosis(report)
    assert "### Alternative Hypotheses" in text
    assert "Heap corruption (20%)" in text
    assert "### Skeptic Challenges" in text
    assert "No recurrence evidence" in text


def test_render_verdict_emits_single_green_frame():
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
