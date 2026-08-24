# 03 - Agent implementation (`MemoryForensicsAgent`)

**Parent task:** 03.0 Memory Forensics Agent
**State:** ⬜ Not started
**Depends on:** 01 (output schema)
**Blocks:** 04, 05

## Objective

Implement `src/aegis_swr/agents/forensic/memory_forensics.py` containing
`MemoryForensicsAgent`. The agent follows the `os_kernel.py` implementation
pattern exactly: a module-level `_SYSTEM_PROMPT` constant, a `run()` method that
builds a context dict and calls `self._ai.generate(...)`, and a deterministic
fill-pattern pre-check that runs before and independent of the LLM call.

## Files

- **Create** `src/aegis_swr/agents/forensic/memory_forensics.py`
- **Modify** `src/aegis_swr/agents/forensic/__init__.py` - add
  `MemoryForensicsAgent` to `__all__` and the module-level import.

## ClassVars (contract C2)

```
agent_key    = "memory_forensics"
category     = "forensic"
display_name = "Memory Forensics Agent"
```

`display_name` must equal the string passed as `AgentTurn.agent` so existing
turn-matching logic in consensus and the orchestrator continues to work unchanged.

## System prompt

Define `_SYSTEM_PROMPT` as a module-level constant (not a property body). The
persona must convey:

- Expert identity: a memory-safety and heap-corruption forensics specialist.
- Primary specialism: heap corruption, use-after-free, double-free, buffer
  over/underflow, allocator and heap-metadata tells, guard-page hits, fill-pattern
  sentinel analysis (`0xCCCCCCCC`, `0xFEEEFEEE`, `0xBAADF00D`, `0xDDDDDDDD`,
  `0xABABABAB`, `0xCDCDCDCD`).
- Instruction to reason about: allocator metadata consistency, chunk size
  fields, free-list linkage, guard pages, fill patterns, and allocation-site
  provenance.
- Explicit instruction to output structured JSON matching `MemoryForensicsOutput`,
  with `confidence_score` between 0.0 and 1.0.
- Instruction to populate `corruption_signatures` with every hex sentinel or
  allocator anomaly found, `suspected_allocation_site` when traceable, and
  `heap_state` with a concise assessment of the heap's integrity.

The prompt must **not** tell the model to repeat raw stack text verbatim or to
include PII or credential values.

## `run()` method

Follow the `os_kernel.py` pattern precisely:

1. Extract `round_num`, `incident_brief`, and `discussion_history` from `state`.
2. Collect Skeptic corrections from the previous round (same reversed-history scan
   as `OSKernelAgent`).
3. **Deterministic fill-pattern pre-check** (runs before the LLM call):
   - Scan `incident_brief.get("stack_frames", [])` and
     `incident_brief.get("raw_text_excerpt", "")` using regex for the known
     sentinel hex constants: `0xCCCCCCCC`, `0xCCCC`, `0xFEEEFEEE`, `0xBAADF00D`,
     `0xDDDDDDDD`, `0xABABABAB`, `0xCDCDCDCD`.
   - Collect unique matches (case-insensitive) into `pre_detected_signatures:
     list[str]`.
   - The regex must operate on strings only; never pass raw bytes or binary
     content to the pattern.
4. Build `context: dict[str, object]` from the brief, round number, and any
   Skeptic corrections. Include `pre_detected_signatures` in the context dict so
   the LLM can reference them.
5. Call `output = await self._ai.generate(self.system_prompt, messages, MemoryForensicsOutput)`.
6. Merge: `final_signatures = list({*pre_detected_signatures, *output.corruption_signatures})`
   - the LLM may surface additional signatures; the deterministic pre-check
   results are never discarded.
7. Construct `AgentTurn`:
   - `agent = self.display_name` (i.e. `"Memory Forensics Agent"`).
   - `turn_number = round_num`.
   - `message`: a concise narrative derived from the output (e.g. first
     hypothesis `root_cause`, or a brief summary of `heap_state`).
   - `hypotheses`: list of `Hypothesis` built from `output.hypotheses`.
   - `confidence_score = output.confidence_score`.
8. Call `self._accumulate_tokens(state)`.
9. Return the `AgentTurn`.

## Constraints

- `ruff check src/ tests/` - clean.
- The regex for fill-pattern detection must be compiled at module level (not
  inside the hot path) using `re.compile`.
- Untrusted payload text (stack frames, raw excerpt) must not be passed to a
  shell, SQL, `eval`, or logged at any level. Regex scanning is the only
  permitted operation on this text in this module.
- `SensitiveFilter` is applied via the loguru setup; do not bypass it.
- No `print` statements in product code; use `loguru.logger` for diagnostics.
- The `_SYSTEM_PROMPT` constant must include the literal instruction to output
  JSON matching `MemoryForensicsOutput` so test assertions on prompt content
  keywords are unambiguous.

## Success criteria

- [ ] `src/aegis_swr/agents/forensic/memory_forensics.py` exists and is importable.
- [ ] `MemoryForensicsAgent.agent_key == "memory_forensics"`,
      `category == "forensic"`, `display_name == "Memory Forensics Agent"`.
- [ ] `_SYSTEM_PROMPT` references the agent's specialism keywords and
      `MemoryForensicsOutput`.
- [ ] `run()` returns an `AgentTurn` with `agent == "Memory Forensics Agent"`.
- [ ] The fill-pattern pre-check populates `corruption_signatures` for a brief
      containing `0xBAADF00D` before the LLM call is invoked.
- [ ] Merged `corruption_signatures` never loses pre-check entries even when the
      LLM returns an empty list.
- [ ] `ruff check src/ tests/` - clean.
