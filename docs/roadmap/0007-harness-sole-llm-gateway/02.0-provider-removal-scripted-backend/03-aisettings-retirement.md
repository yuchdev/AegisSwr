# 03 — `AISettings` retirement of provider-key fields

**Parent task:** 02.0 Direct-Provider Removal & `ScriptedAIBackend`
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** Task 03.0
**Contracts:** C1, C12, C13

## Objective

Reduce `AISettings` so it no longer carries any provider API-key field or
network-provider selector, making "Aegis holds no model API key" a settings-shape
invariant rather than just a runtime one.

## Scope

- Remove from `AISettings` the per-provider sub-settings that held keys
  (`anthropic`, `openai`, `bedrock`, `claude_cli`) and any `ANTHROPIC_API_KEY` /
  `OPENAI_API_KEY` / AWS-credential fields they sourced. The `provider` discriminator
  field is removed or reduced to a no-op legacy alias that resolves only to the
  harness adapter (Task 03.0 decides which; prefer removal if no external config
  reads it).
- Any structured-output / retry tuning that is provider-neutral and still needed
  (e.g. a max-retry count consumed by `_BaseAIBackend`) is **kept** on `AISettings`
  or migrated to the harness-adapter settings (Task 03.0) — it is not a secret and
  is not deleted blindly.
- Honour the recorded memory convention: any surviving `Optional[str]` env setting
  must treat `""` (an unset CI secret) as `None`, not crash at collection.
- Migrate every consumer of the removed fields. Grep for `settings.ai.anthropic`,
  `settings.ai.openai`, `settings.ai.bedrock`, `settings.ai.claude_cli`,
  `settings.ai.provider` and update/delete each site.

## Constraints

- No key field survives anywhere in `Settings` (C1). A `security-auditor`-style
  check: constructing `Settings()` with every provider env var unset must succeed
  and expose no key attribute.
- `Optional[T]` from `typing`; `from __future__ import annotations`; RST
  docstrings (C12).

## Acceptance criteria

- [ ] `AISettings` carries no provider API-key field and no network-provider
      selector; `ClaudeCliSettings` is gone (coordinated with subtask 02).
- [ ] Any provider-neutral tuning still needed by `_BaseAIBackend` survives,
      documented, not blind-deleted.
- [ ] Every consumer of a removed field is migrated; grep is clean.
- [ ] `Settings()` constructs with all provider env vars unset and exposes no key
      attribute (C1).
- [ ] An unset-CI-secret `""` coerces to `None`, not a construction crash (memory
      convention).
- [ ] `ruff` clean.
