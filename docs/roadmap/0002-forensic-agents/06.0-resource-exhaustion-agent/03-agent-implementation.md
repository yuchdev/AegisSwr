# 03 - Agent implementation (`ResourceExhaustionAgent`)

**Parent task:** 06.0 Resource Exhaustion Agent
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 04, 05

## Objective

Implement `src/aegis_swr/agents/forensic/resource_analyst.py` containing
`ResourceExhaustionAgent`. The agent must follow the `run()` pattern established
by `OSKernelAgent` and extend it with log-context inclusion (mirroring
`LogHistorianAgent`) and a deterministic leak-indicator pre-check that populates
`leak_indicators` before the LLM is called.

## Files

- **Create** `src/aegis_swr/agents/forensic/resource_analyst.py`

## Class skeleton

```
class ResourceExhaustionAgent(BaseAgent):
    agent_key: ClassVar[str] = "resource_exhaustion"
    category: ClassVar[str] = "forensic"
    display_name: ClassVar[str] = "Resource Exhaustion Agent"

    @property
    def system_prompt(self) -> str: ...

    async def run(self, state: InvestigationState) -> AgentTurn: ...

    @staticmethod
    def _extract_leak_indicators(brief: dict[str, object]) -> list[str]: ...
```

The three `ClassVar`s satisfy contract C2 from `plan.md`. `display_name` must
equal the `AgentTurn.agent` string the agent emits.

## System prompt (specification)

The system prompt must convey the following persona and instructions to the LLM.
It is not a Python string literal here - the implementer writes the exact text.

Key elements the prompt must include:

1. **Persona**: the agent is an expert in OS resource accounting, kernel object
   management, and production memory-leak forensics. It reasons from handle
   tables, fd limits, thread-pool watermarks, connection-pool metrics, and
   GDI/kernel object counts.

2. **Scope of analysis**: the prompt explicitly names the resource types the
   agent investigates - Win32 handles, POSIX file descriptors, thread-pool
   workers, heap/virtual memory pages, connection-pool slots, GDI objects, kernel
   semaphore/mutex/event object counts.

3. **Log-temporal emphasis**: the prompt instructs the LLM that the user message
   includes a `log_summary` field and that temporal growth patterns in that
   summary are the primary diagnostic channel for slow leaks.

4. **Output contract**: instruct the agent to respond with a structured JSON
   object matching `ResourceExhaustionOutput`. Set `confidence_score` between
   0.0 and 1.0. Populate `exhausted_resource` with the most specific resource
   name resolvable. Populate `growth_trend` only when temporal evidence exists.

5. **`leak_indicators` instruction**: inform the LLM that `leak_indicators` has
   already been pre-populated by a deterministic scan; it may append additional
   indicators from its reasoning but must not remove pre-populated entries.

Include `cache_control: {"type": "ephemeral"}` on the system prompt block per
the project-wide `_BaseAIBackend` convention (C7).

## `run()` specification

1. Extract `round_number`, `incident_brief`, and `discussion_history` from
   `state` following the `OSKernelAgent.run()` pattern exactly.
2. Incorporate Skeptic corrections from the previous round using the same
   reversed-history scan pattern as `OSKernelAgent`.
3. Call `_extract_leak_indicators(brief)` - the deterministic pre-check - and
   store the result in a local variable before constructing the LLM context.
4. Build the user-message context dict. Include:
   - `"incident_brief"`: the full brief dict.
   - `"log_summary"`: `brief.get("log_summary")` - may be `None`; include the
     key regardless so the LLM can see its absence explicitly.
   - `"precheck_leak_indicators"`: the list returned by step 3.
   - `"round"`: the round number.
   - `"skeptic_corrections_from_previous_round"`: only if non-empty (same
     conditional as `OSKernelAgent`).
5. Call `self._ai.generate(self.system_prompt, messages, ResourceExhaustionOutput)`.
6. Assert the output is `ResourceExhaustionOutput`.
7. Merge pre-check indicators into the output's `leak_indicators`: deduplicate
   by string equality, preserving the LLM-returned order with pre-check entries
   prepended for any not already present. Do not mutate raw payload strings.
8. Build and return an `AgentTurn` with:
   - `agent = self.display_name` (`"Resource Exhaustion Agent"`).
   - `turn_number = round_num`.
   - `message`: a concise summary string derived from `output.exhausted_resource`
     and `output.growth_trend` (e.g. `f"Exhausted: {output.exhausted_resource}"`
     when both are present, fallback to the first hypothesis's `root_cause`).
   - `hypotheses`: mapped from `output.hypotheses` exactly as `OSKernelAgent`
     maps them (field-by-field `Hypothesis` construction, not dict unpacking).
   - `confidence_score = output.confidence_score`.
9. Call `self._accumulate_tokens(state)` before returning.

## `_extract_leak_indicators` specification

A `@staticmethod` that accepts `brief: dict[str, object]` and returns
`list[str]`. It must:

- Collect text from `brief.get("log_summary") or ""` and
  `brief.get("raw_text_excerpt") or ""`.
- Apply regex-based pattern matching (no shell invocation, no SQL) against a
  fixed set of resource-pressure signal patterns. Required patterns:
  - Case-insensitive match for `"out of memory"` / `"outofmemoryerror"` /
    `"oom"` keyword in context.
  - `"too many open files"`.
  - `"ERROR_NO_SYSTEM_RESOURCES"` (Windows NTSTATUS / Win32 error string).
  - `"handle count"` followed by a number, or any line containing
    `"handle"` adjacent to digits climbing above a plausible threshold.
  - `"thread"` adjacent to words like `"exhausted"`, `"starvation"`, `"limit"`,
    `"max"`.
  - `"connection pool"` or `"connectionpool"` adjacent to `"exhausted"` /
    `"full"` / `"timeout"`.
  - `"GDI object"` counts or `"USER object"` counts mentioned with values.
- For each match, append a short normalized indicator string (not the raw
  matched line in full - trim to a maximum of 200 characters to avoid
  persisting large payload fragments).
- Return the deduplicated list; preserve first-occurrence order.
- Never raise; on any internal error return an empty list and emit a
  `loguru` warning (do not log the raw text, only a sanitized message such as
  `"leak-indicator pre-check failed: {type(exc).__name__}"`).

## Constraints

- `Optional[T]` from `typing`; never `T | None`.
- `replace_optional.py --check` clean.
- `ruff` clean; line length 100.
- No bare `except:`; catch specific exception types.
- `_extract_leak_indicators` must never pass raw brief text to a shell, SQL,
  `eval`, or any unsanitised logging sink.
- RST-style docstrings on the class and on every public/static method.
- `display_name` must match the literal string used in `AgentTurn.agent`.

## Success criteria

- [ ] `src/aegis_swr/agents/forensic/resource_analyst.py` exists and is
      importable.
- [ ] `ResourceExhaustionAgent` has all three `ClassVar`s set correctly.
- [ ] `run()` follows the `OSKernelAgent` pattern, includes `log_summary` in
      context, and merges pre-check indicators into the output.
- [ ] `_extract_leak_indicators` matches all listed signal patterns via regex
      only; never logs raw text; never raises.
- [ ] `AgentTurn.agent` equals `"Resource Exhaustion Agent"`.
- [ ] `replace_optional.py --check` clean; `ruff` clean.
