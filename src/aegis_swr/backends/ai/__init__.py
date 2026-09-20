"""AI backend factory"""
from __future__ import annotations

from aegis_swr.backends.ai.anthropic_provider import AnthropicBackend
from aegis_swr.backends.ai.aws_bedrock_provider import AwsBedrockBackend
from aegis_swr.backends.ai.claude_cli_provider import ClaudeCliBackend
from aegis_swr.backends.ai.openai_provider import OpenAIBackend
from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import AISettings

__all__ = [
    "AnthropicBackend",
    "AwsBedrockBackend",
    "ClaudeCliBackend",
    "OpenAIBackend",
    "create_ai_backend",
]


def create_ai_backend(settings: AISettings) -> AIAPIBackend:
    """Construct the AI backend named by ``settings.provider``.

    The matching provider sub-config is resolved (and merged with any per-model
    override via :meth:`~aegis_swr.config.settings.ProviderSettingsBase.for_model`)
    and passed to the backend, so each backend receives only its own typed
    settings rather than the whole :class:`AISettings`.
    """
    if settings.provider == "anthropic":
        return AnthropicBackend(settings.anthropic.for_model())
    if settings.provider == "openai":
        return OpenAIBackend(settings.openai.for_model())
    if settings.provider == "bedrock":
        return AwsBedrockBackend(settings.bedrock.for_model())
    if settings.provider == "claude_cli":
        return ClaudeCliBackend(settings.claude_cli.for_model())
    raise ValueError(f"Unknown AI provider: {settings.provider!r}")
