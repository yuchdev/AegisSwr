"""Integration tests spanning Steps 1–3.

Exercises the real contract that Phase 5 will rely on: a raw IncidentSource is
preprocessed by the Data Adapter into an IncidentBrief, the brief is threaded
into an AI backend prompt, and the backend returns a validated structured
object. Covered with both the in-process MockAIBackend and the real provider
code path (Anthropic) driven by a mocked SDK client.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from aegis_swr.backends.ai.anthropic_provider import AnthropicBackend
from aegis_swr.config.settings import AnthropicSettings, Settings
from aegis_swr.core.data_adapter import DataAdapter
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    IncidentBrief,
    IncidentMode,
    IncidentSource,
    OSKernelOutput,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend
from tests.unit.fixtures.mock_debug_backend import MockDebugBackend, default_extraction

FIXTURES = Path(__file__).parent.parent / "unit" / "fixtures"


def _os_kernel_payload() -> dict[str, Any]:
    return {
        "exception_summary": {
            "fault_class": "memory_access_violation",
            "exception_code_raw": "0xc0000005",
            "exception_address": "0x00007ff8016a1c3f",
            "faulting_module": "db_writer",
            "faulting_function": "db_writer::serialize",
            "interpretation": "Access violation dereferencing a freed pointer.",
        },
        "hypotheses": [
            {
                "root_cause": "use-after-free in serialize()",
                "faulting_module": "db_writer",
                "confidence": 0.82,
                "evidence": ["frame 0 is db_writer::serialize"],
            }
        ],
        "confidence_score": 0.82,
    }


def _brief_to_messages(brief: IncidentBrief) -> list[dict[str, Any]]:
    """Minimal stand-in for the Phase 5 agent prompt assembly"""
    payload = {
        "fault_class": brief.fault_class.value if brief.fault_class else None,
        "faulting_module": brief.faulting_module,
        "stack_frames": brief.stack_frames,
        "log_summary": brief.log_summary,
    }
    return [{"role": "user", "content": json.dumps(payload)}]


# ---------------------------------------------------------------------------
# Data Adapter -> MockAIBackend
# ---------------------------------------------------------------------------


async def test_adapter_to_mock_backend_structured(settings: Settings, tmp_path: Path):
    """
    [Integration] ai pipeline: verifies adapter to mock backend structured.

    Scenario:
        Given test inputs and fixtures for adapter to mock backend structured
        When test_adapter_to_mock_backend_structured executes the target flow
        Then the expected outcome for adapter to mock backend structured is confirmed.

    Boundaries:
        - Focus: adapter to mock backend structured
        - Fixtures/params: settings, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to adapter to mock backend structured
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai pipeline
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        dump_path=str(dump),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    adapter = DataAdapter(settings)
    brief = await adapter.process(source, debug_backend=MockDebugBackend(default_extraction()))

    backend = MockAIBackend(responses=[_os_kernel_payload()])
    result = await backend.generate(
        "You are the OS Kernel Agent.", _brief_to_messages(brief), OSKernelOutput
    )

    assert isinstance(result, OSKernelOutput)
    assert result.exception_summary.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.confidence_score == 0.82
    # The brief that reached the model carried the adapter's extracted fields...
    sent = json.loads(backend.calls[0]["messages"][0]["content"])
    assert sent["faulting_module"] == "db_writer"
    # ...and was PII-scrubbed (Phase 2 contract) before leaving the adapter.
    assert "alice@example.com" not in (brief.log_summary or "")


async def test_adapter_to_mock_backend_stream(settings: Settings):
    """
    [Integration] ai pipeline: verifies adapter to mock backend stream.

    Scenario:
        Given test inputs and fixtures for adapter to mock backend stream
        When test_adapter_to_mock_backend_stream executes the target flow
        Then the expected outcome for adapter to mock backend stream is confirmed.

    Boundaries:
        - Focus: adapter to mock backend stream
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to adapter to mock backend stream
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai pipeline
    """
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    adapter = DataAdapter(settings)
    brief = await adapter.process(source)

    backend = MockAIBackend(stream_tokens=["The ", "root ", "cause ", "is..."])
    tokens = [t async for t in backend.stream("system", _brief_to_messages(brief))]
    assert "".join(tokens) == "The root cause is..."


# ---------------------------------------------------------------------------
# Data Adapter -> real AnthropicBackend (mocked SDK)
# ---------------------------------------------------------------------------


async def test_adapter_to_anthropic_backend_structured(
    settings: Settings, tmp_path: Path
):
    """
    [Integration] ai pipeline: verifies adapter to anthropic backend structured.

    Scenario:
        Given test inputs and fixtures for adapter to anthropic backend structured
        When test_adapter_to_anthropic_backend_structured executes the target flow
        Then the expected outcome for adapter to anthropic backend structured is confirmed.

    Boundaries:
        - Focus: adapter to anthropic backend structured
        - Fixtures/params: settings, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to adapter to anthropic backend structured
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai pipeline
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path=str(dump),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    adapter = DataAdapter(settings)
    brief = await adapter.process(source, debug_backend=MockDebugBackend(default_extraction()))

    with mock.patch("anthropic.AsyncAnthropic") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = AnthropicBackend(AnthropicSettings(model="claude-sonnet-4-6"))
    client.messages.create = mock.AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input=_os_kernel_payload())],
            usage=SimpleNamespace(input_tokens=1200, output_tokens=150),
        )
    )

    result = await backend.generate(
        "You are the OS Kernel Agent.", _brief_to_messages(brief), OSKernelOutput
    )

    assert isinstance(result, OSKernelOutput)
    assert result.hypotheses[0].root_cause.startswith("use-after-free")
    assert backend.last_usage == {"input_tokens": 1200, "output_tokens": 150}
    # The structured tool was actually requested from the provider.
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"]["name"] == "structured_output"


async def test_adapter_low_symbol_coverage_flows_to_brief(
    settings: Settings, tmp_path: Path
):
    """
    [Integration] ai pipeline: verifies adapter low symbol coverage flows to brief.

    Scenario:
        Given test inputs and fixtures for adapter low symbol coverage flows to brief
        When test_adapter_low_symbol_coverage_flows_to_brief executes the target flow
        Then the expected outcome for adapter low symbol coverage flows to brief is confirmed.

    Boundaries:
        - Focus: adapter low symbol coverage flows to brief
        - Fixtures/params: settings, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to adapter low symbol coverage flows to brief
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai pipeline
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 16)
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=str(dump))
    adapter = DataAdapter(settings)
    brief = await adapter.process(
        source, debug_backend=MockDebugBackend(default_extraction(symbol_score=0.20))
    )
    assert brief.low_symbol_coverage_warning == "[LOW SYMBOL COVERAGE: 20%]"


def test_pytest_can_import_shared_fixtures():
    # Guards the test-package import path used across unit + integration suites.
    """
    [Integration] ai pipeline: verifies pytest can import shared fixtures.

    Scenario:
        Given test inputs and fixtures for pytest can import shared fixtures
        When test_pytest_can_import_shared_fixtures executes the target flow
        Then the expected outcome for pytest can import shared fixtures is confirmed.

    Boundaries:
        - Focus: pytest can import shared fixtures
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pytest can import shared fixtures
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai pipeline
    """
    assert MockAIBackend is not None
    assert MockDebugBackend is not None
