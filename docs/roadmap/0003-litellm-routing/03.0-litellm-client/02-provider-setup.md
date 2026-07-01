# 02 - `_configure_providers()` - provider auth setup

**Parent task:** 03.0 LiteLLM Client
**State:** ⬜ Not started
**Depends on:** 01, 02.0/01 (ProviderConfig)
**Blocks:** 03

## Objective

Implement `LiteLLMClient.__init__()` and its private
`_configure_providers()` method. This is called once at construction time
and sets LiteLLM's module-level API keys and base URLs for each provider.

## Implementation

```python
class LiteLLMClient:
    """Async wrapper around litellm.acompletion.

    This is the only class in Aegis SWR that imports litellm.
    All litellm exceptions are normalized to RouterException before leaving
    this class.

    :param provider_configs: Mapping of provider name to ProviderConfig.
    """

    def __init__(self, provider_configs: dict[str, ProviderConfig]) -> None:
        self._configure_providers(provider_configs)

    def _configure_providers(
        self,
        providers: dict[str, ProviderConfig],
    ) -> None:
        """Set litellm API keys and base URLs for each configured provider.

        Called once at construction; not called again during the lifetime
        of this object.

        LiteLLM uses module-level globals for provider credentials, so this
        method mutates litellm state. Subsequent calls with different providers
        would overwrite previous state - the singleton pattern in app.py
        (one ModelRouter, one LiteLLMClient) prevents conflicts.

        For self_hosted providers (OpenAI-compatible vLLM), the base_url
        is used to set a custom endpoint; the model string in CompletionRequest
        should use the "openai/" prefix (resolved by ModelRouter from the
        "self_hosted/" YAML prefix).
        """
        ...
```

## LiteLLM configuration mapping

| Provider key  | LiteLLM config                                     |
|---------------|----------------------------------------------------|
| `anthropic`   | `litellm.anthropic_key = config.api_key`           |
| `deepseek`    | `litellm.deepseek_key = config.api_key`; set custom base_url via `litellm.api_base` override per call (or via environment) |
| `self_hosted` | Uses OpenAI-compatible endpoint; set `litellm.api_base` + key for the `openai/` prefix |

> Verify exact LiteLLM API for per-provider base_url override at implementation
> time - the module-level API may differ across LiteLLM versions. The pattern
> is to use `litellm.custom_provider_map` or pass `api_base` in the completion
> call. Consult LiteLLM docs via context7.

## Constraints

- `_configure_providers` is called exactly once per `LiteLLMClient` instance.
- No credentials are logged or stored as instance attributes (only passed
  through to LiteLLM; the `SensitiveFilter` covers loguru outputs).

## Success criteria

- [ ] `LiteLLMClient.__init__` calls `_configure_providers(provider_configs)`.
- [ ] `_configure_providers` configures LiteLLM for `anthropic`, `deepseek`,
      and `self_hosted` provider keys.
- [ ] No credentials appear in any log output (verified by SensitiveFilter).
