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
    backend, _ = _make_backend(
        monkeypatch,
        converse_side_effect=botocore.exceptions.ReadTimeoutError(endpoint_url="https://x"),
    )
    with pytest.raises(AIBackendError, match="ReadTimeoutError"):
        await backend.generate("system", [{"role": "user", "content": "x"}])
