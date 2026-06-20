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
from aegis_swr.config.settings import AISettings
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
    settings = AISettings(provider="anthropic", model="claude-sonnet-4-6")
    with mock.patch("anthropic.AsyncAnthropic") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = AnthropicBackend(settings)
    return backend, client


@pytest.fixture
def openai_backend() -> tuple[OpenAIBackend, Any]:
    settings = AISettings(provider="openai", model="gpt-5.4")
    with mock.patch("openai.AsyncOpenAI") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = OpenAIBackend(settings)
    return backend, client


@pytest.fixture
def bedrock_backend(monkeypatch: pytest.MonkeyPatch) -> tuple[AwsBedrockBackend, Any]:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-bearer-token")
    settings = AISettings(provider="bedrock")
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
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_text_block("hello "), _text_block("world")])
    )
    result = await backend.generate("system", _USER)
    assert result == "hello world"


async def test_anthropic_stream_yields_tokens(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
    backend, client = anthropic_backend
    client.messages.stream = mock.MagicMock(return_value=_FakeStreamCtx(["a", "b", "c"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_anthropic_raises_when_no_tool_block(
    anthropic_backend: tuple[AnthropicBackend, Any],
):
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
    settings = AISettings(provider="openai", model="gpt-4o", temperature=0.2, max_tokens=4096)
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
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response("plain answer")
    )
    result = await backend.generate("system", _USER)
    assert result == "plain answer"


async def test_openai_stream_yields_tokens(
    openai_backend: tuple[OpenAIBackend, Any],
):
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(return_value=_openai_chunks(["x", "y"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["x", "y"]


# ---------------------------------------------------------------------------
# OpenAI strict-schema adapter
# ---------------------------------------------------------------------------


def test_openai_strict_schema_sets_additional_properties_false():
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
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(return_value=_bedrock_text_response("no tool here"))
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)


async def test_bedrock_unstructured_returns_text(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    backend, client = bedrock_backend
    client.converse = mock.MagicMock(
        return_value=_bedrock_text_response("hello world")
    )
    result = await backend.generate("system", _USER)
    assert result == "hello world"


async def test_bedrock_stream_yields_tokens(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
    backend, client = bedrock_backend
    client.converse_stream = mock.MagicMock(
        return_value=_bedrock_stream_response(["a", "b", "c"])
    )
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_bedrock_client_error_becomes_backend_error(
    bedrock_backend: tuple[AwsBedrockBackend, Any],
):
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
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-token")
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        AwsBedrockBackend(AISettings(provider="bedrock"))
    client.meta.events.register.assert_called_once()
    event_name = client.meta.events.register.call_args.args[0]
    assert event_name == "before-send.bedrock-runtime.*"


def test_bedrock_no_bearer_hook_without_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    client = mock.MagicMock()
    session = mock.MagicMock()
    session.client.return_value = client
    with mock.patch("boto3.Session", return_value=session):
        AwsBedrockBackend(AISettings(provider="bedrock"))
    client.meta.events.register.assert_not_called()


async def test_bedrock_thinking_enabled_for_free_form(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    settings = AISettings(provider="bedrock")
    settings.bedrock.thinking_budget_tokens = 2048
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
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = AnthropicBackend(AISettings(provider="anthropic", model=model))
    assert backend.has_reasoning is expected


def test_openai_has_reasoning_always_false(openai_backend: tuple[OpenAIBackend, Any]):
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
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    settings = AISettings(provider="bedrock")
    settings.bedrock.model_id = model_id
    session = mock.MagicMock()
    session.client.return_value = mock.MagicMock()
    with mock.patch("boto3.Session", return_value=session):
        backend = AwsBedrockBackend(settings)
    assert backend.has_reasoning is expected


def test_mock_backend_has_reasoning_defaults_false():
    from tests.unit.fixtures.mock_ai_backend import MockAIBackend

    assert MockAIBackend().has_reasoning is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_anthropic():
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = create_ai_backend(AISettings(provider="anthropic"))
    assert isinstance(backend, AnthropicBackend)


def test_factory_returns_openai():
    with mock.patch("openai.AsyncOpenAI"):
        backend = create_ai_backend(AISettings(provider="openai", model="gpt-5.4"))
    assert isinstance(backend, OpenAIBackend)


def test_factory_returns_bedrock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    with mock.patch("boto3.Session"):
        backend = create_ai_backend(AISettings(provider="bedrock"))
    assert isinstance(backend, AwsBedrockBackend)


def test_factory_unknown_provider_raises():
    # Bypass AISettings validation to reach the factory's guard.
    fake = SimpleNamespace(provider="grok")
    with pytest.raises(ValueError, match="Unknown AI provider"):
        create_ai_backend(fake)  # type: ignore[arg-type]
