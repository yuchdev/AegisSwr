# 05 — Burn down `assignment` + `attr-defined`

**Parent task:** [02.0 Close the mypy Enforcement Gap](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Add the mypy CI job](01-mypy-ci-job.md); land **after**
subtask 02 so untyped bodies no longer mask these
**Blocks:** none

## Objective

`mypy.ini:6` disables two codes from the `Optional`/attribute-safety cluster:

- **`attr-defined`** — access to an attribute that does not exist on the
  (possibly narrowed) type.
- **`assignment`** — assigning a value whose type is incompatible with the
  target's declared/inferred type.

Measured 2026-10-03 (full re-enable run, see parent README): **1 occurrence
each — 2 total**. `union-attr` — the code originally grouped here and
described as highest real-bug-yield, since it catches unguarded `None`
dereferences — measured **zero** violations and is dropped for free in
subtask 01; this subtask's real scope is the two remaining single-digit codes.
Treat each of the two real occurrences as a *suspected real bug* until proven
otherwise, not a type-annotation nit.

## Implementation approach

1. Re-baseline both codes (subtask 01 methodology) — confirm the counts are
   still ~1 each before starting; at this size the fix is a single small PR,
   not a campaign.
2. Fix by **narrowing**, not by casting. The codebase already has the correct
   `Optional`-guard idiom — `sqlite_store.py:111-113`:

   ```python
   if row is None:
       return None
   return RCAReport.model_validate_json(row[0])
   ```
   Apply that shape wherever an `Optional[...]` return from one of the store /
   adapter methods (`get_report`, `find_by_hash`, `load_recent`) is consumed
   without a `None` check.
3. For `attr-defined`, confirm whether the attribute was renamed/removed (a real
   bug) or the type is too narrow (annotation fix). Never silence with
   `# type: ignore[attr-defined]` unless the attribute is a documented dynamic
   one with an inline justification.
4. Security note: an `assignment`/`attr-defined` fix on an incident-handling
   path must preserve the `SensitiveFilter` / no-raw-payload invariant
   (`.claude/CLAUDE.md` §3) — do not "fix" a `None` by logging the offending
   value to see what it was.
5. Drop `assignment` and `attr-defined` from `disable_error_code` in the same
   PR as the two fixes.

## Exclusions

- `arg-type` belongs to subtask 04 even if co-located; do not expand scope.
- Third-party `attr-defined` caused by missing stubs is a subtask-06 concern.

## Test plan

- CI `mypy` job stays green after `assignment` and `attr-defined` are removed
  from `mypy.ini`.
- **Each fix that corrects a real `None` dereference or missing attribute
  ships with a `testing-expert` regression test** reproducing the
  previously-crashing path — at only 2 sites, both are worth an individual
  regression test rather than a blanket smoke check.
- Any fix touching investigation flow or payload handling gets an
  `incident-analyst` pass; one touching logging/redaction gets a
  `security-auditor` pass (`.claude/CLAUDE.md` §5).
- `uv run mypy src/aegis_swr/` clean locally before the PR.
</content>
