"""Factory for AI backend instantiation."""
from wincrash_analyzer.backends.ai.base import AIBackendBase
from wincrash_analyzer.config import get_option


def create_ai_backend(engine: str) -> AIBackendBase:
    """
    Instantiate and return the requested AI backend.

    @param engine: The identifier of the AI engine to create.
    @return: An instance of the requested AI backend.
    @raises ValueError: If an unknown engine identifier is provided.
    """
    ai_opt = get_option("ai")
    if engine not in ai_opt.choices:
        raise ValueError(f"Unknown AI engine: {engine!r}. Valid choices are: {ai_opt.choices}")

    if engine == "gemini":
        from wincrash_analyzer.backends.ai.gemini import GeminiBackend
        return GeminiBackend()
    if engine == "openai":
        from wincrash_analyzer.backends.ai.openai import OpenAIBackend
        return OpenAIBackend()
    
    raise ValueError(f"AI engine {engine!r} is in schema but not implemented in factory.")
