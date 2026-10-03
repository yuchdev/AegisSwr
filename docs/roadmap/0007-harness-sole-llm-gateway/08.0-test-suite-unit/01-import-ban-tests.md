# 01 — Grep/import-ban tests

**Parent task:** 08.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** Task 02.0
**Contracts:** C1, C13

## Objective

The pytest mirror of the CI grep gate (Task 10.0): assert the sole-gateway import
bans hold, with a self-test proving the guard turns red on a re-introduced import.

## Scope (`tests/unit/backends/ai/test_import_bans.py`)

- Assert no module under `src/aegis_swr/` contains an `import anthropic`,
  `import openai`, or `import boto3` statement (import-statement-aware, so a
  docstring mention does not trip it — mirror the Milestone 0004 `litellm`/`grpc`
  isolation test).
- Assert no module imports `aegis_swr.backends.ai.claude_cli_provider` (deleted).
- Assert `create_ai_backend` constructs only `HarnessSessionBackend` — no
  provider-name branch remains (introspect the factory / assert the only returned
  type).
- Assert `backends/ai/scripted.py` (`ScriptedAIBackend`) is never constructed by any
  production composition path (test-only, C2).
- **Self-test:** drop a probe `import openai` into a temp module path, assert the
  guard flags it, remove it — proving the guard turns red on a real violation (the
  0004 pattern).

## Acceptance criteria

- [ ] No `anthropic`/`openai`/`boto3` import anywhere in `src/aegis_swr/` (C13).
- [ ] No `claude_cli_provider` import anywhere (C13).
- [ ] `create_ai_backend` returns only `HarnessSessionBackend` (C1).
- [ ] `ScriptedAIBackend` is not constructed by production code (C2).
- [ ] The guard self-test proves it turns red on a re-introduced import.
- [ ] Import-statement-aware (docstring mentions do not trip it).
