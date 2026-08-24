# 03 — app.py composition root

**Parent task:** 06.0 Agent Wiring
**State:** ⬜ Not started
**Depends on:** 02
**Blocks:** 04

## Objective

Update `aegis/app.py` — the composition root — to construct the
`RouterConfig → LiteLLMClient → ModelRouter` chain once at startup and inject
the shared `ModelRouter` instance into all agents. One `RouterConfig`, one
`LiteLLMClient`, one `ModelRouter` for the entire pipeline run.

## Target shape

```python
# aegis/app.py — relevant section (AFTER)

from aegis.router.config import RouterConfig
from aegis.router.router import ModelRouter

def build_pipeline(config_dir: Path, bus: EventBus) -> Pipeline:
    """Construct and wire the full analysis pipeline.

    :param config_dir: Directory containing agents.yaml.
    :param bus: Shared EventBus for the pipeline run.
    :return: Configured Pipeline ready to run.
    """
    router_config = RouterConfig.from_yaml(config_dir / "agents.yaml")
    router = ModelRouter.from_config(router_config, bus)

    hypothesis_agent  = HypothesisAgent(router=router, bus=bus)
    adversarial_agent = AdversarialAgent(router=router, bus=bus)
    synthesis_agent   = SynthesisAgent(router=router, bus=bus)

    return Pipeline(
        agents=[hypothesis_agent, adversarial_agent, synthesis_agent],
        bus=bus,
    )
```

## Constraints

- `RouterConfig.from_yaml()` is called **once** — at startup, not per
  analysis run. Config is immutable after loading.
- `ModelRouter` is **shared** across all agents — one instance, not one per
  agent. This is the singleton pattern that makes the litellm isolation check
  meaningful.
- `--dry-run` flag (from Task 06.0/04) must be threaded through here: when
  `--dry-run` is set, inject a `NullClient` instead of the real `LiteLLMClient`.

## Startup error handling

`RouterConfig.from_yaml()` raises `ConfigValidationError` on startup if
`agents.yaml` is invalid or env vars are missing. This should surface as a
clear CLI error before the pipeline starts — not as a mid-run failure.

```python
from aegis.router.exceptions import ConfigValidationError

try:
    router_config = RouterConfig.from_yaml(config_dir / "agents.yaml")
except ConfigValidationError as exc:
    raise SystemExit(f"Configuration error: {exc}") from exc
```

## Success criteria

- [ ] `RouterConfig` instantiated once in `build_pipeline`.
- [ ] `ModelRouter` instantiated once and shared across all agents.
- [ ] `ConfigValidationError` surfaces as a clean startup error, not an
      unhandled exception.
- [ ] `--dry-run` wires `NullClient` instead of `LiteLLMClient`.
