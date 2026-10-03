# 04 — `ScriptedAIBackend` deterministic double

**Parent task:** 02.0 Direct-Provider Removal & `ScriptedAIBackend`
**State:** ⬜ Not started
**Depends on:** none (co-landed with the deletions to keep the suite green)
**Blocks:** Task 04.0 (panel parity), Task 08.0 (unit suite)
**Contracts:** C2, C6, C12

## Objective

Provide a single deterministic `ScriptedAIBackend` (`backends/ai/scripted.py`)
that replaces the deleted network providers for unit tests — reaching no provider,
needing no key, and preserving the exact `generate()`/token/one-retry semantics by
subclassing `_BaseAIBackend`.

## Design

```python
class ScriptedAIBackend(_BaseAIBackend[ScriptedSettings]):
    """Deterministic, offline AIAPIBackend double for unit tests (C2).

    Subclasses _BaseAIBackend so generate(), token accounting, and the one-retry
    structured-output correction path are inherited verbatim; only _invoke() and
    stream() are supplied, answering from a pre-seeded script of
    (matcher -> response) entries. Never selectable in a production composition
    path; reaches no provider and needs no API key.
    """
```

- The script is a list/ordered map of `(matcher, response)` where `matcher`
  inspects `(system_prompt, messages, output_schema)` and `response` is either a
  raw string (no-schema path) or a dict/JSON string that validates against the
  supplied `output_schema`. A default fallthrough response and a "fail once then
  succeed" entry are supported so the inherited one-retry correction path
  (`base.py:76-91`) can be exercised.
- `_invoke()` returns `(payload, usage)` exactly as the ABC requires; `usage` is
  seeded per entry (default a small fixed `{"input_tokens", "output_tokens"}`) so
  token-accounting assertions are deterministic.
- `stream()` yields the response text in fixed chunks for the streaming seam.
- It is importable only from tests (or a clearly test-scoped module); it is
  **never** registered by `create_ai_backend`. A guard test asserts no production
  composition path constructs it.

## Why this shape

Milestone 0004/0005 proved the panel's deterministic arbitration depends only on
the **structured** per-agent output (C6). Seeding `ScriptedAIBackend` with
structured JSON matching each agent's `output_schema` lets Task 04.0/08.0 prove
panel parity — identical weights, one-arbiter invariant, and `consensus.py` output
— entirely offline, which is exactly the coverage the deleted network providers'
mocks used to carry.

## Acceptance criteria

- [ ] `ScriptedAIBackend` subclasses `_BaseAIBackend`; `generate()`/token/one-retry
      semantics are inherited unchanged (C2).
- [ ] It answers from a seeded `(matcher -> response)` script; no network, no key.
- [ ] A seeded "invalid once, then valid" entry drives the inherited one-retry
      correction path and the test asserts the retry happened.
- [ ] Token usage is deterministic and flows through `last_usage`.
- [ ] A guard test asserts `create_ai_backend` never constructs it (test-only, C2).
- [ ] It validates structured responses against real agent `output_schema`s used
      by the Task 04.0 parity suite (C6).
- [ ] `ruff` clean; RST docstrings; `Optional[T]` not `T | None` (C12).
