"""Integration tests for the Amazon Bedrock backend.

Exercises the real provider code path - prompt assembly, the Converse request
shape, structured tool-use parsing, streaming, and bearer-token auth wiring -
end to end, with boto3 mocked so no AWS call ever leaves the process.

The Data Adapter preprocesses a raw IncidentSource into an IncidentBrief, the
brief is threaded into a Bedrock prompt, and the mocked Converse response is
parsed back into a validated structured object - the same contract the
orchestrator relies on.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest import mock

import botocore.exceptions
import pytest

from aegis_swr.backends.ai import create_ai_backend
from aegis_swr.backends.ai.aws_bedrock_provider import AwsBedrockBackend
from aegis_swr.config.settings import AISettings, Settings
from aegis_swr.core.exceptions import AIBackendError
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import IncidentMode, IncidentSource, OSKernelOutput
from tests.unit.fixtures.mock_debug_backend import MockDebugBackend, default_extraction

FIXTURES = Path(__file__).parent.parent / "unit" / "fixtures"


def _os_kernel_payload() -> dict[str, Any]:
    """Helper that provides os kernel payload for the bedrock integration tests."""
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


def _brief_to_messages(brief: Any) -> list[dict[str, Any]]:
    """Helper that provides brief to messages for the bedrock integration tests."""
    payload = {
        "fault_class": brief.fault_class.value if brief.fault_class else None,
        "faulting_module": brief.faulting_module,
        "stack_frames": brief.stack_frames,
        "log_summary": brief.log_summary,
    }
    return [{"role": "user", "content": json.dumps(payload)}]


def _make_backend(
    monkeypatch: pytest.MonkeyPatch,
    converse_return: Any = None,
    converse_stream_return: Any = None,
    converse_side_effect: Any = None,
) -> tuple[AwsBedrockBackend, Any]:
    """Helper that provides make backend for the bedrock integration tests."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "integration-token")
    client = mock.MagicMock()
    if converse_side_effect is not None:
        client.converse = mock.MagicMock(side_effect=converse_side_effect)
    else:
        client.converse = mock.MagicMock(return_value=converse_return)
    client.converse_stream = mock.MagicMock(return_value=converse_stream_return)
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = create_ai_backend(AISettings(provider="bedrock"))
    assert isinstance(backend, AwsBedrockBackend)
    return backend, client


# ---------------------------------------------------------------------------
# Data Adapter -> Bedrock backend (mocked Converse)
# ---------------------------------------------------------------------------


async def test_adapter_to_bedrock_backend_structured(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    [Integration] bedrock integration: verifies adapter to bedrock backend structured.

    Scenario:
        Given test inputs and fixtures for adapter to bedrock backend structured
        When test_adapter_to_bedrock_backend_structured executes the target flow
        Then the expected outcome for adapter to bedrock backend structured is confirmed.

    Boundaries:
        - Focus: adapter to bedrock backend structured
        - Fixtures/params: settings, tmp_path, monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to adapter to bedrock backend structured
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by bedrock integration
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    # The Data Adapter requires the optional ``pii`` extra (presidio); skip the
    # adapter-coupled assertions when it is not installed.
    pytest.importorskip("presidio_analyzer")
    from aegis_swr.core.data_adapter import DataAdapter

    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path=str(dump),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    adapter = DataAdapter(settings)
    brief = await adapter.process(
        source, debug_backend=MockDebugBackend(default_extraction())
    )

    converse_return = {
        "output": {
            "message": {
                "content": [
                    {"toolUse": {"name": "structured_output", "input": _os_kernel_payload()}}
                ]
            }
        },
        "usage": {"inputTokens": 1200, "outputTokens": 150},
        "stopReason": "tool_use",
    }
    backend, client = _make_backend(monkeypatch, converse_return=converse_return)

    result = await backend.generate(
        "You are the OS Kernel Agent.", _brief_to_messages(brief), OSKernelOutput
    )

    assert isinstance(result, OSKernelOutput)
    assert result.exception_summary.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.hypotheses[0].root_cause.startswith("use-after-free")
    assert backend.last_usage == {"input_tokens": 1200, "output_tokens": 150}

    # The structured tool was actually requested from Bedrock via Converse.
    kwargs = client.converse.call_args.kwargs
    assert kwargs["toolConfig"]["toolChoice"]["tool"]["name"] == "structured_output"
    # Bearer-token auth hook was wired onto the runtime client.
    client.meta.events.register.assert_called_once()
    # The PII-scrubbed brief is what reached the model.
    assert "alice@example.com" not in (brief.log_summary or "")


async def test_adapter_to_bedrock_backend_stream(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    """
    [Integration] bedrock integration: verifies adapter to bedrock backend stream.

    Scenario:
        Given test inputs and fixtures for adapter to bedrock backend stream
        When test_adapter_to_bedrock_backend_stream executes the target flow
        Then the expected outcome for adapter to bedrock backend stream is confirmed.

    Boundaries:
        - Focus: adapter to bedrock backend stream
        - Fixtures/params: settings, monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to adapter to bedrock backend stream
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by bedrock integration
    """
    pytest.importorskip("presidio_analyzer")
    from aegis_swr.core.data_adapter import DataAdapter

    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11),
        log_paths=[str(FIXTURES / "sample_logs_with_pii.txt")],
    )
    adapter = DataAdapter(settings)
    brief = await adapter.process(source)

    stream_return = {
        "stream": [
            {"contentBlockDelta": {"delta": {"text": "The "}}},
            {"contentBlockDelta": {"delta": {"text": "root "}}},
            {"contentBlockDelta": {"delta": {"text": "cause "}}},
            {"contentBlockDelta": {"delta": {"text": "is..."}}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]
    }
    backend, _ = _make_backend(monkeypatch, converse_stream_return=stream_return)

    tokens = [t async for t in backend.stream("system", _brief_to_messages(brief))]
    assert "".join(tokens) == "The root cause is..."


async def test_bedrock_transport_error_raises_backend_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    [Integration] bedrock integration: verifies bedrock transport error raises backend error.

    Scenario:
        Given test inputs and fixtures for bedrock transport error raises backend error
        When test_bedrock_transport_error_raises_backend_error executes the target flow
        Then the expected outcome for bedrock transport error raises backend error is confirmed.

    Boundaries:
        - Focus: bedrock transport error raises backend error
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock transport error raises backend error
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by bedrock integration
    """
    backend, _ = _make_backend(
        monkeypatch,
        converse_side_effect=botocore.exceptions.ReadTimeoutError(endpoint_url="https://x"),
    )
    with pytest.raises(AIBackendError, match="ReadTimeoutError"):
        await backend.generate("system", [{"role": "user", "content": "x"}])


# ---------------------------------------------------------------------------
# New spec-compliance integration tests
# ---------------------------------------------------------------------------


async def test_bedrock_token_usage_propagates_to_state(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Integration] bedrock integration: After generate() with a response carrying a usage block, backend.last_usage.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: after generate() with a response carrying a usage block, backend.last_usage.
    """
    converse_return = {
        "output": {"message": {"content": [{"text": "root cause identified"}]}},
        "usage": {"inputTokens": 850, "outputTokens": 120},
        "stopReason": "end_turn",
    }
    backend, _ = _make_backend(monkeypatch, converse_return=converse_return)

    result = await backend.generate("system", [{"role": "user", "content": "analyze"}])

    assert result == "root cause identified"
    usage = backend.last_usage
    assert usage["input_tokens"] == 850, f"expected 850 input tokens, got {usage['input_tokens']}"
    assert usage["output_tokens"] == 120, f"expected 120 output tokens, got {usage['output_tokens']}"
    # Combined usage must be non-zero (the feed into InvestigationState.token_tracker).
    assert usage["input_tokens"] + usage["output_tokens"] > 0


async def test_bedrock_structured_retry_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Integration] bedrock integration: First stubbed converse returns an invalid structured payload, second returns a.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: first stubbed converse returns an invalid structured payload, second returns a.
    """
    from aegis_swr.core.schemas import Hypothesis

    # First call: toolUse input missing required `confidence` field.
    first_response = {
        "output": {
            "message": {
                "content": [
                    {"toolUse": {"name": "structured_output", "input": {"root_cause": "uaf"}}}
                ]
            }
        },
        "usage": {"inputTokens": 200, "outputTokens": 50},
        "stopReason": "tool_use",
    }
    # Second call: fully valid Hypothesis.
    second_response = {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "structured_output",
                            "input": {"root_cause": "uaf in serialize()", "confidence": 0.84},
                        }
                    }
                ]
            }
        },
        "usage": {"inputTokens": 400, "outputTokens": 80},
        "stopReason": "tool_use",
    }
    backend, client = _make_backend(
        monkeypatch,
        converse_side_effect=[first_response, second_response],
    )

    result = await backend.generate(
        "You are the OS Kernel Agent.",
        [{"role": "user", "content": "crash at 0xdeadbeef"}],
        Hypothesis,
    )

    assert isinstance(result, Hypothesis)
    assert result.root_cause == "uaf in serialize()"
    assert abs(result.confidence - 0.84) < 1e-6
    # Two calls: initial attempt + one correction retry.
    assert client.converse.call_count == 2
    # Accumulated usage spans both calls.
    assert backend.last_usage["input_tokens"] == 600
    assert backend.last_usage["output_tokens"] == 130


async def test_bedrock_pii_never_reaches_request(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """[Integration] bedrock integration: Drive an IncidentSource carrying PII through the adapter (when presidio is.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: drive an IncidentSource carrying PII through the adapter (when presidio is.
    """
    pytest.importorskip("presidio_analyzer")
    from aegis_swr.core.data_adapter import DataAdapter

    pii_log_path = str(FIXTURES / "sample_logs_with_pii.txt")
    source = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        log_paths=[pii_log_path],
    )
    adapter = DataAdapter(settings)
    brief = await adapter.process(source)

    converse_return = {
        "output": {"message": {"content": [{"text": "analysis done"}]}},
        "usage": {"inputTokens": 100, "outputTokens": 20},
        "stopReason": "end_turn",
    }
    backend, client = _make_backend(monkeypatch, converse_return=converse_return)

    messages = _brief_to_messages(brief)
    await backend.generate("You are the OS Kernel Agent.", messages)

    # Collect all text that was submitted to Converse.
    converse_kwargs = client.converse.call_args.kwargs
    submitted_text = json.dumps(converse_kwargs)

    # Read the known PII strings from the fixture file.
    fixture_text = Path(pii_log_path).read_text(encoding="utf-8")
    # alice@example.com is the canonical PII address in the sample fixture.
    assert "alice@example.com" not in submitted_text, (
        "Raw PII email found in Converse request body"
    )
    # The fixture content itself contains PII to make the assertion meaningful.
    assert "alice@example.com" in fixture_text
