"""Unit tests for the Anthropic and OpenAI backends using mocked SDK clients.

No network access: the SDK client classes are patched so __init__ never needs a
real API key and every response is fabricated.
"""

from __future__ import annotations

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
from aegis_swr.backends.ai.openai_provider import OpenAIBackend, _to_openai_strict_schema
from aegis_swr.config.settings import (
    AISettings,
    AnthropicSettings,
    BedrockSettings,
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
