# 01 — `HarnessSession` per-role session object

**Parent task:** 03.0 Harness Session Adapter & Factory
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03 (this task)
**Contracts:** C4, C5, C7, C9, C12

## Objective

Define `HarnessSession` in `harness/session.py`: a per-role object wrapping a
Milestone-0005 `CodeIntelBackend` plus the role's binding (tool tier, trust tier,
timeout) and exposing a single async `run_turn(...)` the adapter calls.

## Shape (described, not implemented)

```python
class HarnessSession:
    """One forensic role's bound harness session (C4, C5).

    Wraps a resolved CodeIntelBackend (chosen at the role's trust tier, C9) and
    the role binding from the Task 01.0 table. Exposes run_turn(), which folds a
    role turn into a bounded task string and delegates to the backend, returning
    the structured CodeResult for the adapter to parse (subtask 04).

    :ivar role_key: The forensic role this session serves (e.g. "os_kernel").
    :ivar trust_tier: "payload" or "trusted_source" (C9).
    :ivar tool_allowlist: The concrete allowlist for this role's persona (C5).
    """

    async def run_turn(
        self,
        system_prompt: str,
        task: str,
        *,
        output_hint: Optional[str] = None,
    ) -> CodeResult: ...
```

## Session-statefulness decision (flagged)

**Proposed:** **per-turn re-delegation.** Each `run_turn` constructs a fresh,
bounded task string = the role's system prompt role-summary + the pushed
pre-redacted incident summary (C7) + a compact digest of the prior debate turns
relevant to this role, then calls `backend.delegate(task, ctx)`. This keeps every
turn one auditable one-shot delegation (matching how `code_analyst` already seeds
a question and lets `CodeAgent.investigate()` pull specifics), bounds token growth
explicitly, and composes with the one-shot `claude_code` backend that has no
persistent session at all.

**Alternative (flagged for confirmation):** a long-lived stateful session carried
across rounds (cheaper shared context on the sidecar backends, but opaque for
OpenClaude/Claude Code token accounting and harder to bound/redact per turn).

Record the chosen option in the task README and `status.md`; do not implement
before the user confirms.

## Behaviour

- `run_turn` has a timeout (the role's `timeout_s`) and a defined failure path: a
  session/backend failure surfaces as a typed error the adapter maps to the
  existing `AIOutputValidationError`/retry flow or a loud failure — never a silent
  empty turn (C12).
- The pushed summary is passed **already redacted** (through `mcp/redaction.py`,
  Task 05.0); `HarnessSession` never redacts raw payload itself, but it asserts
  (debug-only, payload-free) that the task it is about to send carries no
  unredacted-marker sentinel.
- No raw payload/prompt/response text is logged; `SensitiveFilter` on every sink
  (C12).

## Acceptance criteria

- [ ] `HarnessSession` wraps a `CodeIntelBackend` + role binding and exposes
      `run_turn` returning a `CodeResult` (C4).
- [ ] `run_turn` folds system prompt + pushed summary + prior-turn digest into one
      bounded task (per-turn re-delegation), with the stateful alternative recorded
      as flagged (C7).
- [ ] Timeout + defined failure path; no silent empty turn (C12).
- [ ] No unredacted payload/prompt/response reaches a log sink (C12).
- [ ] `ruff` clean; RST docstrings; `Optional[T]` not `T | None`.
