"""Unit tests for the Anthropic and OpenAI backends using mocked SDK clients.

No network access: the SDK client classes are patched so __init__ never needs a
real API key and every response is fabricated.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest import mock

import botocore.exceptions
import pytest
from loguru import logger

from aegis_swr.backends.ai import create_ai_backend
from aegis_swr.backends.ai.anthropic_provider import AnthropicBackend
from aegis_swr.backends.ai.aws_bedrock_provider import AwsBedrockBackend
from aegis_swr.backends.ai.claude_cli_provider import (
    ClaudeCliBackend,
    _flatten_messages,
    _strip_code_fence,
)
from aegis_swr.backends.ai.openai_provider import OpenAIBackend, _to_openai_strict_schema
from aegis_swr.config.settings import (
    AISettings,
    AnthropicSettings,
    BedrockSettings,
    ClaudeCliSettings,
    OpenAISettings,
)
from aegis_swr.core.exceptions import AIBackendError, AIOutputValidationError
from aegis_swr.core.schemas import Hypothesis
from tests.unit.fixtures.mock_ai_backend import MockAIBackend

# ---------------------------------------------------------------------------
# Fake SDK response builders
# ---------------------------------------------------------------------------


def _anthropic_response(blocks: list[Any], inp: int = 10, out: int = 5) -> SimpleNamespace:
    """Build a fake Anthropic ``messages.create`` response with usage counters."""
    return SimpleNamespace(content=blocks, usage=SimpleNamespace(input_tokens=inp, output_tokens=out))


def _tool_block(data: dict[str, Any]) -> SimpleNamespace:
    """Build a fake Anthropic ``tool_use`` content block carrying *data*."""
    return SimpleNamespace(type="tool_use", input=data)


def _text_block(text: str) -> SimpleNamespace:
    """Build a fake Anthropic ``text`` content block carrying *text*."""
    return SimpleNamespace(type="text", text=text)


def _openai_response(content: str, ptok: int = 10, ctok: int = 5) -> SimpleNamespace:
    """Build a fake OpenAI chat completion response wrapping *content*."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], usage=SimpleNamespace(prompt_tokens=ptok, completion_tokens=ctok))


class _FakeStreamCtx:
    """Async context manager mimicking anthropic ``messages.stream(...)``"""

    def __init__(self, tokens: list[str]):
        """Store the scripted stream *tokens*."""
        self._tokens = tokens

    async def __aenter__(self) -> _FakeStreamCtx:
        """Enter the fake stream context, returning self."""
        return self

    async def __aexit__(self, *args: Any) -> bool:
        """Exit the fake stream context without suppressing exceptions."""
        return False

    @property
    def text_stream(self) -> Any:
        """Return an async generator yielding the scripted tokens."""

        async def _gen() -> Any:
            """Yield each scripted token in order."""
            for token in self._tokens:
                yield token

        return _gen()


async def _openai_chunks(tokens: list[str]) -> Any:
    """Yield fake OpenAI streaming chunks for *tokens*, then a usage-only chunk."""
    for token in tokens:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=token))])
    yield SimpleNamespace(choices=[])  # final usage chunk has no choices


def _bedrock_tool_response(data: dict[str, Any], inp: int = 10, out: int = 5) -> dict[str, Any]:
    """Build a fake Bedrock Converse tool-use response carrying *data*."""
    return {
        "output": {"message": {"content": [{"toolUse": {"name": "structured_output", "input": data}}]}},
        "usage": {"inputTokens": inp, "outputTokens": out},
        "stopReason": "tool_use",
    }


def _bedrock_text_response(text: str, inp: int = 10, out: int = 5) -> dict[str, Any]:
    """Build a fake Bedrock Converse free-form text response carrying *text*."""
    return {
        "output": {"message": {"content": [{"text": text}]}},
        "usage": {"inputTokens": inp, "outputTokens": out},
        "stopReason": "end_turn",
    }


def _bedrock_stream_response(tokens: list[str]) -> dict[str, Any]:
    """Build a fake Bedrock ``converse_stream`` event list ending in ``messageStop``."""
    # converse_stream returns {"stream": <EventStream>}; a list is an iterable
    # stand-in. A trailing non-text event exercises the text-only filter.
    events: list[dict[str, Any]] = [{"contentBlockDelta": {"delta": {"text": t}}} for t in tokens]
    events.append({"messageStop": {"stopReason": "end_turn"}})
    return {"stream": events}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anthropic_backend() -> tuple[AnthropicBackend, Any]:
    """Yield an ``AnthropicBackend`` with a patched SDK client mock."""
    settings = AnthropicSettings(model="claude-sonnet-4-6")
    with mock.patch("anthropic.AsyncAnthropic") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = AnthropicBackend(settings)
    return backend, client


@pytest.fixture
def openai_backend() -> tuple[OpenAIBackend, Any]:
    """Yield an ``OpenAIBackend`` with a patched SDK client mock."""
    settings = OpenAISettings(model="gpt-5.4")
    with mock.patch("openai.AsyncOpenAI") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = OpenAIBackend(settings)
    return backend, client


@pytest.fixture
def bedrock_backend(monkeypatch: pytest.MonkeyPatch) -> tuple[AwsBedrockBackend, Any]:
    """Yield an ``AwsBedrockBackend`` with a patched boto3 session and bearer token."""
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
    """[Unit] ai backends: a valid Anthropic tool block parses into a Hypothesis.

    Scenario: the mock client returns one tool block with a well-formed
    ``root_cause``/``confidence`` payload.

    Boundaries: the SDK client is mocked; only the parse and usage bookkeeping are
    under test.

    On failure, first check: the result must be a ``Hypothesis`` with the expected
    confidence and ``last_usage`` reflecting the response tokens.
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
    """[Unit] ai backends: Anthropic requests carry cache control and forced tool.

    Scenario: a structured generate call is made and the recorded request kwargs
    are inspected.

    Boundaries: the SDK client is mocked; only request assembly is asserted.

    On failure, first check: the system block must set ephemeral cache control,
    ``tool_choice`` must force ``structured_output``, and the tool schema title
    must be ``Hypothesis``.
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
    """[Unit] ai backends: Anthropic retries once and accumulates usage on success.

    Scenario: the first response omits ``confidence`` (invalid) and the second is
    valid.

    Boundaries: the SDK client is mocked with a two-call side effect.

    On failure, first check: the result must be a ``Hypothesis``, the client must
    be called twice, and usage must sum across both calls.
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
    """[Unit] ai backends: Anthropic raises after the retry budget is exhausted.

    Scenario: every response omits ``confidence`` so validation always fails.

    Boundaries: the SDK client is mocked to always return an invalid payload.

    On failure, first check: ``generate`` must raise ``AIOutputValidationError``
    after exactly two attempts.
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
    """[Unit] ai backends: an unstructured Anthropic call concatenates text blocks.

    Scenario: the mock returns two text blocks and ``generate`` is called with no
    schema.

    Boundaries: the SDK client is mocked; only text extraction is asserted.

    On failure, first check: the result must be the joined block text.
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
    """[Unit] ai backends: Anthropic ``stream`` yields each token in order.

    Scenario: the mock stream context yields three tokens.

    Boundaries: the SDK stream is a fake async context manager.

    On failure, first check: the collected tokens must equal the scripted list.
    """
    backend, client = anthropic_backend
    client.messages.stream = mock.MagicMock(return_value=_FakeStreamCtx(["a", "b", "c"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_anthropic_raises_when_no_tool_block(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    """[Unit] ai backends: a structured Anthropic call with no tool block raises.

    Scenario: the mock returns only a text block when a schema is requested.

    Boundaries: the SDK client is mocked; only the missing-tool guard is exercised.

    On failure, first check: ``generate`` must raise ``AIOutputValidationError``.
    """
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(return_value=_anthropic_response([_text_block("no tool here")]))
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)


# ---------------------------------------------------------------------------
# OpenAI - structured output
# ---------------------------------------------------------------------------


async def test_openai_structured_output_valid(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """[Unit] ai backends: a valid OpenAI JSON response parses into a Hypothesis.

    Scenario: the mock returns well-formed JSON for the requested schema.

    Boundaries: the SDK client is mocked; only parse and usage are asserted.

    On failure, first check: the result must be a ``Hypothesis`` with the expected
    confidence and mapped usage counters.
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
    """[Unit] ai backends: OpenAI requests use a strict json_schema response format.

    Scenario: a structured generate call is made and the request kwargs inspected.

    Boundaries: the SDK client is mocked; only request assembly is asserted.

    On failure, first check: the response format must be strict ``json_schema`` and
    the system prompt must be the first message.
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
    """[Unit] ai backends: a reasoning model uses max_completion_tokens, no temperature.

    Scenario: the reasoning model ``gpt-5.4`` runs a structured generate call and
    the request kwargs are inspected.

    Boundaries: the SDK client is mocked; only the reasoning-model param branch is
    asserted.

    On failure, first check: ``max_completion_tokens`` must be present (>=16000)
    while ``max_tokens`` and ``temperature`` are absent.
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
    """[Unit] ai backends: a non-reasoning model uses max_tokens and temperature.

    Scenario: a ``gpt-4o`` backend with explicit temperature/max_tokens runs a
    structured generate call.

    Boundaries: the SDK client is mocked; only the non-reasoning param branch is
    asserted.

    On failure, first check: ``max_tokens`` and ``temperature`` must be honoured
    and ``max_completion_tokens`` absent.
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
    """[Unit] ai backends: OpenAI retries once and succeeds on the valid response.

    Scenario: the first response omits ``confidence`` and the second is valid.

    Boundaries: the SDK client is mocked with a two-call side effect.

    On failure, first check: the result must be a ``Hypothesis`` and the client
    must be called twice.
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
    """[Unit] ai backends: malformed OpenAI JSON raises after the retry budget.

    Scenario: the mock returns non-JSON content for a structured request.

    Boundaries: the SDK client is mocked to always return invalid content.

    On failure, first check: ``generate`` must raise ``AIOutputValidationError``
    after exactly two attempts.
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(return_value=_openai_response("not json at all"))
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)
    assert client.chat.completions.create.call_count == 2


async def test_openai_unstructured_returns_text(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """[Unit] ai backends: an unstructured OpenAI call returns the message content.

    Scenario: the mock returns plain text and ``generate`` is called with no schema.

    Boundaries: the SDK client is mocked; only text extraction is asserted.

    On failure, first check: the result must equal the message content verbatim.
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(return_value=_openai_response("plain answer"))
    result = await backend.generate("system", _USER)
    assert result == "plain answer"


async def test_openai_stream_yields_tokens(
    openai_backend: tuple[OpenAIBackend, Any],
):
    """[Unit] ai backends: OpenAI ``stream`` yields each delta token in order.

    Scenario: the mock stream yields two content deltas then a usage-only chunk.

    Boundaries: the SDK stream is a fake async generator.

    On failure, first check: the collected tokens must equal the scripted list and
    the choiceless final chunk must be ignored.
    """
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(return_value=_openai_chunks(["x", "y"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["x", "y"]


# ---------------------------------------------------------------------------
# OpenAI strict-schema adapter
# ---------------------------------------------------------------------------


def test_openai_strict_schema_sets_additional_properties_false():
    """[Unit] ai backends: the strict-schema adapter forbids additional properties.

    Scenario: ``_to_openai_strict_schema`` is called on the ``Hypothesis`` model.

    Boundaries: exercises the pure schema-rewriting helper directly.

    On failure, first check: ``additionalProperties`` must be False, every property
    must be required, and no ``default`` key may survive.
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
    """[Unit] ai backends: a valid Bedrock tool response parses into a Hypothesis.

    Scenario: the mock ``converse`` returns a well-formed tool-use payload.

    Boundaries: the boto3 client is mocked; only parse and usage are asserted.

    On failure, first check: the result must be a ``Hypothesis`` with the expected
    confidence and mapped usage counters.
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(return_value=_bedrock_tool_response({"root_cause": "uaf", "confidence": 0.8}))
    result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert result.confidence == 0.8
    assert backend.last_usage == {"input_tokens": 10, "output_tokens": 5}


async def test_bedrock_sends_tool_config_and_system(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """[Unit] ai backends: Bedrock requests carry tool config, system, and no thinking.

    Scenario: a structured generate call is made and the ``converse`` kwargs
    inspected.

    Boundaries: the boto3 client is mocked; only request assembly is asserted.

    On failure, first check: the model id, system block, user content wrapping,
    forced tool name, schema title must match, and thinking fields must be absent.
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(return_value=_bedrock_tool_response({"root_cause": "x", "confidence": 0.5}))
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
    """[Unit] ai backends: Bedrock retries once and accumulates usage on success.

    Scenario: the first tool response omits ``confidence`` and the second is valid.

    Boundaries: the boto3 client is mocked with a two-call side effect.

    On failure, first check: the result must be a ``Hypothesis``, ``converse`` must
    run twice, and usage must sum across both calls.
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
    """[Unit] ai backends: Bedrock raises after the retry budget is exhausted.

    Scenario: every tool response omits ``confidence`` so validation always fails.

    Boundaries: the boto3 client is mocked to always return an invalid payload.

    On failure, first check: ``generate`` must raise ``AIOutputValidationError``
    after exactly two attempts.
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
    """[Unit] ai backends: a structured Bedrock call with no tool block raises.

    Scenario: the mock returns a free-form text response for a structured request.

    Boundaries: the boto3 client is mocked; only the missing-tool guard is exercised.

    On failure, first check: ``generate`` must raise ``AIOutputValidationError``.
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(return_value=_bedrock_text_response("no tool here"))
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)


async def test_bedrock_unstructured_returns_text(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """[Unit] ai backends: an unstructured Bedrock call returns the response text.

    Scenario: the mock returns a free-form text response and ``generate`` is called
    with no schema.

    Boundaries: the boto3 client is mocked; only text extraction is asserted.

    On failure, first check: the result must equal the response text verbatim.
    """
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(return_value=_bedrock_text_response("hello world"))
    result = await backend.generate("system", _USER)
    assert result == "hello world"


async def test_bedrock_stream_yields_tokens(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """[Unit] ai backends: Bedrock ``stream`` yields each text delta in order.

    Scenario: the mock ``converse_stream`` yields three text deltas then a stop
    event.

    Boundaries: the boto3 stream is a fake event list.

    On failure, first check: the collected tokens must equal the scripted list and
    the non-text stop event must be filtered out.
    """
    backend, client = bedrock_backend
    client.converse_stream = mock.MagicMock(return_value=_bedrock_stream_response(["a", "b", "c"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_bedrock_client_error_becomes_backend_error(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    """[Unit] ai backends: a boto ClientError from converse becomes AIBackendError.

    Scenario: ``converse`` raises a throttling ``ClientError``.

    Boundaries: the boto3 client is mocked to raise; only error translation is
    asserted.

    On failure, first check: ``generate`` must raise ``AIBackendError`` carrying
    the ``ThrottlingException`` code.
    """

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
    """[Unit] ai backends: a present bearer token registers the auth event hook.

    Scenario: ``AWS_BEARER_TOKEN_BEDROCK`` is set and a backend is constructed.

    Boundaries: the boto3 session/client are mocked; only hook registration is
    asserted.

    On failure, first check: the client's event register must be called once for
    ``before-send.bedrock-runtime.*``.
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
    """[Unit] ai backends: no bearer token means no auth event hook is registered.

    Scenario: ``AWS_BEARER_TOKEN_BEDROCK`` is unset and a backend is constructed.

    Boundaries: the boto3 session/client are mocked; only hook absence is asserted.

    On failure, first check: the client's event register must not be called.
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
async def test_bedrock_client_error_codes_parametrized(monkeypatch: pytest.MonkeyPatch, error_code: str):
    """[Unit] ai backends: each stubbed ClientError code surfaces as AIBackendError.

    Scenario: ``converse`` raises a ``ClientError`` for a parametrized error code.

    Boundaries: the boto3 client is mocked to raise; only error translation is
    asserted.

    On failure, first check: ``generate`` must raise ``AIBackendError`` matching the
    parametrized error code.
    """

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
    """[Unit] ai backends: a ClientError message with secrets is not surfaced.

    Scenario: ``converse`` raises a ``ClientError`` whose message embeds a secret
    token.

    Boundaries: enforces the sensitivity policy - only the error code may escape.

    On failure, first check: the raised ``AIBackendError`` must contain the code but
    never the secret fragment.
    """

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
    """[Unit] ai backends: explicit region wins, blank region falls back to env.

    Scenario: a backend is built once with an explicit region and once with a
    blank region while ``AWS_DEFAULT_REGION`` is set.

    Boundaries: the boto3 session is mocked; only region resolution is asserted.

    On failure, first check: the explicit region must reach ``Session`` and a blank
    region must fall back to ``AWS_DEFAULT_REGION``.
    """
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


def test_bedrock_bearer_hook_does_not_log_token(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]):
    """[Unit] ai backends: the bearer token is never logged during construction.

    Scenario: a backend is constructed with a secret bearer token while a DEBUG
    log sink captures output.

    Boundaries: enforces the sensitivity policy for auth material.

    On failure, first check: the token value must be absent from logs while the
    ``bearer-token`` auth-mode label is present.
    """

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
    """[Unit] ai backends: a BotoCoreError mid-stream surfaces as AIBackendError.

    Scenario: the stream yields one good event then raises ``ReadTimeoutError`` on
    the next iteration.

    Boundaries: the boto3 stream is a faulting iterator; only mid-stream error
    translation is asserted.

    On failure, first check: iterating ``stream`` must raise ``AIBackendError``
    matching ``ReadTimeoutError``.
    """

    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(BedrockSettings())

    # The stream returns one good event then raises ReadTimeoutError on next().
    class _FaultingIterator:
        """Iterator that yields one text event, then raises ``ReadTimeoutError``."""

        def __init__(self):
            """Initialise the yielded-event counter."""
            self._count = 0

        def __iter__(self) -> _FaultingIterator:
            """Return self as the iterator."""
            return self

        def __next__(self) -> dict[str, Any]:
            """Yield one text event, then raise ``ReadTimeoutError``."""
            if self._count == 0:
                self._count += 1
                return {"contentBlockDelta": {"delta": {"text": "first "}}}
            raise botocore.exceptions.ReadTimeoutError(endpoint_url="https://bedrock.test")

    client.converse_stream = mock.MagicMock(return_value={"stream": _FaultingIterator()})

    with pytest.raises(AIBackendError, match="ReadTimeoutError"):
        async for _ in backend.stream("system", _USER):
            pass


async def test_bedrock_thinking_disabled_for_structured(monkeypatch: pytest.MonkeyPatch):
    """[Unit] ai backends: forced tool use disables thinking for structured output.

    Scenario: a thinking-capable model with a qualifying budget runs a structured
    generate call.

    Boundaries: the boto3 client is mocked; only the thinking-field suppression is
    asserted.

    On failure, first check: ``additionalModelRequestFields`` must be absent when a
    schema forces tool use.
    """
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
    client.converse = mock.MagicMock(return_value=_bedrock_tool_response({"root_cause": "uaf", "confidence": 0.75}))
    await backend.generate("system", _USER, Hypothesis)
    kwargs = client.converse.call_args.kwargs
    # Forced tool use disables thinking - the field must be absent.
    assert "additionalModelRequestFields" not in kwargs


def test_bedrock_thinking_disabled_for_unsupported_model(monkeypatch: pytest.MonkeyPatch):
    """[Unit] ai backends: an unsupported model omits the thinking key.

    Scenario: a qualifying budget is paired with a non-thinking-capable model id and
    a free-form request is built directly.

    Boundaries: the boto3 client is mocked; only the model-capability gate is
    asserted.

    On failure, first check: the built request must not contain
    ``additionalModelRequestFields``.
    """
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
    """[Unit] ai backends: reasoning-content blocks are excluded from the text result.

    Scenario: a Converse response mixes a ``reasoningContent`` block with text
    blocks and ``generate`` is called with no schema.

    Boundaries: enforces the sensitivity policy - internal chain-of-thought must
    not leak into results.

    On failure, first check: the result must be only the concatenated text, never
    the reasoning content.
    """
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
    """[Unit] ai backends: free-form generate enables thinking with temperature 1.

    Scenario: a qualifying budget runs a free-form (no schema) generate call and
    the ``converse`` kwargs are inspected.

    Boundaries: the boto3 client is mocked; only the thinking-field assembly is
    asserted.

    On failure, first check: the thinking field must be enabled with the budget and
    ``inferenceConfig`` temperature must be 1.0.
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
    """[Unit] ai backends: ``has_reasoning`` reflects the Anthropic model generation.

    Scenario: a backend is built for a parametrized model and ``has_reasoning`` is
    read.

    Boundaries: the SDK client is mocked; only the capability flag is asserted.

    On failure, first check: ``has_reasoning`` must equal the parametrized
    expectation for each model.
    """
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = AnthropicBackend(AnthropicSettings(model=model))
    assert backend.has_reasoning is expected


def test_openai_has_reasoning_always_false(openai_backend: tuple[OpenAIBackend, Any]):
    """[Unit] ai backends: OpenAI ``has_reasoning`` is always False over Chat.

    Scenario: a reasoning-model backend is inspected for both the internal flag and
    the public capability.

    Boundaries: proves reasoning traces are not surfaced over Chat Completions.

    On failure, first check: ``_is_reasoning_model`` may be True but ``has_reasoning``
    must be False.
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
def test_bedrock_has_reasoning(monkeypatch: pytest.MonkeyPatch, model_id: str, expected: bool):
    """[Unit] ai backends: Bedrock ``has_reasoning`` reflects the model id capability.

    Scenario: a backend is built for a parametrized model id and ``has_reasoning``
    is read.

    Boundaries: the boto3 session is mocked; only the capability flag is asserted.

    On failure, first check: ``has_reasoning`` must equal the parametrized
    expectation for each model id.
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    settings = BedrockSettings(model_id=model_id)
    session = mock.MagicMock()
    session.client.return_value = mock.MagicMock()
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)
    assert backend.has_reasoning is expected


def test_mock_backend_has_reasoning_defaults_false():
    """[Unit] ai backends: the test MockAIBackend defaults ``has_reasoning`` to False.

    Scenario: a fresh ``MockAIBackend`` is inspected.

    Boundaries: exercises the test fixture's default capability only.

    On failure, first check: ``has_reasoning`` must be False by default.
    """

    assert MockAIBackend().has_reasoning is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_anthropic():
    """[Unit] ai backends: the factory builds an AnthropicBackend for provider anthropic.

    Scenario: ``create_ai_backend`` is called with ``provider="anthropic"``.

    Boundaries: the SDK client is mocked; only backend selection is asserted.

    On failure, first check: the returned instance must be an ``AnthropicBackend``.
    """
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = create_ai_backend(AISettings(provider="anthropic"))
    assert isinstance(backend, AnthropicBackend)


def test_factory_returns_openai():
    """[Unit] ai backends: the factory builds an OpenAIBackend for provider openai.

    Scenario: ``create_ai_backend`` is called with ``provider="openai"``.

    Boundaries: the SDK client is mocked; only backend selection is asserted.

    On failure, first check: the returned instance must be an ``OpenAIBackend``.
    """
    with mock.patch("openai.AsyncOpenAI"):
        backend = create_ai_backend(AISettings(provider="openai"))
    assert isinstance(backend, OpenAIBackend)


def test_factory_returns_bedrock(monkeypatch: pytest.MonkeyPatch):
    """[Unit] ai backends: the factory builds an AwsBedrockBackend for provider bedrock.

    Scenario: ``create_ai_backend`` is called with ``provider="bedrock"`` and a
    bearer token set.

    Boundaries: the boto3 session is mocked; only backend selection is asserted.

    On failure, first check: the returned instance must be an ``AwsBedrockBackend``.
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    with mock.patch("boto3.Session"):
        backend = create_ai_backend(AISettings(provider="bedrock"))
    assert isinstance(backend, AwsBedrockBackend)


def test_factory_returns_claude_cli():
    """[Unit] ai backends: the factory builds a ClaudeCliBackend for provider claude_cli.

    Scenario: ``create_ai_backend`` is called with ``provider="claude_cli"``.

    Boundaries: no subprocess is spawned; only backend selection is asserted.

    On failure, first check: the returned instance must be a ``ClaudeCliBackend``.
    """
    backend = create_ai_backend(AISettings(provider="claude_cli"))
    assert isinstance(backend, ClaudeCliBackend)


def test_factory_unknown_provider_raises():
    """[Unit] ai backends: the factory rejects an unknown provider.

    Scenario: a settings stand-in with ``provider="grok"`` bypasses validation and
    reaches the factory guard.

    Boundaries: exercises the factory's provider guard only.

    On failure, first check: ``create_ai_backend`` must raise ``ValueError`` matching
    ``Unknown AI provider``.
    """
    fake = SimpleNamespace(provider="grok")
    with pytest.raises(ValueError, match="Unknown AI provider"):
        create_ai_backend(fake)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Claude CLI - local ``claude`` subprocess backend (no API key)
# ---------------------------------------------------------------------------


def _claude_cli_envelope(
    result: str,
    inp: int = 10,
    out: int = 5,
    is_error: bool = False,
    subtype: str = "success",
) -> bytes:
    """Build the single JSON envelope emitted by ``claude -p --output-format json``."""
    return json.dumps(
        {
            "result": result,
            "usage": {"input_tokens": inp, "output_tokens": out},
            "is_error": is_error,
            "subtype": subtype,
        }
    ).encode()


def _make_fake_process(stdout_bytes: bytes, returncode: int = 0, stderr_bytes: bytes = b"") -> Any:
    """Build a fake ``asyncio`` subprocess with StreamReader stdout/stderr at EOF."""
    stdout = asyncio.StreamReader()
    stdout.feed_data(stdout_bytes)
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_data(stderr_bytes)
    stderr.feed_eof()
    proc = mock.MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    stdin = mock.MagicMock()
    stdin.drain = mock.AsyncMock()
    proc.stdin = stdin
    proc.returncode = returncode
    proc.wait = mock.AsyncMock(return_value=returncode)
    return proc


def _patch_exec(*procs: Any) -> Any:
    """Patch ``asyncio.create_subprocess_exec`` to return the given fake processes."""
    if len(procs) == 1:
        return mock.patch("asyncio.create_subprocess_exec", mock.AsyncMock(return_value=procs[0]))
    return mock.patch("asyncio.create_subprocess_exec", mock.AsyncMock(side_effect=list(procs)))


async def test_claude_cli_unstructured_returns_text():
    """[Unit] ai backends: an unstructured claude CLI call returns the result text.

    Scenario: the fake process prints a JSON envelope whose ``result`` is plain
    text and ``generate`` is called with no schema.

    Boundaries: the subprocess is faked; only envelope parsing and usage are
    asserted.

    On failure, first check: the result must equal the envelope ``result`` and
    ``last_usage`` must reflect the envelope token counts.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    proc = _make_fake_process(_claude_cli_envelope("root cause is a use-after-free."))
    with _patch_exec(proc):
        result = await backend.generate("system", _USER)
    assert result == "root cause is a use-after-free."
    assert backend.last_usage == {"input_tokens": 10, "output_tokens": 5}


async def test_claude_cli_structured_output_valid():
    """[Unit] ai backends: a valid claude CLI JSON result parses into a Hypothesis.

    Scenario: the ``result`` field holds a JSON object matching the schema.

    Boundaries: the subprocess is faked; only parse/validate and usage are
    asserted.

    On failure, first check: the result must be a ``Hypothesis`` with the expected
    confidence and mapped usage counters.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    payload = json.dumps({"root_cause": "uaf", "confidence": 0.8})
    proc = _make_fake_process(_claude_cli_envelope(payload))
    with _patch_exec(proc):
        result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert result.confidence == 0.8
    assert backend.last_usage == {"input_tokens": 10, "output_tokens": 5}


async def test_claude_cli_payload_goes_via_stdin_not_argv():
    """[Unit] ai backends: incident payload travels on stdin, never on argv (C13).

    Scenario: a generate call is made and both the argv and the stdin write are
    captured from the faked subprocess.

    Boundaries: enforces the security rule that payload text is invisible to ``ps``.

    On failure, first check: the message content must be absent from every argv
    token and present in the bytes written to stdin; ``--bare`` must never appear.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    proc = _make_fake_process(_claude_cli_envelope("ok"))
    secret_payload = "SECRET-INCIDENT-PAYLOAD-42"
    messages = [{"role": "user", "content": secret_payload}]
    with _patch_exec(proc) as exec_mock:
        await backend.generate("persona system prompt", messages)
    argv = list(exec_mock.await_args.args)
    assert all(secret_payload not in token for token in argv)
    assert "--bare" not in argv
    assert "--restricted" in argv
    stdin_written = proc.stdin.write.call_args.args[0]
    assert secret_payload.encode() in stdin_written


async def test_claude_cli_is_error_raises_backend_error():
    """[Unit] ai backends: an ``is_error`` envelope surfaces as AIBackendError.

    Scenario: the fake process prints an envelope with ``is_error: true``.

    Boundaries: the subprocess is faked; only error translation is asserted.

    On failure, first check: ``generate`` must raise ``AIBackendError`` naming the
    model, never the payload.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=0))
    proc = _make_fake_process(_claude_cli_envelope("partial", is_error=True, subtype="error_during_execution"))
    with _patch_exec(proc), pytest.raises(AIBackendError, match="claude-sonnet-4-6"):
        await backend.generate("system", _USER)


async def test_claude_cli_nonzero_exit_raises_backend_error():
    """[Unit] ai backends: a non-zero exit with no parseable output raises.

    Scenario: the fake process exits with code 1 and prints nothing.

    Boundaries: the subprocess is faked; only the exit-code failure path is
    asserted.

    On failure, first check: ``generate`` must raise ``AIBackendError`` mentioning
    the exit code.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=0))
    proc = _make_fake_process(b"", returncode=1)
    with _patch_exec(proc), pytest.raises(AIBackendError, match="exited with code 1"):
        await backend.generate("system", _USER)


async def test_claude_cli_unparseable_output_raises():
    """[Unit] ai backends: unparseable stdout on a clean exit raises AIBackendError.

    Scenario: the fake process exits 0 but prints non-JSON text.

    Boundaries: the subprocess is faked; only the parse-failure path is asserted.

    On failure, first check: ``generate`` must raise ``AIBackendError`` matching
    ``unparseable``.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=0))
    proc = _make_fake_process(b"not json at all")
    with _patch_exec(proc), pytest.raises(AIBackendError, match="unparseable"):
        await backend.generate("system", _USER)


async def test_claude_cli_retries_process_failure_then_succeeds():
    """[Unit] ai backends: a process-level failure is retried with backoff.

    Scenario: the first spawn exits non-zero, the second returns a good envelope;
    ``asyncio.sleep`` is patched so the backoff does not delay the test.

    Boundaries: the subprocess is faked with a two-call side effect.

    On failure, first check: the result must be the second envelope's text and
    ``create_subprocess_exec`` must be awaited twice.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=2))
    bad = _make_fake_process(b"", returncode=1)
    good = _make_fake_process(_claude_cli_envelope("recovered"))
    with _patch_exec(bad, good) as exec_mock, mock.patch("asyncio.sleep", mock.AsyncMock()):
        result = await backend.generate("system", _USER)
    assert result == "recovered"
    assert exec_mock.await_count == 2


async def test_claude_cli_raises_after_retries_exhausted():
    """[Unit] ai backends: repeated process failures raise after the retry budget.

    Scenario: every spawn exits non-zero and ``asyncio.sleep`` is patched.

    Boundaries: the subprocess is faked to always fail.

    On failure, first check: ``generate`` must raise ``AIBackendError`` after
    ``max_retries + 1`` attempts.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=2))
    procs = [_make_fake_process(b"", returncode=1) for _ in range(3)]
    with _patch_exec(*procs) as exec_mock, mock.patch("asyncio.sleep", mock.AsyncMock()):
        with pytest.raises(AIBackendError):
            await backend.generate("system", _USER)
    assert exec_mock.await_count == 3


async def test_claude_cli_stream_yields_partial_deltas():
    """[Unit] ai backends: ``stream`` yields ``text_delta`` frames in order.

    Scenario: the fake process emits two partial-message text deltas then a
    terminal ``result`` frame.

    Boundaries: the subprocess is faked; only delta extraction is asserted.

    On failure, first check: the collected tokens must equal the scripted deltas.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    frames = [
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "hel"}},
        },
        {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "lo"}},
        },
        {"type": "result", "subtype": "success", "is_error": False, "usage": {"input_tokens": 3, "output_tokens": 2}},
    ]
    stdout = ("\n".join(json.dumps(f) for f in frames) + "\n").encode()
    proc = _make_fake_process(stdout)
    with _patch_exec(proc):
        tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["hel", "lo"]


async def test_claude_cli_stream_falls_back_to_complete_assistant_frames():
    """[Unit] ai backends: ``stream`` yields complete assistant text when no partials.

    Scenario: the fake process emits only a complete ``assistant`` frame (no
    partial-message deltas) then a ``result`` frame.

    Boundaries: the subprocess is faked; only the fallback path is asserted.

    On failure, first check: the single complete-frame text must be yielded once.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    frames = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "full answer"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "usage": {"input_tokens": 1, "output_tokens": 1}},
    ]
    stdout = ("\n".join(json.dumps(f) for f in frames) + "\n").encode()
    proc = _make_fake_process(stdout)
    with _patch_exec(proc):
        tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["full answer"]


def test_claude_cli_flatten_single_user_message_verbatim():
    """[Unit] ai backends: a lone user message is flattened to its content verbatim.

    Scenario: ``_flatten_messages`` is called with a single user turn.

    Boundaries: exercises the pure transcript helper directly.

    On failure, first check: the output must equal the message content with no
    role label added.
    """
    assert _flatten_messages([{"role": "user", "content": "just this"}]) == "just this"


def test_claude_cli_flatten_multi_turn_labels_roles():
    """[Unit] ai backends: a multi-turn conversation is rendered with role labels.

    Scenario: ``_flatten_messages`` is called with a user + assistant + user
    conversation.

    Boundaries: exercises the pure transcript helper directly.

    On failure, first check: each turn must be delimited and role-labelled in order.
    """
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "second"},
    ]
    rendered = _flatten_messages(messages)
    assert rendered == "[USER]\nfirst\n\n[ASSISTANT]\nreply\n\n[USER]\nsecond"


def test_claude_cli_rejects_repo_root_cwd(tmp_path: Any):
    """[Unit] ai backends: a cwd that is an ancestor of the repo root is rejected.

    Scenario: a settings ``cwd`` is set to a directory that contains a ``.git``
    marker (making it the detected repo root) and a backend is constructed.

    Boundaries: exercises the construction-time cwd guard only.

    On failure, first check: construction must raise ``AIBackendError`` naming the
    repository-root rule.
    """
    (tmp_path / ".git").mkdir()
    with mock.patch("aegis_swr.backends.ai.claude_cli_provider.Path.cwd", return_value=tmp_path):
        with pytest.raises(AIBackendError, match="repository root"):
            ClaudeCliBackend(ClaudeCliSettings(cwd=str(tmp_path)))


def test_claude_cli_accepts_safe_cwd(tmp_path: Any):
    """[Unit] ai backends: a cwd outside the repo tree is accepted and resolved.

    Scenario: the repo root is a sibling directory of an explicit, safe ``cwd``.

    Boundaries: exercises the construction-time cwd guard's accept path.

    On failure, first check: construction must succeed and record the resolved cwd.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    safe = tmp_path / "scratch"
    safe.mkdir()
    with mock.patch("aegis_swr.backends.ai.claude_cli_provider.Path.cwd", return_value=repo):
        backend = ClaudeCliBackend(ClaudeCliSettings(cwd=str(safe)))
    assert backend._explicit_cwd == str(safe.resolve())


@pytest.mark.parametrize(
    "model, expected",
    [
        ("claude-sonnet-4-6", True),
        ("claude-opus-4-8", True),
        ("claude-3-7-sonnet", True),
        ("claude-3-5-sonnet", False),
    ],
)
def test_claude_cli_has_reasoning(model: str, expected: bool):
    """[Unit] ai backends: ``has_reasoning`` reflects the Claude model generation.

    Scenario: a backend is built for a parametrized model and ``has_reasoning`` is
    read.

    Boundaries: no subprocess is spawned; only the capability flag is asserted.

    On failure, first check: ``has_reasoning`` must equal the parametrized
    expectation for each model.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(model=model))
    assert backend.has_reasoning is expected


async def test_claude_cli_stderr_never_leaks_to_returned_text():
    """[Unit] ai backends: stderr content is not mixed into the returned result.

    Scenario: the fake process prints a clean envelope on stdout and noise on
    stderr.

    Boundaries: the subprocess is faked; only stdout parsing is asserted.

    On failure, first check: the result must be exactly the envelope text with no
    stderr fragment.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    proc = _make_fake_process(_claude_cli_envelope("clean answer"), stderr_bytes=b"warning: noisy stderr line\n")
    with _patch_exec(proc):
        result = await backend.generate("system", _USER)
    assert result == "clean answer"
    assert "stderr" not in result


async def test_claude_cli_spawn_failure_raises_backend_error():
    """[Unit] ai backends: a spawn OSError surfaces as AIBackendError.

    Scenario: ``create_subprocess_exec`` raises ``OSError`` (e.g. the ``claude``
    binary is missing).

    Boundaries: the subprocess spawn is faked to fail; only the spawn-failure path
    is asserted.

    On failure, first check: ``generate`` must raise ``AIBackendError`` matching
    ``could not be spawned``.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=0))
    with mock.patch("asyncio.create_subprocess_exec", mock.AsyncMock(side_effect=OSError("no such binary"))):
        with pytest.raises(AIBackendError, match="could not be spawned"):
            await backend.generate("system", _USER)


async def test_claude_cli_reaps_still_running_process():
    """[Unit] ai backends: a child still running at exit is terminated (RAII).

    Scenario: the fake process reports ``returncode is None`` at context exit so the
    teardown must terminate it.

    Boundaries: the subprocess is faked; only the reap-on-exit path is asserted.

    On failure, first check: the result must parse and ``terminate`` must be called
    exactly once during teardown.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    proc = _make_fake_process(_claude_cli_envelope("done"))
    proc.returncode = None
    proc.terminate = mock.MagicMock()
    with _patch_exec(proc):
        result = await backend.generate("system", _USER)
    assert result == "done"
    proc.terminate.assert_called_once()


async def test_claude_cli_stream_skips_malformed_and_nondict_frames():
    """[Unit] ai backends: ``stream`` skips malformed and non-object NDJSON frames.

    Scenario: the fake process emits a non-JSON line, a JSON scalar, a valid text
    delta, then a ``result`` frame.

    Boundaries: the subprocess is faked; only the defensive skip paths are asserted.

    On failure, first check: only the well-formed delta must be yielded.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    lines = [
        "not valid json",
        "123",
        json.dumps(
            {
                "type": "stream_event",
                "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}},
            }
        ),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "usage": {"input_tokens": 1, "output_tokens": 1}}),
    ]
    stdout = ("\n".join(lines) + "\n").encode()
    proc = _make_fake_process(stdout)
    with _patch_exec(proc):
        tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["ok"]


async def test_claude_cli_stream_nonzero_exit_raises():
    """[Unit] ai backends: a non-zero exit at end of stream raises AIBackendError.

    Scenario: the fake process emits a clean ``result`` frame but exits with code 1.

    Boundaries: the subprocess is faked; only the stream exit-code failure path is
    asserted.

    On failure, first check: draining ``stream`` must raise ``AIBackendError``
    mentioning the exit code.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    frames = [{"type": "result", "subtype": "success", "is_error": False, "usage": {"input_tokens": 1, "output_tokens": 1}}]
    stdout = ("\n".join(json.dumps(f) for f in frames) + "\n").encode()
    proc = _make_fake_process(stdout, returncode=1)
    with _patch_exec(proc), pytest.raises(AIBackendError, match="exited with code 1"):
        async for _ in backend.stream("system", _USER):
            pass


def test_claude_cli_resolved_model_falls_back_to_default():
    """[Unit] ai backends: a non-Claude model name falls back to the CLI default.

    Scenario: ``resolved_model`` is read for a GPT-style name and a Claude name.

    Boundaries: exercises the settings property directly.

    On failure, first check: a non-Claude name must resolve to ``claude-sonnet-4-6``
    while a Claude name is returned verbatim.
    """
    assert ClaudeCliSettings(model="gpt-4o").resolved_model == "claude-sonnet-4-6"
    assert ClaudeCliSettings(model="claude-opus-4-8").resolved_model == "claude-opus-4-8"


async def test_claude_cli_structured_output_strips_code_fence():
    """[Unit] ai backends: a fenced JSON result still validates against the schema.

    Scenario: the CLI honours the schema but wraps the object in a ```json code
    fence - the common shape for this prompt-driven backend, which has no forced
    tool use - and ``generate`` is called with a schema.

    Boundaries: the subprocess is faked; only fence stripping plus schema
    validation are asserted.

    On failure, first check: the fence must be peeled before the base class
    parses, so the first attempt validates instead of burning the correction
    retry on an already-correct reply.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    payload = json.dumps({"root_cause": "uaf", "confidence": 0.8})
    proc = _make_fake_process(_claude_cli_envelope(f"```json\n{payload}\n```"))
    with _patch_exec(proc):
        result = await backend.generate("system", _USER, Hypothesis)
    assert isinstance(result, Hypothesis)
    assert result.confidence == 0.8


async def test_claude_cli_unstructured_keeps_code_fence():
    """[Unit] ai backends: a free-form reply keeps a code fence the model sent.

    Scenario: the envelope ``result`` is a fenced snippet and ``generate`` is
    called with **no** schema.

    Boundaries: the subprocess is faked; asserts the strip is scoped to schema
    requests only.

    On failure, first check: fence stripping must not apply without a schema -
    a free-form answer may legitimately be a code block, and rewriting it would
    corrupt the agent's own output.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings())
    fenced = "```c\nint *p = NULL;\n```"
    proc = _make_fake_process(_claude_cli_envelope(fenced))
    with _patch_exec(proc):
        result = await backend.generate("system", _USER)
    assert result == fenced


async def test_claude_cli_error_envelope_reports_cli_reason():
    """[Unit] ai backends: an error envelope surfaces the CLI's own reason.

    Scenario: the CLI returns ``is_error: true`` while still reporting
    ``subtype: success`` - the real shape seen when the CLI fails at the
    transport layer (usage limit, credit balance, upstream API error) - and the
    cause is carried in ``result``.

    Boundaries: the subprocess is faked; asserts only the error message content.

    On failure, first check: the raised ``AIBackendError`` must name the reason
    from ``result``; without it a transport failure is indistinguishable from a
    model failure and the operator has nothing to act on.
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=0))
    proc = _make_fake_process(
        _claude_cli_envelope("Usage limit reached. Resets at 5pm.", is_error=True, subtype="success")
    )
    with _patch_exec(proc), pytest.raises(AIBackendError, match="Usage limit reached"):
        await backend.generate("system", _USER)


async def test_claude_cli_error_reason_is_truncated_and_single_line():
    """[Unit] ai backends: an oversized error reason is capped and flattened.

    Scenario: an error envelope carries a very long multi-line ``result``.

    Boundaries: the subprocess is faked; asserts the message bound, not wording.

    On failure, first check: the message must be truncated and newline-free, so
    an error body that echoes transcript text cannot dump an incident payload
    into a log or exception (repo security §3).
    """
    backend = ClaudeCliBackend(ClaudeCliSettings(max_retries=0))
    body = "SECRET-STACK-LINE\n" * 500
    proc = _make_fake_process(_claude_cli_envelope(body, is_error=True, subtype="success"))
    with _patch_exec(proc), pytest.raises(AIBackendError) as excinfo:
        await backend.generate("system", _USER)
    message = str(excinfo.value)
    assert "\n" not in message
    assert len(message) < 500


def test_strip_code_fence_leaves_bare_and_partial_text_untouched():
    """[Unit] ai backends: only a fully wrapping code fence is stripped.

    Scenario: ``_strip_code_fence`` is given bare JSON, text that merely contains
    a fence mid-body, and a properly wrapped block.

    Boundaries: pure function; no subprocess involved.

    On failure, first check: a bare object must be returned unchanged and an
    inner fence must be preserved - stripping either would corrupt valid output.
    """
    assert _strip_code_fence('{"a": 1}') == '{"a": 1}'
    assert _strip_code_fence("prefix ```json\n{}\n```") == "prefix ```json\n{}\n```"
    assert _strip_code_fence("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    assert _strip_code_fence("```\n{\"a\": 1}\n```") == '{"a": 1}'
