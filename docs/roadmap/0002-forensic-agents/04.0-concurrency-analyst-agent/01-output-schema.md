# 01 — Output schema (`ConcurrencyAnalystOutput`)

**Parent task:** 04.0 Concurrency Analyst Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0 (Extensible Panel — `BaseAgent` ClassVars and data-driven consensus in place)
**Blocks:** 03

## Objective

Add `ConcurrencyAnalystOutput` to `core/schemas.py`, mirroring the shape of
`OSKernelOutput` (list of `Hypothesis` + `confidence_score: float`) and
extending it with the three concurrency-domain fields required by the agent's
specialism. Implements contract **C6**.

## Files

- **Modify** `src/aegis_swr/core/schemas.py`

## Schema definition

`ConcurrencyAnalystOutput` is a Pydantic `BaseModel` placed immediately after
`OSKernelOutput` in `core/schemas.py`, in the "Agent turn types" section.

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hypotheses` | `list[Hypothesis]` | `Field(default_factory=list)` | Ordered list of concurrency hypotheses (mirrors `OSKernelOutput`). |
| `confidence_score` | `float` | — (required) | Overall confidence in 0.0–1.0; the agent must always populate this. |
| `wait_chain` | `list[str]` | `Field(default_factory=list)` | Ordered sequence of thread/lock identifiers forming the detected wait chain, e.g. `["Thread-12 (holds lock A, waits B)", "Thread-7 (holds lock B, waits A)"]`. May be pre-populated by the deterministic pre-check before the LLM call. |
| `lock_order_inversions` | `list[str]` | `Field(default_factory=list)` | Human-readable descriptions of observed lock-acquisition order inversions, e.g. `["MutexA acquired before MutexB in module foo.cpp:142, reversed in bar.cpp:88"]`. |
| `suspected_race` | `Optional[str]` | `None` | Free-text description of the suspected race condition or TOCTOU window, if identified. `None` when no race is suspected. |

### Docstring requirements

The class docstring must follow RST style (`:ivar field: description`) and
describe the purpose of each field. Match the density of the `OSKernelOutput`
docstring already in `core/schemas.py`.

### Placement in `core/schemas.py`

Insert directly after the closing line of `OSKernelOutput`. Precede it with
the section comment pattern already used (no new section header needed — it is
part of "Agent output models").

## Constraints

- `Optional[str]` from `typing`; never `str | None`.
- All list fields use `Field(default_factory=list)`.
- `confidence_score` has no default — callers must supply it; Pydantic will
  raise `ValidationError` if omitted, which is the intended guard.
- `mypy --strict` clean; `ruff` clean.
- No changes to `Hypothesis`, `OSKernelOutput`, or any existing model.

## Tests

**Unit** (`tests/unit/test_schemas.py` — extend the existing file):

- `test_concurrency_analyst_output_minimal` — construct with only
  `hypotheses=[]` and `confidence_score=0.5`; assert `wait_chain == []`,
  `lock_order_inversions == []`, `suspected_race is None`.
- `test_concurrency_analyst_output_full` — construct with all fields populated;
  assert round-trip through `model_dump()` / `model_validate()` is lossless.
- `test_concurrency_analyst_output_missing_confidence_raises` — omitting
  `confidence_score` raises `ValidationError`.
- `test_concurrency_analyst_output_optional_race_none` — `suspected_race=None`
  serialises as `null` in JSON (`model_dump_json()`).

## Success criteria

- [ ] `ConcurrencyAnalystOutput` exists in `core/schemas.py` with the five
      fields documented above at their documented types and defaults.
- [ ] The class has a complete RST-style docstring covering all five fields.
- [ ] All four unit tests above pass.
- [ ] `mypy --strict` clean on `src/`; `ruff` clean.
- [ ] No existing schema tests are broken.
