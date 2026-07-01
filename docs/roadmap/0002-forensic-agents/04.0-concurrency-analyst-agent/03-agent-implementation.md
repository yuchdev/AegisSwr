# 03 - Agent implementation (`ConcurrencyAnalystAgent`)

**Parent task:** 04.0 Concurrency Analyst Agent
**State:** ⬜ Not started
**Depends on:** 01 (output schema)
**Blocks:** 04, 05

## Objective

Implement `ConcurrencyAnalystAgent` in
`src/aegis_swr/agents/forensic/concurrency_analyst.py`. The agent follows the
`os_kernel.py` run-loop pattern exactly and adds a **deterministic wait-chain
pre-check** that fires before the LLM call when the incident brief shows
evidence of multiple blocked threads.

## Files

- **Create** `src/aegis_swr/agents/forensic/concurrency_analyst.py`
- **Modify** `src/aegis_swr/agents/forensic/__init__.py`
  (add `ConcurrencyAnalystAgent` to the package exports)

## Module structure

### ClassVars (contract C2)

```
agent_key    = "concurrency_analyst"
category     = "forensic"
display_name = "Concurrency Analyst Agent"
```

`display_name` must equal the string passed to `AgentTurn(agent=...)` so that
existing turn-matching logic in consensus and the orchestrator is undisturbed.

### System prompt

The module-level `_SYSTEM_PROMPT` constant must:

1. Declare the agent's forensic persona: an expert in concurrent programming
   hazards - deadlocks, lock-ordering inversions, race conditions, TOCTOU
   vulnerabilities, thread wait-chains, and priority starvation.
2. Instruct the LLM to reason about lock acquisition order, thread state
   (blocked/runnable/waiting), mutex ownership, and synchronization primitive
   signals (`WaitForMultipleObjects`, `EnterCriticalSection`, `pthread_mutex`,
   `std::mutex`, `CRITICAL_SECTION`, `futex`, `os_unfair_lock`).
3. Require output as a strict JSON object matching `ConcurrencyAnalystOutput`:
   `hypotheses` (list), `confidence_score` (float 0–1), `wait_chain` (list of
   strings), `lock_order_inversions` (list of strings), `suspected_race`
   (string or null).
4. Instruct the agent to weight heavily toward `deadlock` when the `fault_class`
   in the brief is `deadlock`, and toward race-condition hypotheses when
   `use_after_free` or `assertion_failure` is present.
5. Not exceed 600 tokens (the cache-control block is added by `_BaseAIBackend`;
   the agent passes the system prompt through as a plain string).

### `run(state: InvestigationState) -> AgentTurn`

Execution sequence:

1. **Extract from state:**
   - `round_num = state.get("round_number", 1)`
   - `brief = state.get("incident_brief", {})`
   - `history = state.get("discussion_history", [])`

2. **Skeptic-correction injection** (identical pattern to `os_kernel.py`):
   On `round_num > 1`, scan `history` in reverse for the most recent
   `SkepticAgent` turn at `round_num - 1`; extract its `corrections` list.

3. **Deterministic wait-chain pre-check** (fires before LLM call):

   Scan `brief.get("raw_text_excerpt", "")` and any thread-summary fields
   for:
   - Keywords: `WaitForMultipleObjects`, `EnterCriticalSection`,
     `pthread_mutex_lock`, `pthread_mutex_trylock`, `std::mutex`, `CRITICAL_SECTION`,
     `os_unfair_lock`, `futex`, `SleepConditionVariableCS`, `MonitorEnter`.
   - Pattern: two or more stack frames from different threads referencing
     blocking calls.

   When the pre-check fires, construct a `wait_chain_candidates: list[str]`
   from any thread-identifier strings found adjacent to the blocking keywords
   (regex extraction, no shell invocation). These candidates are passed into
   the LLM context so the model can confirm or refine them.

   The pre-check result is stored in the `context` dict under the key
   `"wait_chain_candidates"` so it is visible in the LLM prompt.

4. **Build `context` dict:**

   ```
   {
     "incident_brief": brief,
     "round": round_num,
     ["skeptic_corrections_from_previous_round": corrections],   # if round > 1
     ["warning": brief["low_symbol_coverage_warning"]],          # if present
     ["wait_chain_candidates": wait_chain_candidates],           # if pre-check fired
   }
   ```

5. **LLM call:**
   `output = await self._ai.generate(self.system_prompt, messages, ConcurrencyAnalystOutput)`
   `assert isinstance(output, ConcurrencyAnalystOutput)`

6. **Merge pre-check results:** If `wait_chain_candidates` was non-empty and
   `output.wait_chain` is empty, prepend the candidates into `output.wait_chain`
   so the deterministic signal is never lost even if the LLM returns an empty
   list. If `output.wait_chain` is already populated, do not overwrite it.

7. **Build and return `AgentTurn`:**

   ```
   AgentTurn(
       agent="Concurrency Analyst Agent",
       turn_number=round_num,
       message=<primary hypothesis root_cause, or a summary string if empty>,
       hypotheses=<list[Hypothesis] built from output.hypotheses>,
       confidence_score=output.confidence_score,
   )
   ```

   The `message` field should summarise the primary finding; a good default is
   the `root_cause` of the highest-confidence hypothesis, or a
   "No concurrency fault detected" string if `hypotheses` is empty.

8. **Token accounting:** `self._accumulate_tokens(state)` (same as all agents).

### Helper function

```
def _extract_wait_chain_candidates(text: str) -> list[str]
```

A module-level private function that accepts a raw text string and returns a
list of human-readable candidate strings describing detected blocking-primitive
mentions. It uses only `re` (stdlib); no shell calls, no eval, no SQL. Returns
an empty list when no candidates are found. Must be independently unit-testable.

## Constraints

- `Optional[T]` from `typing`; never `T | None`.
- `mypy --strict` and `ruff` clean.
- `_extract_wait_chain_candidates` is pure (no I/O, no side effects).
- The pre-check must never log raw incident payload text; log only counts or
  booleans via loguru with `SensitiveFilter` in place.
- No bare `except:`; catch specific exceptions from the AI backend and let them
  propagate so the orchestrator's retry/failure path handles them.
- Do not hard-code thread IDs or module names - the regex must be generic.

## Success criteria

- [ ] `src/aegis_swr/agents/forensic/concurrency_analyst.py` exists and imports
      cleanly from `aegis_swr.agents.forensic`.
- [ ] `ConcurrencyAnalystAgent.agent_key == "concurrency_analyst"`,
      `category == "forensic"`, `display_name == "Concurrency Analyst Agent"`.
- [ ] `run()` calls `self._ai.generate(...)` with `ConcurrencyAnalystOutput` as
      the response model.
- [ ] The wait-chain pre-check fires and populates `wait_chain_candidates` in
      the context when blocking-primitive keywords are present in `raw_text_excerpt`.
- [ ] Pre-check candidates are merged into `output.wait_chain` when the LLM
      returns an empty list.
- [ ] `_extract_wait_chain_candidates` is a standalone, pure function.
- [ ] `mypy --strict` clean; `ruff` clean.
