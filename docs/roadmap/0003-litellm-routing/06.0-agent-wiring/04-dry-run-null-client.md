# 04 — NullClient for `--dry-run`

**Parent task:** 06.0 Agent Wiring
**State:** ⬜ Not started
**Depends on:** 03.0/01 (CompletionRequest/CompletionResponse)
**Blocks:** 05.0/05 (integration tests use it), 03 (app.py wires it)

## Objective

Implement `NullClient` in `aegis/router/null_client.py` — a drop-in
replacement for `LiteLLMClient` that returns a fixed response without making
any API calls. Used when `--dry-run` is passed on the CLI so the full pipeline
can execute in CI without API keys.

## Implementation

```python
# aegis/router/null_client.py
from __future__ import annotations
from aegis.router.client import CompletionRequest, CompletionResponse


class NullClient:
    """Fake LiteLLMClient for --dry-run mode.

    Returns a synthetic response for any request. No API key or network
    access required.

    :param content: The fixed text content to return in every response.
    """

    def __init__(self, content: str = "[dry-run]") -> None:
        self._content = content

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Return a synthetic CompletionResponse. Never raises RouterException.

        :param request: Ignored except for model name.
        :return: CompletionResponse with fixed content, zero tokens and cost.
        """
        return CompletionResponse(
            model_used=request.model,
            content=self._content,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
            cost_usd=0.0,
        )
```

## CLI integration

```python
# aegis/app.py — build_pipeline with --dry-run

def build_pipeline(
    config_dir: Path,
    bus: EventBus,
    *,
    dry_run: bool = False,
) -> Pipeline:
    router_config = RouterConfig.from_yaml(config_dir / "agents.yaml")

    if dry_run:
        from aegis.router.null_client import NullClient
        client = NullClient()
    else:
        from aegis.router.client import LiteLLMClient
        client = LiteLLMClient(router_config.providers)

    router = ModelRouter(config=router_config, client=client, bus=bus)
    ...
```

## Constraints

- `NullClient` must implement the same `complete()` interface as `LiteLLMClient`
  (duck typing — no shared ABC required, but the signature must match).
- No `import litellm` in `null_client.py`.
- `--dry-run` must be checked **before** `RouterConfig.from_yaml()` — the
  config must still be valid even in dry-run mode (it validates the YAML
  schema, not the API keys).

## Success criteria

- [ ] `NullClient.complete()` returns a `CompletionResponse` with
      `content="[dry-run]"`, `input_tokens=0`, `output_tokens=0`,
      `cost_usd=0.0`, `latency_ms=0.0`.
- [ ] `python -m aegis.app --dry-run` completes the full pipeline without
      any API keys set.
- [ ] `NullClient` has no `import litellm`.
- [ ] Unit test: `test_dry_run_null_client_returns_fixed_response()`.
