# Task 02.0 — Direct-Provider Removal & `ScriptedAIBackend`

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §A.1 (delete the three direct providers), §A.2 (delete
`claude_cli_provider.py`)
**Contracts:** C1, C2, C13

## Scope

This task removes the three reasoning paths ADR 0006 collapses and stands up the
deterministic test double that replaces their offline-test coverage:

- **Delete the three direct providers.**
  `backends/ai/{anthropic,openai,aws_bedrock}_provider.py` are removed as
  selectable production backends. Aegis SWR holds **no** model API key. The
  `AIAPIBackend` ABC (`backends/base.py:22`) and the `_BaseAIBackend`
  structured-output/retry seam (`backends/ai/base.py`) are **retained** — only the
  concrete network providers are deleted.
- **Delete `claude_cli_provider.py`.** Its one legitimate use — "Claude Code as
  just an LLM, agentic loop stripped" — is re-expressed as a **no-tools persona**
  of the existing `claude_code` backend (`allowed_tools=""`). This removes the
  duplicate wiring of the `claude` binary and the illegal reach into
  `aegis_swr.claude_code.process` internals (`_extract_assistant_text`,
  `_extract_usage`). `ClaudeCliSettings` is deleted; `ClaudeCodeSettings` is the
  one Claude-Code config surface.
- **Retire `create_ai_backend`'s network branches.** The factory
  (`backends/ai/__init__.py:20`) stops constructing any network provider. (It is
  rewired to construct the harness adapter in Task 03.0; this task reduces it to a
  no-network state and removes the deleted imports.)
- **No escape hatch.** No `AEGIS_ALLOW_DIRECT_LLM` is introduced — a dev back-door
  to a direct provider would re-open exactly the key-holding posture this decision
  removes (ADR §A.1, Alternatives).
- **`ScriptedAIBackend` test double.** A single deterministic `ScriptedAIBackend`
  replaces the deleted network providers for unit tests: it needs no key, reaches
  no provider, and covers the prior unit coverage (C2).

> The harness-backed adapter that becomes the *sole production* `AIAPIBackend`
> lives in [Task 03.0](/docs/roadmap/0007-harness-sole-llm-gateway/03.0-harness-session-adapter-factory/README.md).
> This task leaves `create_ai_backend` in a deliberately no-network interim state
> (raising a clear "no production backend wired yet" error until 03.0 lands, or,
> if 02.0/03.0 land together, 03.0 supplies the adapter branch). The ordering is
> captured in the milestone dependency graph.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Delete the three direct providers + factory branches](01-delete-direct-providers.md) | ⬜ Not started | 04, 03.0 |
| 02 | [Delete `claude_cli_provider.py`; no-tools `claude_code` persona](02-delete-claude-cli-persona.md) | ⬜ Not started | 03.0 |
| 03 | [`AISettings` retirement of provider-key fields](03-aisettings-retirement.md) | ⬜ Not started | 03.0 |
| 04 | [`ScriptedAIBackend` deterministic double](04-scripted-ai-backend.md) | ⬜ Not started | 04.0, 08.0 |

Subtasks 01, 02, 03 are independent deletions/edits and may proceed in parallel.
Subtask 04 (the double) depends on none of them structurally but is co-landed so
the unit suite stays green through the deletions.

## Contracts touched

- **C1** — the retained-seam / sole-adapter posture; this task performs the
  deletions C1 depends on.
- **C2** — `ScriptedAIBackend` is defined here.
- **C13** — the import bans (`anthropic`/`openai`/`boto3`/`claude_cli_provider`)
  become true after this task; the grep gate is wired in Task 10.0 and the pytest
  mirror in Task 08.0.

## Key constraints

- The retained `AIAPIBackend` ABC and `_BaseAIBackend` seam must **not** change
  shape — downstream `Orchestrator`/`resolve_panel` injection types are stable (C1).
- `ScriptedAIBackend` must subclass `_BaseAIBackend` so it inherits the exact
  `generate()`/token/one-retry semantics; it only supplies `_invoke()` and
  `stream()` from a seeded script (C2).
- No deleted provider's behaviour is silently re-homed into a kept module; the
  only survivor of the `claude_cli` path is the empty-allowlist `claude_code`
  persona (C13).

## Files created or modified by this task

```
src/aegis_swr/
├── backends/ai/
│   ├── anthropic_provider.py     ← DELETED
│   ├── openai_provider.py        ← DELETED
│   ├── aws_bedrock_provider.py   ← DELETED
│   ├── claude_cli_provider.py    ← DELETED
│   ├── __init__.py               ← modified: no network-provider branches/imports
│   └── scripted.py               ← NEW: ScriptedAIBackend (subtask 04)
├── claude_code/
│   └── config.py                 ← modified: document the no-tools persona (allowed_tools="")
└── config/
    └── settings.py               ← modified: AISettings loses provider-key fields; ClaudeCliSettings removed

tests/unit/backends/ai/
├── test_scripted.py              ← NEW (subtask 04)
└── (deleted provider tests re-pointed to the double / removed)
```
