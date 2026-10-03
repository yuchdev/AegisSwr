# 01 — Delete the three direct providers + factory branches

**Parent task:** 02.0 Direct-Provider Removal & `ScriptedAIBackend`
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 04 (this task); Task 03.0
**Contracts:** C1, C13

## Objective

Remove `backends/ai/{anthropic,openai,aws_bedrock}_provider.py` as selectable
production backends and strip their construction from `create_ai_backend`, so
Aegis SWR no longer makes a direct provider API call and holds no model API key —
while keeping the `AIAPIBackend` ABC and `_BaseAIBackend` seam intact.

## Scope

- Delete `backends/ai/anthropic_provider.py` (`AnthropicBackend`),
  `backends/ai/openai_provider.py` (`OpenAIBackend`), and
  `backends/ai/aws_bedrock_provider.py` (`AwsBedrockBackend`).
- In `backends/ai/__init__.py`, remove the three provider imports and the
  `settings.provider == "anthropic" | "openai" | "bedrock"` branches of
  `create_ai_backend`. Remove them from `__all__`.
- Leave the factory in a **no-network interim state**: constructing any backend
  other than the harness adapter raises a clear error (e.g. "no production LLM
  backend wired yet; Task 03.0 supplies the harness adapter"), never silently
  falling back to a provider. If this subtask is co-landed with Task 03.0, the
  adapter branch is added there; this subtask only performs the removal.
- Confirm no remaining module under `src/aegis_swr/` imports `anthropic`,
  `openai`, or `boto3` after the deletion (the grep gate is formalised in Task
  10.0; verify manually here).
- The `AIAPIBackend` ABC (`backends/base.py`) and `_BaseAIBackend`
  (`backends/ai/base.py`) are **not** modified — they remain the retained seam (C1).

## Constraints

- No provider's logic is re-homed; the deletion is clean. Prompt-caching or
  model-name resolution that lived only in a deleted provider goes with it (the
  harness owns model selection now).
- No `AEGIS_ALLOW_DIRECT_LLM` or any dev flag is added (ADR §A.1, Alternatives).

## Acceptance criteria

- [ ] The three provider modules are deleted; their classes are gone from
      `backends/ai/__init__.py` `__all__`.
- [ ] `create_ai_backend` constructs no network provider and raises a clear error
      (or defers to the Task 03.0 adapter branch) rather than falling back.
- [ ] No `import anthropic`, `import openai`, or `import boto3` remains anywhere in
      `src/aegis_swr/` (C13).
- [ ] `AIAPIBackend` / `_BaseAIBackend` are unchanged (C1).
- [ ] `ruff` clean; the unit suite is green once subtask 04's double is in place.
