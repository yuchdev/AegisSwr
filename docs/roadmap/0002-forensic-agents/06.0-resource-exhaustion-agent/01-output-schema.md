# 01 - Output schema (`ResourceExhaustionOutput`)

**Parent task:** 06.0 Resource Exhaustion Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0
**Blocks:** 03

## Objective

Add `ResourceExhaustionOutput` to `core/schemas.py`. The model mirrors the
existing `OSKernelOutput` shape - a list of `Hypothesis` objects plus a
`confidence_score: float` - and extends it with three domain-specific fields
that carry the resource-exhaustion specialist's unique findings.

## Files

- **Modify** `src/aegis_swr/core/schemas.py`
- **Modify** `tests/unit/test_schemas.py`

## New model

Add `ResourceExhaustionOutput` adjacent to the other specialist output models in
`core/schemas.py`, after `LogHistorianOutput` and any other forensic output
models already present:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `hypotheses` | `list[Hypothesis]` | `Field(default_factory=list)` | Same as `OSKernelOutput.hypotheses`. |
| `confidence_score` | `float` | - | Required; 0.0–1.0. |
| `exhausted_resource` | `Optional[str]` | `None` | The specific resource that was exhausted, e.g. `"Win32 handle table (limit 65535)"`, `"thread-pool worker threads (limit 64)"`, `"file descriptors (ulimit 1024)"`. Populated by the agent from both the pre-check and LLM reasoning. |
| `leak_indicators` | `list[str]` | `Field(default_factory=list)` | Textual signals of resource pressure found in the incident, e.g. `"'too many open files' at 2024-01-15T03:42Z"`, `"handle count: 62100 (threshold 60000)"`. Pre-populated by the deterministic pre-check before the LLM call; the LLM may add further entries. |
| `growth_trend` | `Optional[str]` | `None` | Free-text description of the growth pattern observed, e.g. `"handle count grows ~400/min, linear since 02:00 UTC"`, `"thread count plateaued at 512 then spiked"`. Derived from log temporal analysis. |

All `Optional[str]` fields use `Optional[str]` imported from `typing`.
`list` fields use `Field(default_factory=list)`.

## Constraints

- `Optional[T]` from `typing`; never `T | None`.
- `mypy --strict` clean after the change.
- `ruff` clean; line length 100.
- The RST-style docstring on `ResourceExhaustionOutput` must document every
  field with `:ivar:` / `:type:` entries, matching the style of `OSKernelOutput`.
- Do not alter any existing model; insertion only.

## Tests

In `tests/unit/test_schemas.py`:

- `test_resource_exhaustion_output_minimal` - construct with only `hypotheses`
  and `confidence_score`; assert `exhausted_resource is None`,
  `leak_indicators == []`, `growth_trend is None`.
- `test_resource_exhaustion_output_full` - round-trip serialize and deserialize
  a fully-populated instance (all fields non-default); assert field values
  survive the round-trip.
- `test_resource_exhaustion_output_hypotheses_list` - verify that each element
  in `hypotheses` is a valid `Hypothesis` instance with `confidence` in
  `[0.0, 1.0]`.
- `test_resource_exhaustion_output_rejects_invalid_confidence` -
  `confidence_score` outside `[0.0, 1.0]` raises `ValidationError` (add a
  field validator if not already inherited from the existing convention).

## Success criteria

- [ ] `ResourceExhaustionOutput` is importable from `aegis_swr.core.schemas`.
- [ ] All five fields have correct types and defaults as specified above.
- [ ] RST docstring covers every field.
- [ ] All four unit tests pass.
- [ ] `mypy --strict` clean; `ruff` clean.
