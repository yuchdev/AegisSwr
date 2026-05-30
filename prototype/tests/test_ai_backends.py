"""Tests for AI backends: factory, truncation logic, and error handling."""
import os
import pytest
from unittest.mock import MagicMock, patch

from wincrash_analyzer.backends.ai.factory import create_ai_backend
from wincrash_analyzer.backends.ai.base import AIBackendBase
from wincrash_analyzer.backends.ai.gemini import GeminiBackend
from wincrash_analyzer.backends.ai.openai import OpenAIBackend
from wincrash_analyzer.core.exceptions import AIBackendError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _load_asset(filename: str) -> str:
    with open(os.path.join(ASSETS_DIR, filename)) as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


def test_factory_returns_gemini_backend():
    backend = create_ai_backend("gemini")
    assert isinstance(backend, AIBackendBase)
    assert isinstance(backend, GeminiBackend)


def test_factory_returns_openai_backend():
    backend = create_ai_backend("openai")
    assert isinstance(backend, AIBackendBase)
    assert isinstance(backend, OpenAIBackend)


def test_factory_raises_for_unknown_engine():
    with pytest.raises(ValueError, match="Unknown AI engine"):
        create_ai_backend("unknown_engine")


# ---------------------------------------------------------------------------
# BaseAIBackend: get_api_key
# ---------------------------------------------------------------------------


def test_get_api_key_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "secret123")
    backend = create_ai_backend("openai")
    assert backend.get_api_key("TEST_KEY") == "secret123"


def test_get_api_key_returns_none_when_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    backend = create_ai_backend("openai")
    assert backend.get_api_key("MISSING_KEY") is None


# ---------------------------------------------------------------------------
# OpenAI: _smart_truncate
# ---------------------------------------------------------------------------


def test_smart_truncate_short_input_unchanged():
    backend = OpenAIBackend()
    short = "A" * 5_000
    assert backend._smart_truncate(short) == short


def test_smart_truncate_exactly_threshold_unchanged():
    backend = OpenAIBackend()
    data = "B" * 10_000
    assert backend._smart_truncate(data) == data


def test_smart_truncate_long_input_keeps_head_and_tail():
    backend = OpenAIBackend()
    head = "H" * 5_000
    middle = "M" * 3_000
    tail = "T" * 5_000
    long_data = head + middle + tail
    result = backend._smart_truncate(long_data)
    assert result.startswith(head)
    assert result.endswith(tail)
    assert "[... middle section truncated ...]" in result
    assert "M" not in result


def test_smart_truncate_preserves_stack_text_section():
    """The realistic_trace.txt asset is short enough to pass through unchanged."""
    trace = _load_asset("realistic_trace.txt")
    backend = OpenAIBackend()
    result = backend._smart_truncate(trace)
    # Asset is smaller than the threshold – must be preserved verbatim.
    assert result == trace
    assert "STACK_TEXT" in result
    assert "Symbol search path" in result


def test_smart_truncate_drops_middle_symbol_noise():
    """For a trace exceeding 10k chars, middle symbol-search lines are dropped."""
    backend = OpenAIBackend()
    # Build a synthetic trace: exception header + symbol noise + stack frames
    header = "EXCEPTION_CODE: 0xc0000005 " + "A" * (5_000 - 28)
    noise = "\nSymbol not found: " + "N" * 3_000
    stack = "\nSTACK_TEXT:\n" + "S" * 4_987  # tail ends with stack data
    long_trace = header + noise + stack
    assert len(long_trace) > 10_000
    result = backend._smart_truncate(long_trace)
    assert "EXCEPTION_CODE" in result
    assert "STACK_TEXT" in result
    assert "Symbol not found" not in result


# ---------------------------------------------------------------------------
# GeminiBackend: missing API key raises AIBackendError
# ---------------------------------------------------------------------------


def test_gemini_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    backend = GeminiBackend()
    with pytest.raises(AIBackendError, match="Gemini Key Missing"):
        backend.analyze("some stack trace")


# ---------------------------------------------------------------------------
# OpenAIBackend: missing API key raises AIBackendError
# ---------------------------------------------------------------------------


def test_openai_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    backend = OpenAIBackend()
    with pytest.raises(AIBackendError, match="OpenAI Key Missing"):
        backend.analyze("some stack trace")


# ---------------------------------------------------------------------------
# GeminiBackend: mocked successful response
# ---------------------------------------------------------------------------


def test_gemini_analyze_returns_model_text(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")

    mock_response = MagicMock()
    mock_response.text = "## Root Cause\nNull pointer dereference."

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response

    with patch("wincrash_analyzer.backends.ai.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = mock_model
        backend = GeminiBackend()
        result = backend.analyze("0xc0000005 Access Violation")

    assert result == "## Root Cause\nNull pointer dereference."
    mock_genai.configure.assert_called_once_with(api_key="fake-gemini-key")


def test_gemini_analyze_wraps_sdk_exception(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key")

    mock_model = MagicMock()
    mock_model.generate_content.side_effect = RuntimeError("network error")

    with patch("wincrash_analyzer.backends.ai.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = mock_model
        backend = GeminiBackend()
        with pytest.raises(AIBackendError, match="Gemini API Failure"):
            backend.analyze("stack trace")


# ---------------------------------------------------------------------------
# OpenAIBackend: mocked successful response
# ---------------------------------------------------------------------------


def test_openai_analyze_returns_message_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")

    mock_message = MagicMock()
    mock_message.content = "## RCA\nUse-after-free in heap allocator."

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("wincrash_analyzer.backends.ai.openai.OpenAI", return_value=mock_client):
        backend = OpenAIBackend()
        result = backend.analyze("0xc0000005 Access Violation")

    assert result == "## RCA\nUse-after-free in heap allocator."


def test_openai_analyze_wraps_sdk_exception(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("timeout")

    with patch("wincrash_analyzer.backends.ai.openai.OpenAI", return_value=mock_client):
        backend = OpenAIBackend()
        with pytest.raises(AIBackendError, match="OpenAI API Failure"):
            backend.analyze("stack trace")


# ---------------------------------------------------------------------------
# OpenAIBackend: 429 / rate-limit scenario logged and re-raised
# ---------------------------------------------------------------------------


def test_openai_analyze_includes_assumption(monkeypatch):
    from wincrash_analyzer.backends.ai.openai import OpenAIBackend
    monkeypatch.setenv("OPENAI_API_KEY", "fake_key")
    
    mock_client = MagicMock()
    monkeypatch.setattr("wincrash_analyzer.backends.ai.openai.OpenAI", lambda **k: mock_client)
    
    backend = OpenAIBackend()
    backend.analyze("trace", assumption="user theory")
    
    messages = mock_client.chat.completions.create.call_args[1]["messages"]
    user_msg = messages[1]["content"]
    assert "user theory" in user_msg
    assert "User Assumption:" in user_msg

def test_gemini_analyze_includes_assumption(monkeypatch):
    from wincrash_analyzer.backends.ai.gemini import GeminiBackend
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key")
    
    mock_model = MagicMock()
    monkeypatch.setattr("google.generativeai.GenerativeModel", lambda *a, **k: mock_model)
    monkeypatch.setattr("google.generativeai.configure", lambda **k: None)
    
    backend = GeminiBackend()
    backend.analyze("trace", assumption="user theory")
    
    user_content = mock_model.generate_content.call_args[0][0]
    assert "user theory" in user_content
    assert "Additional User Context/Assumption:" in user_content

def test_openai_rate_limit_raises_ai_backend_error(monkeypatch):
    """A 429-equivalent error from the SDK is wrapped in AIBackendError."""
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("429 Too Many Requests")

    with patch("wincrash_analyzer.backends.ai.openai.OpenAI", return_value=mock_client):
        backend = OpenAIBackend()
        with pytest.raises(AIBackendError):
            backend.analyze("stack trace")
