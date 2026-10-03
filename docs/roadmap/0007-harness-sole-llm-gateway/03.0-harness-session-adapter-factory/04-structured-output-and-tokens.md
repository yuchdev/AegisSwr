# 04 — Structured-output parse + token lineage

**Parent task:** 03.0 Harness Session Adapter & Factory
**State:** ⬜ Not started
**Depends on:** 02 (`HarnessSessionBackend`)
**Blocks:** Task 04.0
**Contracts:** C4, C6, C10, C12

## Objective

Make the adapter's `CodeResult → output_schema` parse robust and route token
usage through `CodeResult.token_estimate` into the existing accounting, so the
deterministic consensus (C6) reads well-formed structured per-agent output and the
panel's token totals keep their meaning (C10).

## Scope

- **Structured parse.** `_invoke` extracts the structured payload from
  `CodeResult.content` (the harness session's final text). When the harness returns
  JSON wrapped in prose/markdown fences, a tolerant extraction (first balanced JSON
  object) feeds the inherited `generate()` validate step; a non-extractable result
  is returned as a raw dict/string so the inherited one-retry correction path
  (`base.py:76-91`) fires with the role's `output_schema` — the same recovery the
  network providers had. After one retry, failure raises the existing
  `AIOutputValidationError` (unchanged behaviour).
- **Token lineage (C10).** Map `CodeResult.token_estimate` (an `int`) into the
  `usage` dict `_invoke` returns, so the inherited `_accumulate`/`last_usage` and
  the orchestrator `token_tracker` (`core/orchestrator.py:_fold_turn`) are fed
  exactly as before. Where the backing harness reports split input/output (Claude
  Code real `usage`), preserve the split; where it reports a single boundary
  estimate (OpenClaude/OpenHands), attribute it to output and leave input at the
  prompt-length estimate — documented, deterministic, never a crash.
- **Determinism guard.** The parse must be a pure function of `CodeResult.content`
  (no clock/network), so a seeded session result yields a byte-identical parsed
  model — the property Task 04.0/08.0's panel-parity suite relies on (C6).

## Constraints

- No schema change to `CodeResult` (0005 C9 invariant); `token_estimate` keeps its
  name and `int` type.
- No raw content is logged on a parse failure; the error names the schema and the
  attempt count, never the payload (C12).

## Acceptance criteria

- [ ] A well-formed structured `CodeResult.content` validates into `output_schema`
      on the first attempt (C4).
- [ ] A fenced/prose-wrapped JSON result is tolerantly extracted; a non-extractable
      one drives exactly one correction retry, then raises
      `AIOutputValidationError` (unchanged behaviour).
- [ ] `CodeResult.token_estimate` flows into `last_usage`/`token_tracker`;
      `RCAReport` token totals keep their meaning (C10).
- [ ] The parse is deterministic for a seeded result (C6).
- [ ] No raw content/payload reaches a log sink on failure (C12).
- [ ] `ruff` clean; 100% branch on the parse/token-mapping helper.
