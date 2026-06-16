"""AI backend factory"""
from __future__ import annotations

from aegis_swr.backends.ai.anthropic_provider import AnthropicBackend
from aegis_swr.backends.ai.aws_bedrock_provider import AwsBedrockBackend
from aegis_swr.backends.ai.openai_provider import OpenAIBackend
from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import AISettings

__all__ = [
    "AnthropicBackend",
    "AwsBedrockBackend",
    "OpenAIBackend",
    "create_ai_backend",
]


def create_ai_backend(settings: AISettings) -> AIAPIBackend:
    """Construct the AI backend named by ``settings.provider``"""
    if settings.provider == "anthropic":
        return AnthropicBackend(settings)
    if settings.provider == "openai":
        return OpenAIBackend(settings)
    if settings.provider == "bedrock":
        return AwsBedrockBackend(settings)
    raise ValueError(f"Unknown AI provider: {settings.provider!r}")
