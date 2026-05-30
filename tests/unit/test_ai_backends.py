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
from aegis_swr.backends.ai.openai_provider import OpenAIBackend, _to_openai_strict_schema
from aegis_swr.config.settings import AISettings
from aegis_swr.core.exceptions import AIOutputValidationError
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
    """Async context manager mimicking anthropic ``messages.stream(...)``."""

    def __init__(self, tokens: list[str]) -> None:
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
    settings = AISettings(provider="openai", model="gpt-4o")
    with mock.patch("openai.AsyncOpenAI") as cls:
        client = mock.MagicMock()
        cls.return_value = client
        backend = OpenAIBackend(settings)
    return backend, client


_USER = [{"role": "user", "content": "analyze this"}]


# ---------------------------------------------------------------------------
# Anthropic — structured output
# ---------------------------------------------------------------------------


async def test_anthropic_structured_output_valid(
    anthropic_backend: tuple[AnthropicBackend, Any],
) -> None:
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
) -> None:
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
) -> None:
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
) -> None:
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_tool_block({"root_cause": "x"})])  # always invalid
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)
    assert client.messages.create.call_count == 2


async def test_anthropic_unstructured_returns_text(
    anthropic_backend: tuple[AnthropicBackend, Any],
) -> None:
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_text_block("hello "), _text_block("world")])
    )
    result = await backend.generate("system", _USER)
    assert result == "hello world"


async def test_anthropic_stream_yields_tokens(
    anthropic_backend: tuple[AnthropicBackend, Any],
) -> None:
    backend, client = anthropic_backend
    client.messages.stream = mock.MagicMock(return_value=_FakeStreamCtx(["a", "b", "c"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["a", "b", "c"]


async def test_anthropic_raises_when_no_tool_block(
    anthropic_backend: tuple[AnthropicBackend, Any],
) -> None:
    backend, client = anthropic_backend
    client.messages.create = mock.AsyncMock(
        return_value=_anthropic_response([_text_block("no tool here")])
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)


# ---------------------------------------------------------------------------
# OpenAI — structured output
# ---------------------------------------------------------------------------


async def test_openai_structured_output_valid(
    openai_backend: tuple[OpenAIBackend, Any],
) -> None:
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
) -> None:
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


async def test_openai_retry_then_valid(
    openai_backend: tuple[OpenAIBackend, Any],
) -> None:
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
) -> None:
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response("not json at all")
    )
    with pytest.raises(AIOutputValidationError):
        await backend.generate("system", _USER, Hypothesis)
    assert client.chat.completions.create.call_count == 2


async def test_openai_unstructured_returns_text(
    openai_backend: tuple[OpenAIBackend, Any],
) -> None:
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(
        return_value=_openai_response("plain answer")
    )
    result = await backend.generate("system", _USER)
    assert result == "plain answer"


async def test_openai_stream_yields_tokens(
    openai_backend: tuple[OpenAIBackend, Any],
) -> None:
    backend, client = openai_backend
    client.chat.completions.create = mock.AsyncMock(return_value=_openai_chunks(["x", "y"]))
    tokens = [t async for t in backend.stream("system", _USER)]
    assert tokens == ["x", "y"]


# ---------------------------------------------------------------------------
# OpenAI strict-schema adapter
# ---------------------------------------------------------------------------


def test_openai_strict_schema_sets_additional_properties_false() -> None:
    schema = _to_openai_strict_schema(Hypothesis)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())
    assert "default" not in json.dumps(schema)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_anthropic() -> None:
    with mock.patch("anthropic.AsyncAnthropic"):
        backend = create_ai_backend(AISettings(provider="anthropic"))
    assert isinstance(backend, AnthropicBackend)


def test_factory_returns_openai() -> None:
    with mock.patch("openai.AsyncOpenAI"):
        backend = create_ai_backend(AISettings(provider="openai", model="gpt-4o"))
    assert isinstance(backend, OpenAIBackend)


def test_factory_unknown_provider_raises() -> None:
    # Bypass AISettings validation to reach the factory's guard.
    fake = SimpleNamespace(provider="grok")
    with pytest.raises(ValueError, match="Unknown AI provider"):
        create_ai_backend(fake)  # type: ignore[arg-type]
