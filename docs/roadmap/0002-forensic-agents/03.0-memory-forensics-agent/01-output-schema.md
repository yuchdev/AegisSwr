# 01 — Output schema (`MemoryForensicsOutput`)

**Parent task:** 03.0 Memory Forensics Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0
**Blocks:** 03

## Objective

Add `MemoryForensicsOutput` to `core/schemas.py`. The model mirrors the existing
`OSKernelOutput` shape — a list of `Hypothesis` objects plus a
`confidence_score: float` — and extends it with three domain-specific fields that
carry the memory-forensics specialist's unique findings.

## Files

- **Modify** `src/aegis_swr/core/schemas.py`
- **Modify** `tests/unit/test_schemas.py`

## New model

Add `MemoryForensicsOutput` adjacent to `OSKernelOutput` in `core/schemas.py`,
after all existing output models:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `hypotheses` | `list[Hypothesis]` | `Field(default_factory=list)` | Same as `OSKernelOutput.hypotheses`. |
| `confidence_score` | `float` | — | Required; 0.0–1.0. |
| `corruption_signatures` | `list[str]` | `Field(default_factory=list)` | Fill-pattern sentinel values and other allocator-metadata tells found in the incident (e.g. `"0xBAADF00D at 0x7ffd3a20"`). Populated by the agent's deterministic pre-check before the LLM call. |
| `suspected_allocation_site` | `Optional[str]` | `None` | Function or code location suspected to be the allocation origin (e.g. `"operator new[]" in MyBuffer.cpp:42`). |
| `heap_state` | `Optional[str]` | `None` | Free-text summary of the heap/allocator state derived from metadata (e.g. `"heap header overwritten; HEAP_ENTRY size field corrupted"`). |

All `Optional[str]` fields use `Optional[str]` imported from `typing`.
`list` fields use `Field(default_factory=list)`.

## Constraints

- `Optional[T]` from `typing`; never `T | None`.
- `mypy --strict` clean after the change.
- `ruff` clean; line length 100.
- The RST-style docstring on `MemoryForensicsOutput` must document every field
  with `:ivar:` / `:type:` entries, matching the style of `OSKernelOutput`.
- Do not alter any existing model; insertion only.

## Tests

In `tests/unit/test_schemas.py`:

- `test_memory_forensics_output_minimal` — construct with only `hypotheses` and
  `confidence_score`; assert `corruption_signatures == []`,
  `suspected_allocation_site is None`, `heap_state is None`.
- `test_memory_forensics_output_full` — round-trip serialize and deserialize a
  fully-populated instance (all fields non-default); assert field values survive.
- `test_memory_forensics_output_hypotheses_list` — verify that each element in
  `hypotheses` is a valid `Hypothesis` instance with `confidence` in `[0.0, 1.0]`.
- `test_memory_forensics_output_rejects_invalid_confidence` — `confidence_score`
  outside `[0.0, 1.0]` raises `ValidationError` (add a validator if not already
  inherited from `OSKernelOutput`'s convention).

## Success criteria

- [ ] `MemoryForensicsOutput` is importable from `aegis_swr.core.schemas`.
- [ ] All four fields have correct types and defaults as specified above.
- [ ] RST docstring covers every field.
- [ ] All four unit tests pass.
- [ ] `mypy --strict` clean; `ruff` clean.
