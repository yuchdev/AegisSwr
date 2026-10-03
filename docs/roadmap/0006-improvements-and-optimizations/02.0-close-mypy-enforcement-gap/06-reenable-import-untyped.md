# 06 — Resolve `import-untyped`

**Parent task:** [02.0 Close the mypy Enforcement Gap](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Add the mypy CI job](01-mypy-ci-job.md)
**Blocks:** none

## Objective

`mypy.ini:6` disables `import-untyped`, which fires when a third-party module
has no type information (no bundled `py.typed`, no stub package installed). Unlike
the other ten disabled codes, this one is **not** fixed by editing
`src/aegis_swr/` — it is resolved by installing stub packages or declaring a
scoped per-module override. The project's stack (`.claude/CLAUDE.md` §2:
FastAPI, Typer, Pydantic v2, LangGraph, SQLAlchemy/asyncpg, boto3, anthropic +
openai SDKs, loguru, qdrant-client, python-socketio, grpc) is a mix of
typed-shipping and stubless libraries, so a blanket enable would light up only
the stubless ones.

## Implementation approach

1. Baseline:
   ```bash
   uv run mypy --enable-error-code import-untyped src/aegis_swr/ 2>&1 | grep "error:"
   ```
   Read the *module names* in the output, not just the count — each names a
   specific dependency.
2. For each stubless import, in priority order:
   - **Install the official stub package** if one exists (e.g. `boto3-stubs`,
     `types-*`), added to the dev dependency group in `pyproject.toml`. This is
     the preferred fix — it gives real checking, not suppression.
   - **If no stub exists**, add a *scoped, per-module* override to `mypy.ini`
     with a justification comment:
     ```ini
     [mypy-socketio.*]
     ignore_missing_imports = true   # no stubs published; client lib only in openhands/client.py (C3)
     ```
     Scope it to the exact module — never a global `ignore_missing_imports =
     true`, which would re-disable the check everywhere and defeat the subtask.
3. Generated protobuf stubs already ship their own `.pyi` files
   (`openclaude/grpc/proto/openclaude_pb2.pyi`,
   `openclaude_pb2_grpc.pyi`) and are typed; they should not appear in the
   baseline. If they do, the scoping is wrong — fix the scope.
4. Because the gRPC/socketio client libraries are confined to single modules by
   contract C3 (`grpc` only in `openclaude/grpc/client.py`; socketio only in
   `openhands/client.py`), any per-module override is also confined there —
   note that correspondence in the override comment so the C3 boundary stays
   legible.
5. Drop `import-untyped` from `disable_error_code` in the same PR.

## Exclusions

- No product-code logic changes — this subtask touches `pyproject.toml`
  (dev-dep stubs) and `mypy.ini` (scoped overrides) only.
- A global `ignore_missing_imports = true` is explicitly forbidden; so is a
  broad `[mypy-aegis_swr.*]` override (that would hide first-party errors the
  other subtasks just burned down).

## Test plan

- CI `mypy` job stays green after `import-untyped` is removed from `mypy.ini`.
- Adding a stub dev-dependency changes `uv.lock`; coordinate with
  [Task 04.0](/docs/roadmap/0006-improvements-and-optimizations/04.0-ci-supply-chain-integrity/README.md)
  so the `--locked` CI check sees a re-locked file, and the `dep_audit.py` hook's
  manifest-change path runs clean.
- `uv run mypy src/aegis_swr/` clean locally before the PR; confirm the final
  `mypy.ini` `disable_error_code` line is **empty** (this is the last of the
  eleven codes), so `strict = true` is now true in practice.
</content>
