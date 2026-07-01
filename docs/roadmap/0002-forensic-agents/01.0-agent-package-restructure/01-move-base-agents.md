# 01 - Move base agents into `agents/base/`

**Parent task:** 01.0 Agent Package Restructure
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03

## Objective

Create the `src/aegis_swr/agents/base/` subpackage and move the five existing
modules into it with no logic changes. Fix only the intra-package import lines
that break because of the move.

## Files

- **Move** `src/aegis_swr/agents/base.py` → `src/aegis_swr/agents/base/base.py`
- **Move** `src/aegis_swr/agents/os_kernel.py` → `src/aegis_swr/agents/base/os_kernel.py`
- **Move** `src/aegis_swr/agents/code_analyst.py` → `src/aegis_swr/agents/base/code_analyst.py`
- **Move** `src/aegis_swr/agents/log_historian.py` → `src/aegis_swr/agents/base/log_historian.py`
- **Move** `src/aegis_swr/agents/skeptic.py` → `src/aegis_swr/agents/base/skeptic.py`
- **Create** `src/aegis_swr/agents/base/__init__.py`

## Changes

1. Perform the moves. Prefer `git mv` so history is preserved.
2. Inside each moved module, the imports of `aegis_swr.agents.base` (the
   `BaseAgent` import in `os_kernel.py`, `code_analyst.py`, `log_historian.py`,
   `skeptic.py`) still resolve unchanged because `aegis_swr.agents.base` is now a
   **package** whose `__init__.py` re-exports `BaseAgent` (see step 3). No edit
   needed to those `from aegis_swr.agents.base import BaseAgent` lines.
3. Write `agents/base/__init__.py` re-exporting the public classes:

   ```python
   from aegis_swr.agents.base.base import BaseAgent
   from aegis_swr.agents.base.code_analyst import CodeAnalystAgent
   from aegis_swr.agents.base.log_historian import LogHistorianAgent
   from aegis_swr.agents.base.os_kernel import OSKernelAgent
   from aegis_swr.agents.base.skeptic import SkepticAgent

   __all__ = [
       "BaseAgent",
       "OSKernelAgent",
       "CodeAnalystAgent",
       "LogHistorianAgent",
       "SkepticAgent",
   ]
   ```

   > Note: `base.py` lives at `agents/base/base.py`. The package `__init__`
   > re-exporting `BaseAgent` from the submodule is what keeps
   > `from aegis_swr.agents.base import BaseAgent` working for the moved agent
   > modules (and any external caller).

## Constraints

- **No logic edits** to any moved module beyond what the move strictly requires
  (which is nothing, given the re-export design above).
- Do not touch `core/orchestrator.py` or tests in this subtask - that is 01.0/02.
- Keep the existing `from __future__ import annotations` and `Optional[T]` style.

## Tests

No new tests in this subtask. The gate is that `pytest tests/unit/ -q` and
`mypy src/` are unaffected **after** subtask 02 repoints the consumers. Within
this subtask, verify imports resolve in isolation:

```
python -c "from aegis_swr.agents.base import OSKernelAgent, CodeAnalystAgent, LogHistorianAgent, SkepticAgent, BaseAgent; print('ok')"
```

## Success criteria

- [ ] All five modules live under `src/aegis_swr/agents/base/`.
- [ ] `agents/base/__init__.py` re-exports the five public classes.
- [ ] `from aegis_swr.agents.base import OSKernelAgent` (and the other four)
      resolves.
- [ ] No logic diff inside the moved modules (a `git diff -M` shows pure renames
      plus the new `__init__.py`).
