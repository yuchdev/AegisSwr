"""Unit tests for metadata-based incident similarity and recurrence scoring."""
from __future__ import annotations

from aegis_swr.core.incident_similarity import (
    IncidentSignature,
    analyze_history,
    signature_from_brief,
    signature_from_report,
    similarity,
)
from aegis_swr.core.schemas import ConfidenceLevel, Hypothesis, IncidentMode, RCAReport


def _crashui_brief() -> dict:
    return {
        "fault_class": "access_violation",
        "exception_code_raw": "0xC0000005",
        "faulting_module": "CrashUi.exe",
        "faulting_function": "CrashUi!Crash_Window::on_access_violation_click+0x509",
        "stack_frames": [
            {
                "frame_number": 0,
                "module": "CrashUi",
                "function": "Crash_Window::on_access_violation_click",
                "source_file": r"C:\src\CrashUi\CrashUi.cpp",
                "source_line": 121,
                "instruction_address": "0x7ff",
            }
        ],
        "raw_text_excerpt": (
            "NULL_POINTER_WRITE_c0000005_CrashUi.exe!"
            "Crash_Window::on_access_violation_click  AV.Fault=Write"
        ),
    }


def _crashui_report(incident_id_seed: str = "a") -> RCAReport:
    return RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        dump_hash=f"sha256:{incident_id_seed}",
        root_cause=(
            "Intentional null-pointer write in Crash_Window::on_access_violation_click "
            "at CrashUi.cpp:121."
        ),
        faulting_module="CrashUi",
        faulting_function="Crash_Window::on_access_violation_click",
        confidence_score=0.95,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(
            root_cause="null write",
            faulting_module="CrashUi",
            faulting_function="Crash_Window::on_access_violation_click",
            evidence=[
                "Failure bucket NULL_POINTER_WRITE_c0000005_CrashUi.exe!"
                "Crash_Window::on_access_violation_click.",
                "Faulting source CrashUi.cpp:121.",
            ],
            confidence=0.95,
        ),
        consensus_rounds=1,
    )


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_signature_from_brief_extracts_normalised_fields():
    """
    [Unit] incident similarity: verifies signature from brief extracts normalised fields.

    Scenario:
        Given test inputs and fixtures for signature from brief extracts normalised fields
        When test_signature_from_brief_extracts_normalised_fields executes the target flow
        Then the expected outcome for signature from brief extracts normalised fields is confirmed.

    Boundaries:
        - Focus: signature from brief extracts normalised fields
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to signature from brief extracts normalised fields
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    sig = signature_from_brief(_crashui_brief())
    assert sig.exception_code == "c0000005"
    assert sig.faulting_module == "crashui"  # .exe stripped, lowercased
    assert sig.faulting_function == "crash_window::on_access_violation_click"  # prefix/offset stripped
    assert sig.code_location == "crashui.cpp:121"
    assert sig.failure_bucket == "null_pointer_write_c0000005_crashui"


def test_signature_from_report_mines_evidence_text():
    """
    [Unit] incident similarity: verifies signature from report mines evidence text.

    Scenario:
        Given test inputs and fixtures for signature from report mines evidence text
        When test_signature_from_report_mines_evidence_text executes the target flow
        Then the expected outcome for signature from report mines evidence text is confirmed.

    Boundaries:
        - Focus: signature from report mines evidence text
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to signature from report mines evidence text
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    sig = signature_from_report(_crashui_report())
    assert sig.faulting_module == "crashui"
    assert sig.faulting_function == "crash_window::on_access_violation_click"
    assert sig.code_location == "crashui.cpp:121"
    assert sig.exception_code == "c0000005"
    assert sig.failure_bucket == "null_pointer_write_c0000005_crashui"


def test_exception_code_does_not_match_inside_address():
    # A 16-hex address must not be mistaken for an 8-hex exception code.
    """
    [Unit] incident similarity: verifies exception code does not match inside address.

    Scenario:
        Given test inputs and fixtures for exception code does not match inside address
        When test_exception_code_does_not_match_inside_address executes the target flow
        Then the expected outcome for exception code does not match inside address is confirmed.

    Boundaries:
        - Focus: exception code does not match inside address
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to exception code does not match inside address
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    sig = signature_from_report(
        RCAReport(
            mode=IncidentMode.CRASH_DUMP,
            root_cause="Crash at instruction 0x00007ff72a739234 with no code.",
            confidence_score=0.5,
            confidence_level=ConfidenceLevel.MEDIUM,
            primary_hypothesis=Hypothesis(root_cause="x", confidence=0.5),
            consensus_rounds=1,
        )
    )
    assert sig.exception_code is None


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------


def test_similarity_identical_signatures_is_one():
    """
    [Unit] incident similarity: verifies similarity identical signatures is one.

    Scenario:
        Given test inputs and fixtures for similarity identical signatures is one
        When test_similarity_identical_signatures_is_one executes the target flow
        Then the expected outcome for similarity identical signatures is one is confirmed.

    Boundaries:
        - Focus: similarity identical signatures is one
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to similarity identical signatures is one
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    sig = signature_from_brief(_crashui_brief())
    assert similarity(sig, sig) == 1.0


def test_similarity_only_compares_shared_fields():
    """
    [Unit] incident similarity: verifies similarity only compares shared fields.

    Scenario:
        Given test inputs and fixtures for similarity only compares shared fields
        When test_similarity_only_compares_shared_fields executes the target flow
        Then the expected outcome for similarity only compares shared fields is confirmed.

    Boundaries:
        - Focus: similarity only compares shared fields
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to similarity only compares shared fields
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    a = IncidentSignature(faulting_function="foo", code_location="x.cpp:1")
    b = IncidentSignature(faulting_function="foo")  # no code_location
    # Only faulting_function is comparable, and it matches → perfect score.
    assert similarity(a, b) == 1.0


def test_similarity_capped_when_only_weak_fields_match():
    # Module + exception code match, but no symbol / location / bucket.
    """
    [Unit] incident similarity: verifies similarity capped when only weak fields match.

    Scenario:
        Given test inputs and fixtures for similarity capped when only weak fields match
        When test_similarity_capped_when_only_weak_fields_match executes the target flow
        Then the expected outcome for similarity capped when only weak fields match is confirmed.

    Boundaries:
        - Focus: similarity capped when only weak fields match
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to similarity capped when only weak fields match
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    a = IncidentSignature(faulting_module="crashui", exception_code="c0000005")
    b = IncidentSignature(faulting_module="crashui", exception_code="c0000005")
    assert similarity(a, b) <= 0.40


def test_similarity_distinct_incidents_is_low():
    """
    [Unit] incident similarity: verifies similarity distinct incidents is low.

    Scenario:
        Given test inputs and fixtures for similarity distinct incidents is low
        When test_similarity_distinct_incidents_is_low executes the target flow
        Then the expected outcome for similarity distinct incidents is low is confirmed.

    Boundaries:
        - Focus: similarity distinct incidents is low
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to similarity distinct incidents is low
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    a = signature_from_brief(_crashui_brief())
    b = signature_from_report(
        RCAReport(
            mode=IncidentMode.CRASH_DUMP,
            root_cause="Divide-by-zero in render_engine::draw at gfx.cpp:9 (0xc0000094).",
            faulting_module="render_engine",
            faulting_function="render_engine::draw",
            confidence_score=0.8,
            confidence_level=ConfidenceLevel.HIGH,
            primary_hypothesis=Hypothesis(root_cause="div0", confidence=0.8),
            consensus_rounds=1,
        )
    )
    assert similarity(a, b) < 0.4


# ---------------------------------------------------------------------------
# History analysis
# ---------------------------------------------------------------------------


def test_analyze_history_flags_recurrence_across_sessions():
    """
    [Unit] incident similarity: verifies analyze history flags recurrence across sessions.

    Scenario:
        Given test inputs and fixtures for analyze history flags recurrence across sessions
        When test_analyze_history_flags_recurrence_across_sessions executes the target flow
        Then the expected outcome for analyze history flags recurrence across sessions is confirmed.

    Boundaries:
        - Focus: analyze history flags recurrence across sessions
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to analyze history flags recurrence across sessions
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    history = [_crashui_report("1"), _crashui_report("2"), _crashui_report("3")]
    result = analyze_history(_crashui_brief(), history)
    assert result.is_recurrence
    assert result.recurrence_count == 3
    assert result.recurrence_probability > 0.9
    assert result.suggested_confidence_adjustment > 0
    assert "recurrence" in result.summary().lower()


def test_analyze_history_no_match_is_first_observation():
    """
    [Unit] incident similarity: verifies analyze history no match is first observation.

    Scenario:
        Given test inputs and fixtures for analyze history no match is first observation
        When test_analyze_history_no_match_is_first_observation executes the target flow
        Then the expected outcome for analyze history no match is first observation is confirmed.

    Boundaries:
        - Focus: analyze history no match is first observation
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to analyze history no match is first observation
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    unrelated = RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        root_cause="Stack overflow in parser::descend at parser.cpp:88.",
        faulting_module="parser",
        faulting_function="parser::descend",
        confidence_score=0.7,
        confidence_level=ConfidenceLevel.MEDIUM,
        primary_hypothesis=Hypothesis(root_cause="recursion", confidence=0.7),
        consensus_rounds=1,
    )
    result = analyze_history(_crashui_brief(), [unrelated])
    assert not result.is_recurrence
    assert result.recurrence_count == 0
    assert result.suggested_confidence_adjustment == -0.05  # mild caution, novel signature
    assert "first-observed" in result.summary()


def test_analyze_history_empty_history():
    """
    [Unit] incident similarity: verifies analyze history empty history.

    Scenario:
        Given test inputs and fixtures for analyze history empty history
        When test_analyze_history_empty_history executes the target flow
        Then the expected outcome for analyze history empty history is confirmed.

    Boundaries:
        - Focus: analyze history empty history
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to analyze history empty history
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    result = analyze_history(_crashui_brief(), [])
    assert result.history_size == 0
    assert result.recurrence_probability == 0.0
    assert result.suggested_confidence_adjustment == 0.0
    assert "No historical reports" in result.summary()


def test_analyze_history_excludes_current_incident():
    """
    [Unit] incident similarity: verifies analyze history excludes current incident.

    Scenario:
        Given test inputs and fixtures for analyze history excludes current incident
        When test_analyze_history_excludes_current_incident executes the target flow
        Then the expected outcome for analyze history excludes current incident is confirmed.

    Boundaries:
        - Focus: analyze history excludes current incident
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to analyze history excludes current incident
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by incident similarity
    """
    report = _crashui_report("self")
    result = analyze_history(
        _crashui_brief(), [report], exclude_incident_id=str(report.incident_id)
    )
    assert result.history_size == 0
    assert result.recurrence_count == 0
