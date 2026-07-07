"""Unit tests for the Anthropic and OpenAI backends using mocked SDK clients.

No network access: the SDK client classes are patched so __init__ never needs a
real API key and every response is fabricated.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from aegis_swr.backends.ai import create_ai_backend
from aegis_swr.backends.ai.anthropic_provider import AnthropicBackend
from aegis_swr.backends.ai.aws_bedrock_provider import AwsBedrockBackend
from aegis_swr.backends.ai.openai_provider import OpenAIBackend, _to_openai_strict_schema
from aegis_swr.config.settings import (
    AISettings,
    AnthropicSettings,
    BedrockSettings,
    OpenAISettings,
)
from aegis_swr.core.exceptions import AIBackendError, AIOutputValidationError
from aegis_swr.core.schemas import Hypothesis

# ---------------------------------------------------------------------------
# Fake SDK response builders
# ---------------------------------------------------------------------------


def _anthropic_response(blocks: list[Any], inp: int = 10, out: int = 5) -> SimpleNamespace:
    return SimpleNamespace(
        content=blocks, usage=SimpleNamespace(input_tokens=inp, output_tokens=out)
    )


def _tool_block(data: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", input=data)


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _openai_response(content: str, ptok: int = 10, ctok: int = 5) -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(
        choices=[choice], usage=SimpleNamespace(prompt_tokens=ptok, completion_tokens=ctok)
    )


class _FakeStreamCtx:
    """Async context manager mimicking anthropic ``messages.stream(...)``"""

    def __init__(self, tokens: list[str]):
        self._tokens = tokens

    async def __aenter__(self) -> _FakeStreamCtx:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    @property
    def text_stream(self) -> Any:
        async def _gen() -> Any:
            for token in self._tokens:
                yield token

        return _gen()


async def _openai_chunks(tokens: list[str]) -> Any:
    for token in tokens:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=token))])
    yield SimpleNamespace(choices=[])  # final usage chunk has no choices


def _bedrock_tool_response(
    data: dict[str, Any], inp: int = 10, out: int = 5
) -> dict[str, Any]:
    return {
        "output": {"message": {"content": [{"toolUse": {"name": "structured_output", "input": data}}]}},
        "usage": {"inputTokens": inp, "outputTokens": out},
        "stopReason": "tool_use",
    }


def _bedrock_text_response(text: str, inp: int = 10, out: int = 5) -> dict[str, Any]:
    return {
        "output": {"message": {"content": [{"text": text}]}},
        "usage": {"inputTokens": inp, "outputTokens": out},
        "stopReason": "end_turn",
    }


def _bedrock_stream_response(tokens: list[str]) -> dict[str, Any]:
    # converse_stream returns {"stream": <EventStream>}; a list is an iterable
    # stand-in. A trailing non-text event exercises the text-only filter.
    events: list[dict[str, Any]] = [
        {"contentBlockDelta": {"delta": {"text": t}}} for t in tokens
    ]
    events.append({"messageStop": {"stopReason": "end_turn"}})
    return {"stream": events}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anthropic_backend() -> tuple[AnthropicBackend, Any]:
    settings = AnthropicSettings(model="claude-sonnet-4-6")
    with mock.patch("anthropic.AsyncAnthropic") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = AnthropicBackend(settings)
    return backend, client


@pytest.fixture
def openai_backend() -> tuple[OpenAIBackend, Any]:
    settings = OpenAISettings(model="gpt-5.4")
    with mock.patch("openai.AsyncOpenAI") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = OpenAIBackend(settings)
    return backend, client


@pytest.fixture
def bedrock_backend(monkeypatch: pytest.MonkeyPatch) -> tuple[AwsBedrockBackend, Any]:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-bearer-token")
    settings = BedrockSettings()
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)
    return backend, client


_USER = [{"role": "user", "content": "analyze this"}]


# ---------------------------------------------------------------------------
# Anthropic - structured output
# ---------------------------------------------------------------------------


async def test_anthropic_structured_output_valid(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic structured output valid.

    Scenario:
        Given test inputs and fixtures for anthropic structured output valid
        When test_anthropic_structured_output_valid executes the target flow
        Then the expected outcome for anthropic structured output valid is confirmed.

    Boundaries:
        - Focus: anthropic structured output valid
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic structured output valid
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_tool_block({"root_cause": "uaf", "confidence": 0.8})])
    )
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert result.confidence == 0.8
    assert backend.last_usage == {"input_tokens": 10, "output_tokens": 5}


async def test_anthropic_sends_cache_control_and_tool(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic sends cache control and tool.

    Scenario:
        Given test inputs and fixtures for anthropic sends cache control and tool
        When test_anthropic_sends_cache_control_and_tool executes the target flow
        Then the expected outcome for anthropic sends cache control and tool is confirmed.

    Boundaries:
        - Focus: anthropic sends cache control and tool
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic sends cache control and tool
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_tool_block({"root_cause": "x", "confidence": 0.5})])
    )
    await backend.generate("system", _USER, Hypothesis)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tool_choice"]["name"] == "structured_output"
    assert kwargs["tools"][0]["input_schema"]["title"] == "Hypothesis"


async def test_anthropic_retry_then_valid(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic retry then valid.

    Scenario:
        Given test inputs and fixtures for anthropic retry then valid
        When test_anthropic_retry_then_valid executes the target flow
        Then the expected outcome for anthropic retry then valid is confirmed.

    Boundaries:
        - Focus: anthropic retry then valid
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic retry then valid
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        side_effect=[
            _anthropic_response([_tool_block({"root_cause": "x"})]),  # missing confidence
            _anthropic_response([_tool_block({"root_cause": "x", "confidence": 0.7})]),
        ]
    )
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert client.messages.create.call_count == 2
    # usage accumulates across the retry
    assert backend.last_usage == {"input_tokens": 20, "output_tokens": 10}


async def test_anthropic_raises_after_retry(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic raises after retry.

    Scenario:
        Given test inputs and fixtures for anthropic raises after retry
        When test_anthropic_raises_after_retry executes the target flow
        Then the expected outcome for anthropic raises after retry is confirmed.

    Boundaries:
        - Focus: anthropic raises after retry
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic raises after retry
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_tool_block({"root_cause": "x"})])  # always invalid
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)
    assert client.messages.create.call_count == 2


async def test_anthropic_unstructured_returns_text(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic unstructured returns text.

    Scenario:
        Given test inputs and fixtures for anthropic unstructured returns text
        When test_anthropic_unstructured_returns_text executes the target flow
        Then the expected outcome for anthropic unstructured returns text is confirmed.

    Boundaries:
        - Focus: anthropic unstructured returns text
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic unstructured returns text
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_text_block("hello "), _text_block("world")])
    )
    result = await backend.generate("system", _USER)
    assert result == "hello world"


async def test_anthropic_stream_yields_tokens(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic stream yields tokens.

    Scenario:
        Given test inputs and fixtures for anthropic stream yields tokens
        When test_anthropic_stream_yields_tokens executes the target flow
        Then the expected outcome for anthropic stream yields tokens is confirmed.

    Boundaries:
        - Focus: anthropic stream yields tokens
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic stream yields tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.stream = mock.MagicMock(return_value=_FakeStreamCtx(["a", "b", "c"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_anthropic_raises_when_no_tool_block(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """
    [Mock] ai backends: verifies anthropic raises when no tool block.

    Scenario:
        Given test inputs and fixtures for anthropic raises when no tool block
        When test_anthropic_raises_when_no_tool_block executes the target flow
        Then the expected outcome for anthropic raises when no tool block is confirmed.

    Boundaries:
        - Focus: anthropic raises when no tool block
        - Fixtures/params: anthropic_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic raises when no tool block
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_text_block("no tool here")])
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)


# ---------------------------------------------------------------------------
# OpenAI - structured output
# ---------------------------------------------------------------------------


async def test_openai_structured_output_valid(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """
    [Mock] ai backends: verifies openai structured output valid.

    Scenario:
        Given test inputs and fixtures for openai structured output valid
        When test_openai_structured_output_valid executes the target flow
        Then the expected outcome for openai structured output valid is confirmed.

    Boundaries:
        - Focus: openai structured output valid
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai structured output valid
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response(json.dumps({"root_cause": "race", "confidence": 0.9}))
    )
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert result.confidence == 0.9
    assert backend.last_usage == {"input_tokens": 10, "output_tokens": 5}


async def test_openai_sends_json_schema_strict(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """
    [Mock] ai backends: verifies openai sends json schema strict.

    Scenario:
        Given test inputs and fixtures for openai sends json schema strict
        When test_openai_sends_json_schema_strict executes the target flow
        Then the expected outcome for openai sends json schema strict is confirmed.

    Boundaries:
        - Focus: openai sends json schema strict
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai sends json schema strict
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response(json.dumps({"root_cause": "x", "confidence": 0.5}))
    )
    await backend.generate("system", _USER, Hypothesis)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    # System prompt is injected as the first message for OpenAI.
    assert kwargs["messages"][0]["role"] == "system"


async def test_openai_reasoning_model_uses_max_completion_tokens(
    openai_backend: tuple[OpenAIBackend, Any],
):
    # gpt-5.4 is a reasoning model: must use max_completion_tokens and omit
    # temperature (only the default temperature is accepted).
    """
    [Mock] ai backends: verifies openai reasoning model uses max completion tokens.

    Scenario:
        Given test inputs and fixtures for openai reasoning model uses max completion tokens
        When test_openai_reasoning_model_uses_max_completion_tokens executes the target flow
        Then the expected outcome for openai reasoning model uses max completion tokens is confirmed.

    Boundaries:
        - Focus: openai reasoning model uses max completion tokens
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai reasoning model uses max completion tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response(json.dumps({"root_cause": "x", "confidence": 0.5}))
    )
    await backend.generate("system", _USER, Hypothesis)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "max_completion_tokens" in kwargs
    assert kwargs["max_completion_tokens"] >= 16000
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs


async def test_openai_non_reasoning_model_uses_max_tokens():
    """
    [Mock] ai backends: verifies openai non reasoning model uses max tokens.

    Scenario:
        Given test inputs and fixtures for openai non reasoning model uses max tokens
        When test_openai_non_reasoning_model_uses_max_tokens executes the target flow
        Then the expected outcome for openai non reasoning model uses max tokens is confirmed.

    Boundaries:
        - Focus: openai non reasoning model uses max tokens
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai non reasoning model uses max tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    settings = OpenAISettings(model="gpt-4o", temperature=0.2, max_tokens=4096)
    with mock.patch("openai.AsyncOpenAI") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = OpenAIBackend(settings)
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response(json.dumps({"root_cause": "x", "confidence": 0.5}))
    )
    await backend.generate("system", _USER, Hypothesis)
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 4096
    assert kwargs["temperature"] == 0.2
    assert "max_completion_tokens" not in kwargs


async def test_openai_retry_then_valid(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """
    [Mock] ai backends: verifies openai retry then valid.

    Scenario:
        Given test inputs and fixtures for openai retry then valid
        When test_openai_retry_then_valid executes the target flow
        Then the expected outcome for openai retry then valid is confirmed.

    Boundaries:
        - Focus: openai retry then valid
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai retry then valid
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        side_effect=[
            _openai_response(json.dumps({"root_cause": "x"})),  # missing confidence
            _openai_response(json.dumps({"root_cause": "x", "confidence": 0.6})),
        ]
    )
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert client.chat.completions.create.call_count == 2


async def test_openai_raises_on_malformed_json(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """
    [Mock] ai backends: verifies openai raises on malformed json.

    Scenario:
        Given test inputs and fixtures for openai raises on malformed json
        When test_openai_raises_on_malformed_json executes the target flow
        Then the expected outcome for openai raises on malformed json is confirmed.

    Boundaries:
        - Focus: openai raises on malformed json
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai raises on malformed json
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response("not json at all")
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)
    assert client.chat.completions.create.call_count == 2


async def test_openai_unstructured_returns_text(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """
    [Mock] ai backends: verifies openai unstructured returns text.

    Scenario:
        Given test inputs and fixtures for openai unstructured returns text
        When test_openai_unstructured_returns_text executes the target flow
        Then the expected outcome for openai unstructured returns text is confirmed.

    Boundaries:
        - Focus: openai unstructured returns text
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai unstructured returns text
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response("plain answer")
    )
    result = await backend.generate("system", _USER)
    assert result == "plain answer"


async def test_openai_stream_yields_tokens(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """
    [Mock] ai backends: verifies openai stream yields tokens.

    Scenario:
        Given test inputs and fixtures for openai stream yields tokens
        When test_openai_stream_yields_tokens executes the target flow
        Then the expected outcome for openai stream yields tokens is confirmed.

    Boundaries:
        - Focus: openai stream yields tokens
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai stream yields tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(return_value=_openai_chunks(["x", "y"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["x", "y"]


# ---------------------------------------------------------------------------
# OpenAI strict-schema adapter
# ---------------------------------------------------------------------------


def test_openai_strict_schema_sets_additional_properties_false():
    """
    [Unit] ai backends: verifies openai strict schema sets additional properties false.

    Scenario:
        Given test inputs and fixtures for openai strict schema sets additional properties false
        When test_openai_strict_schema_sets_additional_properties_false executes the target flow
        Then the expected outcome for openai strict schema sets additional properties false is confirmed.

    Boundaries:
        - Focus: openai strict schema sets additional properties false
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai strict schema sets additional properties false
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    schema = _to_openai_strict_schema(Hypothesis)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())
    assert "default" not in json.dumps(schema)


# ---------------------------------------------------------------------------
# AWS Bedrock - structured output
# ---------------------------------------------------------------------------


async def test_bedrock_structured_output_valid(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock structured output valid.

    Scenario:
        Given test inputs and fixtures for bedrock structured output valid
        When test_bedrock_structured_output_valid executes the target flow
        Then the expected outcome for bedrock structured output valid is confirmed.

    Boundaries:
        - Focus: bedrock structured output valid
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock structured output valid
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        return_value=_bedrock_tool_response({"root_cause": "uaf", "confidence": 0.8})
    )
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert result.confidence == 0.8
    assert backend.last_usage == {"input_tokens": 10, "output_tokens": 5}


async def test_bedrock_sends_tool_config_and_system(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock sends tool config and system.

    Scenario:
        Given test inputs and fixtures for bedrock sends tool config and system
        When test_bedrock_sends_tool_config_and_system executes the target flow
        Then the expected outcome for bedrock sends tool config and system is confirmed.

    Boundaries:
        - Focus: bedrock sends tool config and system
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock sends tool config and system
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        return_value=_bedrock_tool_response({"root_cause": "x", "confidence": 0.5})
    )
    await backend.generate("system prompt", _USER, Hypothesis)
    kwargs = client.converse.call_args.kwargs
    assert kwargs["modelId"] == "au.anthropic.claude-sonnet-4-6"
    assert kwargs["system"] == [{"text": "system prompt"}]
    # User message is wrapped in a Converse content block.
    assert kwargs["messages"][0]["content"] == [{"text": "analyze this"}]
    tool_choice = kwargs["toolConfig"]["toolChoice"]["tool"]["name"]
    assert tool_choice == "structured_output"
    spec = kwargs["toolConfig"]["tools"][0]["toolSpec"]
    assert spec["inputSchema"]["json"]["title"] == "Hypothesis"
    # Forced tool use ⇒ no thinking field is sent.
    assert "additionalModelRequestFields" not in kwargs


async def test_bedrock_retry_then_valid(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock retry then valid.

    Scenario:
        Given test inputs and fixtures for bedrock retry then valid
        When test_bedrock_retry_then_valid executes the target flow
        Then the expected outcome for bedrock retry then valid is confirmed.

    Boundaries:
        - Focus: bedrock retry then valid
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock retry then valid
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        side_effect=[
            _bedrock_tool_response({"root_cause": "x"}),  # missing confidence
            _bedrock_tool_response({"root_cause": "x", "confidence": 0.7}),
        ]
    )
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert client.converse.call_count == 2
    assert backend.last_usage == {"input_tokens": 20, "output_tokens": 10}


async def test_bedrock_raises_after_retry(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock raises after retry.

    Scenario:
        Given test inputs and fixtures for bedrock raises after retry
        When test_bedrock_raises_after_retry executes the target flow
        Then the expected outcome for bedrock raises after retry is confirmed.

    Boundaries:
        - Focus: bedrock raises after retry
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock raises after retry
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        return_value=_bedrock_tool_response({"root_cause": "x"})  # always invalid
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)
    assert client.converse.call_count == 2


async def test_bedrock_raises_when_no_tool_block(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock raises when no tool block.

    Scenario:
        Given test inputs and fixtures for bedrock raises when no tool block
        When test_bedrock_raises_when_no_tool_block executes the target flow
        Then the expected outcome for bedrock raises when no tool block is confirmed.

    Boundaries:
        - Focus: bedrock raises when no tool block
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock raises when no tool block
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(return_value=_bedrock_text_response("no tool here"))
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)


async def test_bedrock_unstructured_returns_text(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock unstructured returns text.

    Scenario:
        Given test inputs and fixtures for bedrock unstructured returns text
        When test_bedrock_unstructured_returns_text executes the target flow
        Then the expected outcome for bedrock unstructured returns text is confirmed.

    Boundaries:
        - Focus: bedrock unstructured returns text
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock unstructured returns text
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        return_value=_bedrock_text_response("hello world")
    )
    result = await backend.generate("system", _USER)
    assert result == "hello world"


async def test_bedrock_stream_yields_tokens(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock stream yields tokens.

    Scenario:
        Given test inputs and fixtures for bedrock stream yields tokens
        When test_bedrock_stream_yields_tokens executes the target flow
        Then the expected outcome for bedrock stream yields tokens is confirmed.

    Boundaries:
        - Focus: bedrock stream yields tokens
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock stream yields tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, client = bedrock_backend
    client.converse_stream = mock.MagicMock(
        return_value=_bedrock_stream_response(["a", "b", "c"])
    )
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_bedrock_client_error_becomes_backend_error(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """
    [Mock] ai backends: verifies bedrock client error becomes backend error.

    Scenario:
        Given test inputs and fixtures for bedrock client error becomes backend error
        When test_bedrock_client_error_becomes_backend_error executes the target flow
        Then the expected outcome for bedrock client error becomes backend error is confirmed.

    Boundaries:
        - Focus: bedrock client error becomes backend error
        - Fixtures/params: bedrock_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock client error becomes backend error
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    import botocore.exceptions

    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        side_effect=botocore.exceptions.ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse"
        )
    )
    with pytest.raises(AIBackendError, match="ThrottlingException"):
        await backend.generate("system", _USER)


def test_bedrock_registers_bearer_hook_when_token_present(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    [Mock] ai backends: verifies bedrock registers bearer hook when token present.

    Scenario:
        Given test inputs and fixtures for bedrock registers bearer hook when token present
        When test_bedrock_registers_bearer_hook_when_token_present executes the target flow
        Then the expected outcome for bedrock registers bearer hook when token present is confirmed.

    Boundaries:
        - Focus: bedrock registers bearer hook when token present
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock registers bearer hook when token present
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token")
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        AwsBedrockBackend(BedrockSettings())
    client.meta.events.register.assert_called_once()
    event_name = client.meta.events.register.call_args.args[0]
    assert event_name == "before-send.bedrock-runtime.*"


def test_bedrock_no_bearer_hook_without_token(monkeypatch: pytest.MonkeyPatch):
    """
    [Mock] ai backends: verifies bedrock no bearer hook without token.

    Scenario:
        Given test inputs and fixtures for bedrock no bearer hook without token
        When test_bedrock_no_bearer_hook_without_token executes the target flow
        Then the expected outcome for bedrock no bearer hook without token is confirmed.

    Boundaries:
        - Focus: bedrock no bearer hook without token
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock no bearer hook without token
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        AwsBedrockBackend(BedrockSettings())
    client.meta.events.register.assert_not_called()


# ---------------------------------------------------------------------------
# AWS Bedrock - new spec-compliance tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error_code",
    [
        "AccessDeniedException",
        "ServiceUnavailableException",
        "ValidationException",
        "ModelTimeoutException",
    ],
)
async def test_bedrock_client_error_codes_parametrized(
    monkeypatch: pytest.MonkeyPatch, error_code: str
):
    """Each stubbed ClientError code from converse surfaces as AIBackendError."""
    import botocore.exceptions

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(BedrockSettings())
    client.converse = mock.MagicMock(
        side_effect=botocore.exceptions.ClientError(
            {"Error": {"Code": error_code, "Message": "error detail"}}, "Converse"
        )
    )
    with pytest.raises(AIBackendError, match=error_code):
        await backend.generate("system", _USER)


async def test_bedrock_error_message_is_sanitised(monkeypatch: pytest.MonkeyPatch):
    """ClientError message (potentially containing secrets) must not appear in the
    raised AIBackendError; only the error code is surfaced."""
    import botocore.exceptions

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    secret_fragment = "sk-secret-ABCDEF1234567890"
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(BedrockSettings())
    client.converse = mock.MagicMock(
        side_effect=botocore.exceptions.ClientError(
            {
                "Error": {
                    "Code": "ValidationException",
                    "Message": f"invalid request, token={secret_fragment}",
                }
            },
            "Converse",
        )
    )
    with pytest.raises(AIBackendError) as exc_info:
        await backend.generate("system", _USER)
    error_str = str(exc_info.value)
    assert "ValidationException" in error_str
    assert secret_fragment not in error_str


def test_bedrock_region_precedence(monkeypatch: pytest.MonkeyPatch):
    """(a) explicit BedrockSettings(region=...) wins; (b) blank region uses AWS_DEFAULT_REGION."""
    # Part (a): explicit region in settings takes precedence.
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    session_a = mock.MagicMock()
    session_a.client.return_value = mock.MagicMock()
    with mock.patch("boto3.Session", return_value=session_a) as mock_session_cls:
        AwsBedrockBackend(BedrockSettings(region="eu-west-1"))
    # boto3.Session is called with the explicit region.
    call_kwargs = mock_session_cls.call_args.kwargs
    assert call_kwargs["region_name"] == "eu-west-1"

    # Part (b): blank region falls back to AWS_DEFAULT_REGION.
    session_b = mock.MagicMock()
    session_b.client.return_value = mock.MagicMock()
    with mock.patch("boto3.Session", return_value=session_b) as mock_session_cls_b:
        AwsBedrockBackend(BedrockSettings(region=""))
    call_kwargs_b = mock_session_cls_b.call_args.kwargs
    assert call_kwargs_b["region_name"] == "us-east-1"


def test_bedrock_bearer_hook_does_not_log_token(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
):
    """The bearer token value must never appear in log output during client construction;
    the auth-mode label 'bearer-token' must appear."""

    from loguru import logger

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "super-secret-bearer-xyz9876")
    log_records: list[str] = []

    sink_id = logger.add(log_records.append, level="DEBUG", format="{message}")
    try:
        client = mock.MagicMock()
        session = mock.MagicMock()
        session.client.return_value = client
        with mock.patch("boto3.Session", return_value=session):
            AwsBedrockBackend(BedrockSettings())
    finally:
        logger.remove(sink_id)

    combined = "\n".join(log_records)
    assert "super-secret-bearer-xyz9876" not in combined
    assert "bearer-token" in combined


async def test_bedrock_stream_interruption_raises_backend_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """A BotoCoreError raised mid-stream iteration surfaces as AIBackendError."""
    import botocore.exceptions

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(BedrockSettings())

    # The stream returns one good event then raises ReadTimeoutError on next().
    class _FaultingIterator:
        def __init__(self) -> None:
            self._count = 0

        def __iter__(self) -> _FaultingIterator:
            return self

        def __next__(self) -> dict[str, Any]:
            if self._count == 0:
                self._count += 1
                return {"contentBlockDelta": {"delta": {"text": "first "}}}
            raise botocore.exceptions.ReadTimeoutError(endpoint_url="https://bedrock.test")

    client.converse_stream = mock.MagicMock(return_value={"stream": _FaultingIterator()})

    with pytest.raises(AIBackendError, match="ReadTimeoutError"):
        async for _ in backend.stream("system", _USER):
            pass


async def test_bedrock_thinking_disabled_for_structured(monkeypatch: pytest.MonkeyPatch):
    """A qualifying thinking_budget_tokens + thinking-capable model + output_schema
    must produce NO additionalModelRequestFields/thinking in the Converse request."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    # Use a thinking-capable model and a qualifying budget.
    settings = BedrockSettings(
        model_id="au.anthropic.claude-sonnet-4-6",
        thinking_budget_tokens=2048,
    )
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)
    client.converse = mock.MagicMock(
        return_value=_bedrock_tool_response({"root_cause": "uaf", "confidence": 0.75})
    )
    await backend.generate("system", _USER, Hypothesis)
    kwargs = client.converse.call_args.kwargs
    # Forced tool use disables thinking - the field must be absent.
    assert "additionalModelRequestFields" not in kwargs


def test_bedrock_thinking_disabled_for_unsupported_model(monkeypatch: pytest.MonkeyPatch):
    """A qualifying budget with an unsupported model_id produces no thinking key."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    # Nova-2-Lite is not in _THINKING_SUPPORTED_PATTERNS.
    settings = BedrockSettings(
        model_id="global.amazon.nova-2-lite-v1:0",
        thinking_budget_tokens=2048,
    )
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)

    # Build a free-form request directly to inspect the request body.
    request = backend._build_request("system", _USER, output_schema=None)
    assert "additionalModelRequestFields" not in request


async def test_bedrock_parse_ignores_reasoning_blocks(monkeypatch: pytest.MonkeyPatch):
    """A Converse response with reasoningContent + text blocks → generate() returns
    only the concatenated text, not the reasoning content."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(BedrockSettings())

    # Mix a reasoningContent block with text blocks.
    response_with_reasoning: dict[str, Any] = {
        "output": {
            "message": {
                "content": [
                    {"reasoningContent": {"text": "internal chain-of-thought that must be hidden"}},
                    {"text": "root cause is "},
                    {"text": "a use-after-free."},
                ]
            }
        },
        "usage": {"inputTokens": 20, "outputTokens": 10},
        "stopReason": "end_turn",
    }
    client.converse = mock.MagicMock(return_value=response_with_reasoning)

    result = await backend.generate("system", _USER)
    assert result == "root cause is a use-after-free."
    # The reasoning block text must not appear in the result.
    assert "chain-of-thought" not in result


async def test_bedrock_thinking_enabled_for_free_form(monkeypatch: pytest.MonkeyPatch):
    """
    [Mock] ai backends: verifies bedrock thinking enabled for free form.

    Scenario:
        Given test inputs and fixtures for bedrock thinking enabled for free form
        When test_bedrock_thinking_enabled_for_free_form executes the target flow
        Then the expected outcome for bedrock thinking enabled for free form is confirmed.

    Boundaries:
        - Focus: bedrock thinking enabled for free form
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock thinking enabled for free form
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    settings = BedrockSettings(thinking_budget_tokens=2048)
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)
    client.converse = mock.MagicMock(return_value=_bedrock_text_response("ok"))
    await backend.generate("system", _USER)
    kwargs = client.converse.call_args.kwargs
    thinking = kwargs["additionalModelRequestFields"]["thinking"]
    assert thinking == {"type": "enabled", "budget_tokens": 2048}
    # Claude requires temperature == 1 when thinking is on.
    assert kwargs["inferenceConfig"]["temperature"] == 1.0


# ---------------------------------------------------------------------------
# has_reasoning - per-model reasoning-trace capability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model, expected",
    [
        ("claude-sonnet-4-6", True),
        ("claude-opus-4-6", True),
        ("claude-haiku-4-5", True),
        ("claude-3-7-sonnet", True),
        ("claude-3-5-sonnet", False),
        ("claude-3-haiku", False),
    ],
)
def test_anthropic_has_reasoning(model: str, expected: bool):
    """
    [Mock] ai backends: verifies anthropic has reasoning.

    Scenario:
        Given test inputs and fixtures for anthropic has reasoning
        When test_anthropic_has_reasoning executes the target flow
        Then the expected outcome for anthropic has reasoning is confirmed.

    Boundaries:
        - Focus: anthropic has reasoning
        - Fixtures/params: model, expected (parametrized, 6 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to anthropic has reasoning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = AnthropicBackend(AnthropicSettings(model=model))
    assert backend.has_reasoning is expected


def test_openai_has_reasoning_always_false(openai_backend: tuple[OpenAIBackend, Any]):
    """
    [Unit] ai backends: verifies openai has reasoning always false.

    Scenario:
        Given test inputs and fixtures for openai has reasoning always false
        When test_openai_has_reasoning_always_false executes the target flow
        Then the expected outcome for openai has reasoning always false is confirmed.

    Boundaries:
        - Focus: openai has reasoning always false
        - Fixtures/params: openai_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to openai has reasoning always false
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    backend, _ = openai_backend
    # gpt-5.4 is a reasoning model, but the trace is not returned over Chat Completions.
    assert backend._is_reasoning_model() is True
    assert backend.has_reasoning is False


@pytest.mark.parametrize(
    "model_id, expected",
    [
        ("au.anthropic.claude-sonnet-4-6", True),
        ("apac.amazon.nova-pro-v1:0", True),
        ("global.amazon.nova-2-lite-v1:0", False),
    ],
)
def test_bedrock_has_reasoning(
    monkeypatch: pytest.MonkeyPatch, model_id: str, expected: bool
):
    """
    [Mock] ai backends: verifies bedrock has reasoning.

    Scenario:
        Given test inputs and fixtures for bedrock has reasoning
        When test_bedrock_has_reasoning executes the target flow
        Then the expected outcome for bedrock has reasoning is confirmed.

    Boundaries:
        - Focus: bedrock has reasoning
        - Fixtures/params: monkeypatch, model_id, expected (parametrized, 3 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to bedrock has reasoning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    settings = BedrockSettings(model_id=model_id)
    session = mock.MagicMock()
    session.client.return_value = mock.MagicMock()
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)
    assert backend.has_reasoning is expected


def test_mock_backend_has_reasoning_defaults_false():
    """
    [Unit] ai backends: verifies mock backend has reasoning defaults false.

    Scenario:
        Given test inputs and fixtures for mock backend has reasoning defaults false
        When test_mock_backend_has_reasoning_defaults_false executes the target flow
        Then the expected outcome for mock backend has reasoning defaults false is confirmed.

    Boundaries:
        - Focus: mock backend has reasoning defaults false
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to mock backend has reasoning defaults false
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    from tests.unit.fixtures.mock_ai_backend import MockAIBackend

    assert MockAIBackend().has_reasoning is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_anthropic():
    """
    [Mock] ai backends: verifies factory returns anthropic.

    Scenario:
        Given test inputs and fixtures for factory returns anthropic
        When test_factory_returns_anthropic executes the target flow
        Then the expected outcome for factory returns anthropic is confirmed.

    Boundaries:
        - Focus: factory returns anthropic
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory returns anthropic
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = create_ai_backend(AISettings(provider="anthropic"))
    assert isinstance(backend, AnthropicBackend)


def test_factory_returns_openai():
    """
    [Mock] ai backends: verifies factory returns openai.

    Scenario:
        Given test inputs and fixtures for factory returns openai
        When test_factory_returns_openai executes the target flow
        Then the expected outcome for factory returns openai is confirmed.

    Boundaries:
        - Focus: factory returns openai
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory returns openai
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    with mock.patch("openai.AsyncOpenAI"):
        backend = create_ai_backend(AISettings(provider="openai"))
    assert isinstance(backend, OpenAIBackend)


def test_factory_returns_bedrock(monkeypatch: pytest.MonkeyPatch):
    """
    [Mock] ai backends: verifies factory returns bedrock.

    Scenario:
        Given test inputs and fixtures for factory returns bedrock
        When test_factory_returns_bedrock executes the target flow
        Then the expected outcome for factory returns bedrock is confirmed.

    Boundaries:
        - Focus: factory returns bedrock
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory returns bedrock
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    with mock.patch("boto3.Session"):
        backend = create_ai_backend(AISettings(provider="bedrock"))
    assert isinstance(backend, AwsBedrockBackend)


def test_factory_unknown_provider_raises():
    # Bypass AISettings validation to reach the factory's guard.
    """
    [Unit] ai backends: verifies factory unknown provider raises.

    Scenario:
        Given test inputs and fixtures for factory unknown provider raises
        When test_factory_unknown_provider_raises executes the target flow
        Then the expected outcome for factory unknown provider raises is confirmed.

    Boundaries:
        - Focus: factory unknown provider raises
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory unknown provider raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by ai backends
    """
    fake = SimpleNamespace(provider="grok")
    with pytest.raises(ValueError, match="Unknown AI provider"):
        create_ai_backend(fake)  # type: ignore[arg-type]
