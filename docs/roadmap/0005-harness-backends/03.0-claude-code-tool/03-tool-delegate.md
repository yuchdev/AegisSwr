# 03 - ClaudeCodeTool.delegate() + budget + real tokens

**Parent task:** 03.0 Claude Code Subprocess Tool
**State:** ⬜ Not started
**Depends on:** 02
**Blocks:** 04

## Objective

Stand up `aegis_swr/claude_code/tool.py` with `ClaudeCodeTool` - the concrete
`CodeIntelBackend` for the installed `claude` CLI - and implement the happy path
of `delegate()`: the `CallBudget` pre-check, the one-shot spawn via
`ClaudeCodeProcess` (subtask 01), the NDJSON reduction via `parse_stream`
(subtask 02), and assembly of a success `CodeResult` whose `token_estimate` is
the **real** `usage.input_tokens + usage.output_tokens` sum (C6.2, C9). This
subtask also **forward-declares** a minimal `ClaudeCodeUnavailableError` for the
no-`result`/failure paths (canonical home is Task 05.0), and stubs the
`_dry_run_result` / `_failure` helpers that subtask 04 wires into the ordered
gates. Structural sibling of `OpenClaudeTool` (0004 Task 04.0), minus the gRPC
stream loop and permission gate: this backend delegates read-only guarding to the
CLI's own `--allowedTools` + scratch cwd (C6.3), so there is no tool-side
permission handler here.

## File: `aegis_swr/claude_code/tool.py`

```python
from __future__ import annotations

from typing import ClassVar

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.process import ClaudeCodeProcess, ClaudeCodeStreamResult, parse_stream
from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus


class ClaudeCodeUnavailableError(Exception):
    """Raised when the one-shot ``claude`` invocation cannot yield a result.

    **Forward declaration (C10 / Task 05.0).** This minimal definition exists so
    this task's failure paths (non-zero exit, timeout, missing ``result``
    message, spawn failure) have a typed error to raise before the canonical
    ``claude_code/exceptions.py`` exists - exactly as Milestone 0004's Task 01.0
    forward-declared ``OpenClaudeConfigError`` in ``config.py`` ahead of its
    canonical home (see the note in ``openclaude/exceptions.py``). Task 05.0
    moves the canonical definition into ``claude_code/exceptions.py`` (with the
    full auth-failure taxonomy) and updates this module to import/re-export it,
    so downstream imports of ``aegis_swr.claude_code.tool.ClaudeCodeUnavailableError``
    keep resolving unchanged.

    The message and ``reason`` are payload-free: never any task text, response
    text, argv, or credential value (C13). ``retriable`` lets subtask 04 classify
    a transient timeout separately from a deterministic non-zero exit.

    :param reason: Short, payload-free failure marker (e.g. ``"timeout"``,
        ``"nonzero_exit"``, ``"no_result_message"``, ``"spawn_failed"``).
    :param retriable: Whether the caller may retry (``True`` for a timeout;
        ``False`` for a deterministic non-zero exit / missing result).
    :ivar reason: The payload-free failure marker.
    :ivar retriable: Whether the operation may be retried.
    """

    def __init__(self, reason: str, *, retriable: bool = False):
        """Record the payload-free *reason* and retriability on the error."""
        self.reason = reason
        self.retriable = retriable
        super().__init__(f"claude one-shot invocation failed: {reason}")


class ClaudeCodeTool(CodeIntelBackend):
    """A :class:`CodeIntelBackend` that runs a one-shot ``claude`` subprocess.

    Each :meth:`delegate` call spawns a fresh ``claude -p … --output-format
    stream-json`` process (subtask 01), consumes its NDJSON stream (subtask 02),
    and returns one :class:`CodeResult` - no persistent sidecar, no health-check
    lifecycle (contrast :class:`~aegis_swr.openclaude.tool.OpenClaudeTool`). The
    class-level ``description`` concretely satisfies the abstract ``description``
    property on :class:`CodeIntelBackend`, so the tool is accepted anywhere a
    backend is expected. It never reads ``os.environ`` (settings own the config)
    and imports no sibling backend (C3).

    **Read-only enforcement is not owned by a tool-side gate.** Unlike
    ``OpenClaudeTool`` (which adds a defense-in-depth Bash allowlist check), this
    backend delegates read-only guarding entirely to the CLI's own
    ``--allowedTools`` allowlist, ``permission_mode``, and the mandatory
    disposable scratch cwd (C6.3). There is therefore no ``_check_permission``
    here; the guards live in the argv (subtask 01) and in ``ClaudeCodeSettings``
    (Task 02.0, which rejects ``--dangerously-skip-permissions``).

    **Token accounting is real (C6.2, C9).** ``token_estimate`` is the
    ``usage.input_tokens + usage.output_tokens`` sum from the terminal ``result``
    message, not a length estimate - the field name and ``int`` type are
    unchanged so ``CodeAgent``/``CallBudget`` stay backend-agnostic.

    :cvar name: Stable backend identifier used by ``CodeAgent`` registration.
    :cvar description: Human-readable capability advertised to the agent layer;
        overrides the abstract :class:`CodeIntelBackend` property.
    :ivar _settings: Immutable configuration and allowlists (Task 02.0).
    :ivar _bus: EventBus injected for structural parity and forward wiring;
        concrete ``claude_code.*`` emission lands in Task 05.0 (C10).
    :ivar _budget: Boundary-level token/cost accounting for one delegated call.
    """

    name: ClassVar[str] = "claude_code"
    description: ClassVar[str] = (
        "Open-ended multi-file code navigation via the installed Claude Code "
        "CLI (one-shot 'claude -p --output-format stream-json' per call; "
        "read-only tools over the repository under analysis)."
    )

    def __init__(
        self,
        settings: ClaudeCodeSettings,
        bus: EventBus,
        budget: CallBudget,
    ):
        """Store injected collaborators; spawn nothing and touch no budget.

        :param settings: Validated :class:`ClaudeCodeSettings` (Task 02.0),
            including ``allowed_tools``, ``permission_mode``, ``max_turns``,
            ``request_timeout_s``, and the mandatory disposable ``scratch_cwd``.
        :param bus: EventBus for future ``claude_code.*`` emissions (Task 05.0).
        :param budget: Per-call boundary :class:`CallBudget`; the pre-check and
            post-charge happen inside :meth:`delegate`.
        """
        self._settings = settings
        self._bus = bus
        self._budget = budget

    async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Delegate *task* to a one-shot ``claude`` process; return a result.

        Ordered gates (subtask 04 finalises the full ordering): budget pre-check
        first (no spawn on insufficient budget), then the ``ctx.dry_run``
        short-circuit (no spawn, zero tokens), then the spawn-parse-charge happy
        path implemented here. On a clean stream this spawns
        :class:`ClaudeCodeProcess`, reduces stdout via :func:`parse_stream`,
        charges the **real** ``usage`` sum AFTER completion, and returns a
        success :class:`CodeResult` (C6.2, C9). Timeout / non-zero-exit /
        missing-``result`` handling and the defensive final guard are added in
        subtask 04. Never raises: every failure path returns a typed result (C13).

        :param task: The open-ended code-navigation prompt (fed to stdin, C6.1).
        :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id``
            and ``dry_run``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        # C5-parallel step 1 - pre-check BEFORE any spawn; insufficient budget
        # returns a non-retriable failure with ZERO subprocesses spawned.
        if not self._budget.can_afford(self._pre_estimate(task)):
            return self._failure("insufficient_budget", retriable=False)

        # C6.5 - dry-run short-circuits with ZERO spawns and zero tokens; runs
        # AFTER the pre-check so an over-budget dry-run still returns the budget
        # failure. Finalised in subtask 04.
        if ctx.dry_run:
            return self._dry_run_result()

        # Happy path (this subtask); failure classification added in subtask 04.
        async with ClaudeCodeProcess(self._settings, task) as proc:
            result = await parse_stream(proc.stdout_lines())
        return self._on_result(result)

    def _pre_estimate(self, task: str) -> int:
        """Conservative pre-check token floor before the real ``usage`` is known.

        Because the real token count is only available from the terminal
        ``result`` message (C6.2, C9), the pre-check cannot use it; it gates entry
        on an input-derived floor ``max(1, len(task) // 4)``. This differs
        deliberately from ``OpenClaudeTool``, which pre-checks
        ``max_response_tokens // 4`` (a response-cap floor) because OpenClaude's
        usage is opaque. The floor only rejects calls that cannot afford even the
        input; the authoritative charge is the post-completion real sum.

        :param task: The task string whose length seeds the pre-estimate.
        :return: A conservative, non-zero pre-check token estimate.
        """
        return max(1, len(task) // 4)

    def _on_result(self, result: ClaudeCodeStreamResult) -> CodeResult:
        """Convert a clean :class:`ClaudeCodeStreamResult` into a success result.

        Requires a well-formed terminal ``result`` message: when
        ``result.usage is None`` (child died before completing) or
        ``result.is_error`` is set, this raises/returns via the subtask-04
        failure paths. On success it charges the **real** ``usage.total`` to the
        budget AFTER completion (never pre-charged) and returns a success
        :class:`CodeResult` whose ``token_estimate`` is that real sum (C6.2, C9).
        The success/error split and event emission (Task 05.0) are finalised in
        subtask 04; this subtask implements the clean success branch only.

        :param result: The reduced stream from :func:`parse_stream`.
        :return: A success :class:`CodeResult` on a clean, usage-bearing result.
        """
        ...

    def _dry_run_result(self) -> CodeResult:
        """Return the ``[dry-run]`` result with a zero token estimate (C6.5/C13).

        Short-circuits every external call: no ``claude`` process is spawned and
        the budget is untouched. Finalised in subtask 04.

        :return: A success :class:`CodeResult` marking a suppressed call.
        """
        ...

    def _failure(self, reason: str, *, retriable: bool) -> CodeResult:
        """Build a typed failure :class:`CodeResult` with a zero token estimate.

        Carries a short non-payload marker; encodes ``{"ok": False, "error":
        reason, "retriable": retriable}`` in ``metadata`` (never raw task/response
        text, C13). ``available=True``: a backend WAS registered - this is a
        per-call failure recorded in metadata (C4). Finalised in subtask 04.

        :param reason: Short, payload-free failure marker.
        :param retriable: Whether the caller may retry the delegation.
        :return: A typed-failure :class:`CodeResult`.
        """
        ...

    def _success(self, content: str, *, token_estimate: int, frame_count: int) -> CodeResult:
        """Build a success :class:`CodeResult` carrying observability metadata.

        Sets ``content`` to the accumulated answer, ``token_estimate`` to the
        real ``usage`` sum (C9), and records ``{"ok": True, "frame_count": …}``
        in ``metadata``. Finalised in subtask 04.

        :param content: The accumulated assistant answer text.
        :param token_estimate: The real ``usage.input_tokens + output_tokens``.
        :param frame_count: NDJSON frames observed (observability).
        :return: A success :class:`CodeResult`.
        """
        ...
```

## Implementation notes

- **Implements the unchanged ABC.** `CodeIntelBackend`, `CodeResult`,
  `CodeTaskContext`, and `CallBudget` come from the Milestone 0004 `code_intel/`
  package verbatim (backend.py / budget.py, byte-for-byte unchanged). This module
  imports them and never redefines them; `code_intel/` never imports this package
  (C3).
- **No tool-side permission gate.** OpenClaude added a defense-in-depth Bash
  allowlist check because its sidecar could be started in external mode without
  Aegis-managed launch flags. Claude Code always runs with the argv this package
  constructs (subtask 01), so read-only enforcement is the CLI's `--allowedTools`
  + `permission_mode` + scratch cwd (C6.3). Deliberately no `_check_permission`
  / `_is_allowlisted` here - do not port them.
- **Real tokens (C6.2, C9).** `_success` sets `token_estimate =
  result.usage.total`; `delegate` charges it via `self._budget.charge(...)`
  **after** the stream completes (post-charge only, never pre-charged - the
  pre-check reserves nothing). A dry-run, an insufficient-budget rejection, a
  timeout, or a non-zero exit charges **zero**.
- **`usage is None` / `is_error` -> failure.** Subtask 04 maps a missing
  `result` message or an error result to `ClaudeCodeUnavailableError` -> a typed
  failure `CodeResult` (retriable for a timeout, non-retriable for a deterministic
  error). This subtask leaves those branches to subtask 04 and implements only
  the clean, usage-bearing success branch in `_on_result`.
- **Pre-estimate divergence is intentional and flagged.** `_pre_estimate` uses an
  input-length floor, not OpenClaude's response-cap floor, because real usage is
  post-hoc. Note this in the docstring (done) so a reviewer does not "fix" it to
  match OpenClaude.
- **EventBus is injected but idle here.** Concrete `claude_code.*` emission
  (`spawned`, `completed` carrying the token figure, `error`) is Task 05.0. Hold
  the bus for parity/forward wiring; do not emit undefined event classes in this
  task (keeps the MVP path `01.0 → (02.0 → 03.0) → 10.0 → 11.0` free of Task 05.0).
- **Forward-declared exception.** `ClaudeCodeUnavailableError` is defined
  minimally in this file per the 0004 forward-declaration convention; Task 05.0
  relocates it to `claude_code/exceptions.py`. Keep its message/`reason`
  payload-free (C13).

## Constraints

- `from __future__ import annotations`; `Optional[T]` from `typing`, never
  `T | None` (C13).
- Implements the unchanged `CodeIntelBackend` ABC; imports no sibling backend and
  no `grpc` (C3); `code_intel/` stays untouched.
- `token_estimate` is the real `usage` sum (C6.2, C9); the field name/type are
  unchanged; the budget is charged **after** completion only, never pre-charged;
  failure/dry-run paths charge zero.
- No tool-side permission gate; read-only enforcement is the CLI allowlist +
  scratch cwd (C6.3).
- Budget pre-check and dry-run make **zero** spawns (asserted in Task 11.0).
- No task/response/argv/credential text logged or placed on any result/event
  (C13); `ClaudeCodeUnavailableError` messages are payload-free.
- No `Any` in any signature; `ruff` and `replace_optional.py --check` clean; RST
  docstrings on every public class/method (C13).

## Success criteria

- [ ] `ClaudeCodeTool(settings, bus, budget)` constructs with no I/O and touches
      no budget; it is accepted where a `CodeIntelBackend` is expected.
- [ ] `name == "claude_code"`; `description` advertises the one-shot CLI backend.
- [ ] Insufficient budget returns a non-retriable failure and **no** process is
      spawned (`ClaudeCodeProcess` never entered).
- [ ] A clean stream (assistant frames + a usage-bearing `result`) returns a
      success `CodeResult` whose `content` is the accumulated answer.
- [ ] `token_estimate == usage.input_tokens + usage.output_tokens`, charged to
      the budget **after** completion (C6.2, C9); the field name/type unchanged.
- [ ] The pre-check runs before the dry-run branch (over-budget + dry-run still
      returns the budget failure).
- [ ] No tool-side permission/allowlist gate exists in the file.
- [ ] `ClaudeCodeUnavailableError` is forward-declared here with a payload-free
      message/`reason` and a `retriable` attribute.
- [ ] No task/response/credential text is logged or emitted (C13).
- [ ] `ruff` and `replace_optional.py --check` clean; no `Any` in any signature.
