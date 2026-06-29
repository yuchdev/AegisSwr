# 02 — Update consumers & back-compat shims

**Parent task:** 01.0 Agent Package Restructure
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 04

## Objective

Repoint everything that imports the four agents from their old top-level paths,
and add re-export shims at the old module paths so any caller (in-repo or
external) keeps working. After this subtask the full suite is green again.

## Files

- **Modify** `src/aegis_swr/core/orchestrator.py` (the four agent imports)
- **Modify** `src/aegis_swr/agents/__init__.py` (top-level re-exports)
- **Modify** any test modules that import the moved agents by their old path
- **Create** shim modules at the old paths (see "Shim strategy")

## Shim strategy

Choose **one** of the two equivalent approaches and apply it uniformly; the
re-export package `__init__` (Approach A) is preferred because it needs no
deletable stub files.

**Approach A — top-level re-export (preferred).** `agents/__init__.py`:

```python
from aegis_swr.agents.base import (
    BaseAgent,
    CodeAnalystAgent,
    LogHistorianAgent,
    OSKernelAgent,
    SkepticAgent,
)

__all__ = [
    "BaseAgent",
    "OSKernelAgent",
    "CodeAnalystAgent",
    "LogHistorianAgent",
    "SkepticAgent",
]
```

This makes `from aegis_swr.agents import OSKernelAgent` work, but does **not**
restore `from aegis_swr.agents.os_kernel import OSKernelAgent` (a submodule
path). If any code or test uses the submodule path, repoint it to
`aegis_swr.agents.base` (preferred), or add thin shim modules per Approach B.

**Approach B — submodule shims (only if a submodule path must survive).** Create
`agents/os_kernel.py` etc. each containing:

```python
from aegis_swr.agents.base.os_kernel import OSKernelAgent  # noqa: F401  (back-compat shim)
```

## Changes

1. Update `core/orchestrator.py` imports from
   `from aegis_swr.agents.os_kernel import OSKernelAgent` (×4) to
   `from aegis_swr.agents.base import OSKernelAgent, CodeAnalystAgent, LogHistorianAgent, SkepticAgent`.
2. `grep -rn "aegis_swr.agents.os_kernel\|aegis_swr.agents.code_analyst\|aegis_swr.agents.log_historian\|aegis_swr.agents.skeptic" src/ tests/`
   and repoint every hit to `aegis_swr.agents.base`.
3. Apply the chosen shim approach for any external/back-compat path that must
   survive.

## Constraints

- Prefer repointing in-repo imports to the new `agents.base` path over leaving
  shims; reserve shims for paths you cannot edit.
- No behavior change; `mypy --strict` and `ruff` clean.

## Tests

- Add `tests/unit/test_agents_package.py` (or extend an existing agents test):
  - `test_base_import_path` — `from aegis_swr.agents.base import OSKernelAgent` etc.
  - `test_top_level_reexport` — `from aegis_swr.agents import SkepticAgent`.
  - (If Approach B is used) `test_legacy_submodule_shim` —
    `from aegis_swr.agents.os_kernel import OSKernelAgent` still resolves.
- Existing `test_agents.py` / `test_orchestrator.py` must pass unchanged (or with
  only import-line edits).

## Success criteria

- [ ] `core/orchestrator.py` imports the four agents from `aegis_swr.agents.base`.
- [ ] No remaining references to the old submodule import paths in `src/`/`tests/`
      (except intentional shims).
- [ ] `pytest tests/unit/ -q` fully green; `mypy src/` clean.
