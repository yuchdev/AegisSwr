# 03 — Burn down `type-arg`

**Parent task:** [02.0 Close the mypy Enforcement Gap](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Add the mypy CI job](01-mypy-ci-job.md)
**Blocks:** none

## Objective

`mypy.ini:6` disables `type-arg`, which fires on a generic used without its type
parameters — a bare `dict`, `list`, `tuple`, `set`, `type`, or `Callable`
where strict mypy wants `dict[str, int]`, `list[RCAReport]`,
`Callable[[DomainEvent], None]`, and so on. These are almost always
annotation-only fixes with no runtime effect. Re-enable the code and
parameterise every bare generic across `src/aegis_swr/`.

## Implementation approach

1. Baseline:
   ```bash
   uv run mypy --enable-error-code type-arg src/aegis_swr/ 2>&1 | grep -c "error:"
   ```
2. For each hit, supply the real parameters. The project already has correct
   examples to copy from — `core/events.py:145` declares
   `Subscriber = Callable[[DomainEvent], None]` and
   `core/events.py:158` uses `dict[type[DomainEvent], list[Subscriber]]`, so the
   codebase's own idiom (PEP 585 builtin generics, not `typing.Dict`) is the
   target form.

   ```python
   # before — type-arg
   def _sync_update_hitl(self, incident_id: str, response: dict):

   # after
   def _sync_update_hitl(self, incident_id: str, response: dict[str, object]):
   ```
   (`sqlite_store.py:130` already uses `dict[str, object]` for the public
   `update_hitl_response` signature — mirror that concrete type on any bare
   `dict` found in the same family.)
3. Where a true "any mapping" is intended, prefer `Mapping[str, object]` /
   `dict[str, object]` over `dict[Any, Any]` so the fix does not create a
   `no-any-return`/`arg-type` problem downstream.
4. Drop `type-arg` from `disable_error_code` in the same PR as the final fix.

## Exclusions

- No runtime behaviour changes — this group is annotation-only. If a
  parameterisation reveals an actual type mismatch (a `dict` that genuinely
  holds mixed types the rest of the code mishandles), that is an `arg-type` /
  `assignment` concern; fix it in its own group (04 / 05), not here.
- Generated protobuf stubs are out of scope (see subtask 02).

## Test plan

- CI `mypy` job stays green after `type-arg` is removed from `mypy.ini`.
- No new runtime unit test expected (annotation-only). Any logic correction
  that falls out ships with its own test.
- `uv run mypy src/aegis_swr/` clean locally before the PR.
</content>
