# 02 — Constructor injection for all concrete agents

**Parent task:** 06.0 Agent Wiring
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 03

## Objective

Update all concrete agent subclasses (`HypothesisAgent`, `AdversarialAgent`,
`SynthesisAgent`, and any others in `aegis/core/agents/`) to use the new
`BaseAgent(router, bus)` constructor. Remove any remaining direct provider
SDK imports.

## Changes per agent

For each agent in `aegis/core/agents/`:

1. Replace `def __init__(self, ai_backend: AIAPIBackend, ...)` with
   `def __init__(self, router: ModelRouter, bus: EventBus)` — or call
   `super().__init__(router, bus)` if the subclass passes through to `BaseAgent`.

2. Replace direct `ai_backend.generate(...)` / `ai_backend.stream(...)` calls
   with `await self.reason(messages=[...], run_id=run_id)`.

3. Remove `import anthropic`, `import openai`, `import litellm`,
   `import deepseek` from every agent file.

4. Update the `role` property to return the matching key from `agents.yaml`
   (e.g. `"primary_reasoning"`, `"contradiction_finder"`).

## Affected files (verify at implementation time)

- `aegis/core/agents/hypothesis_agent.py`
- `aegis/core/agents/adversarial_agent.py`
- `aegis/core/agents/synthesis_agent.py`
- Any forensic specialist agents from Milestone 0002 that make direct API calls

## Constraints

- The `AIAPIBackend` ABC and its factory can remain in `backends/ai/` for
  backwards compatibility (other code may reference it); this task only removes
  direct usage from `agents/`.
- Each agent's `role` property must match an entry in `agents.yaml`.
- All existing agent tests must still pass — update the test fixtures to inject
  a mocked `ModelRouter` instead of a mocked `AIAPIBackend`.

## Success criteria

- [ ] No `import anthropic`, `import openai`, `import deepseek` in any file
      under `aegis/core/agents/`.
- [ ] All concrete agents call `self.reason(messages, run_id)` not a backend.
- [ ] Each agent exposes a `role` property returning the correct role string.
- [ ] Existing agent unit tests pass (fixtures updated to mock ModelRouter).
- [ ] `ruff check src/ tests/` - clean.
