# 01 - Generalize `BaseAgent`

**Parent task:** 02.0 Extensible Panel
**State:** ⬜ Not started
**Depends on:** Task 01.0
**Blocks:** 03, 04

## Objective

Add identity `ClassVar`s to `BaseAgent` so the registry, consensus, and
orchestrator can address any agent by a stable key without hard-coded tuples.
Implements contract **C2**.

## Files

- **Modify** `src/aegis_swr/agents/base/base.py`
- **Modify** `src/aegis_swr/agents/base/os_kernel.py`
- **Modify** `src/aegis_swr/agents/base/code_analyst.py`
- **Modify** `src/aegis_swr/agents/base/log_historian.py`
- **Modify** `src/aegis_swr/agents/base/skeptic.py`

## Changes

1. In `BaseAgent`, declare three abstract-by-convention class variables:

   ```python
   from typing import ClassVar

   class BaseAgent(ABC):
       agent_key: ClassVar[str]        # canonical key, e.g. "os_kernel"
       category: ClassVar[str]         # "base" | "forensic" | "synthesis"
       display_name: ClassVar[str]     # human label, e.g. "OS Kernel Agent"
   ```

   Keep the existing constructor, `system_prompt` property, `run`, `_append_turn`,
   and `_accumulate_tokens` unchanged.

2. Set the `ClassVar`s on each of the four base agents:

   | Class | `agent_key` | `category` | `display_name` |
   |-------|-------------|------------|----------------|
   | `OSKernelAgent` | `os_kernel` | `base` | `OS Kernel Agent` |
   | `CodeAnalystAgent` | `code_analyst` | `base` | `Code Analyst Agent` |
   | `LogHistorianAgent` | `log_historian` | `base` | `Log Historian Agent` |
   | `SkepticAgent` | `skeptic` | `base` | `Skeptic Agent` |

3. **`display_name` MUST equal the string already passed to
   `AgentTurn(agent=...)`** in each agent's `run()` (e.g. `"OS Kernel Agent"`).
   This keeps the orchestrator's turn-matching (`turn.agent == "Skeptic Agent"`)
   working. Where practical, replace the literal in `run()` with
   `self.display_name` to remove the duplication - but the *value* must not change.

## Constraints

- No change to any agent's analytical behavior or prompt text.
- `ClassVar` typing must stay explicit and consistent (declare on the base, assign on
  subclasses).

## Tests

- Extend `tests/unit/test_agents.py`:
  - `test_agent_identity_classvars` - each base agent exposes the expected
    `agent_key` / `category` / `display_name`.
  - `test_display_name_matches_turn_agent` - after `run()` (with `MockAIBackend`),
    the produced `AgentTurn.agent` equals the class `display_name`.

## Success criteria

- [ ] `BaseAgent` declares `agent_key`, `category`, `display_name` `ClassVar`s.
- [ ] The four base agents set them per the table; `display_name` == the existing
      `AgentTurn.agent` value.
- [ ] All existing agent/orchestrator tests pass unchanged; new identity tests pass.
- [ ] `ruff check src/ tests/` - clean.
