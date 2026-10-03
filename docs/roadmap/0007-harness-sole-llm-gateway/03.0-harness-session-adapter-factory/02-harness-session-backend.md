# 02 — `HarnessSessionBackend` adapter

**Parent task:** 03.0 Harness Session Adapter & Factory
**State:** ⬜ Not started
**Depends on:** 01 (`HarnessSession`)
**Blocks:** Task 04.0
**Contracts:** C1, C4, C10, C12

## Objective

Implement `HarnessSessionBackend` in `backends/ai/harness_adapter.py`: the **sole
production** `AIAPIBackend`, fulfilling the retained
`generate(system_prompt, messages, output_schema) -> BaseModel | str` seam by
delegating to a `HarnessSession`.

## Design

- `HarnessSessionBackend` subclasses `_BaseAIBackend` so `generate()`, token
  accounting, and the one-retry structured-output correction path
  (`base.py:54-91`) are **inherited verbatim**. The adapter supplies only
  `_invoke()` and `stream()`.
- `_invoke(system_prompt, messages, output_schema)`:
  1. Folds `system_prompt` + `messages` into a single bounded **task** string (the
     role's seeded question + pushed pre-redacted summary + prior-turn digest, via
     the `HarnessSession` from subtask 01). The multi-turn `messages` list is
     collapsed per the per-turn re-delegation decision (subtask 01).
  2. Calls `session.run_turn(...)` → `CodeResult`.
  3. Returns `(payload, usage)` where `payload` is the parsed structured dict (when
     `output_schema` is set) or `CodeResult.content` text, and `usage` is derived
     from `CodeResult.token_estimate` (C10, subtask 04). The inherited `generate()`
     does the `output_schema.model_validate` + one-retry.
- `create_ai_backend` (`backends/ai/__init__.py`) constructs a
  `HarnessSessionBackend` and nothing else (C1). It takes the `HarnessSession`/
  factory-provided session for the role; for the shared-backend legacy call sites
  that still pass a single backend, the composition root supplies a default-role
  session (Task 04.0 removes the shared-backend assumption).
- `has_reasoning` is derived from the backing harness family where meaningful, else
  `False` — never from a deleted provider.

## Constraints

- The `AIAPIBackend` ABC / `_BaseAIBackend` seam is unchanged (C1).
- A session/backend failure is surfaced as a typed error flowing through the
  inherited validation/retry path or a loud failure — never a silent empty result
  (C12).
- No raw payload/prompt/response reaches a log sink; `SensitiveFilter` on every
  sink (C12).

## Acceptance criteria

- [ ] `HarnessSessionBackend` subclasses `_BaseAIBackend`; only `_invoke()`/
      `stream()` are supplied; `generate()`/retry is inherited (C1, C4).
- [ ] `_invoke` delegates to a `HarnessSession` and returns `(payload, usage)` with
      `usage` from `CodeResult.token_estimate` (C10).
- [ ] `create_ai_backend` constructs only `HarnessSessionBackend` (C1).
- [ ] A structured `output_schema` round-trips through the inherited validate +
      one-retry path (proven with a seeded failing-then-valid session result).
- [ ] No unredacted payload/prompt/response in any log sink (C12).
- [ ] `ruff` clean; coverage ≥90% on the adapter (ADR Coverage).
