"""The Claude Code :class:`CodeIntelBackend`: a one-shot ``claude`` subprocess.

This module hosts :class:`ClaudeCodeTool`, a concrete
:class:`~aegis_swr.code_intel.backend.CodeIntelBackend` that runs a fresh
``claude -p … --output-format stream-json`` process per
:meth:`ClaudeCodeTool.delegate` call, consumes its NDJSON stream, and returns one
:class:`~aegis_swr.code_intel.backend.CodeResult` — no persistent sidecar, no
health-check lifecycle (contrast :class:`~aegis_swr.openclaude.tool.OpenClaudeTool`).

Three things distinguish it from OpenClaude (C6, C9): the task text is fed over
stdin and never appears in argv (C6.1, enforced in
:mod:`aegis_swr.claude_code.process`); ``token_estimate`` is the **real**
``usage.input_tokens + usage.output_tokens`` sum from the terminal ``result``
message rather than a length estimate (C6.2, C9); and read-only enforcement is
delegated to the CLI's own ``--allowedTools`` allowlist, ``permission_mode``, and
the mandatory disposable scratch cwd (C6.3) — there is no tool-side permission
gate here.

All failure paths return a typed :class:`CodeResult`; no exception escapes
:meth:`ClaudeCodeTool.delegate` (C13). No raw task, response, argv, stderr, or
credential text is ever logged or placed on a result or event (C13).
"""

from __future__ import annotations

import asyncio
from typing import ClassVar, Final, Optional
from uuid import uuid4

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.events import (
    ClaudeCodeAuthFailed,
    ClaudeCodeCompleted,
    ClaudeCodeError,
    ClaudeCodeExited,
    ClaudeCodePermissionDenied,
    ClaudeCodeSpawned,
    ClaudeCodeToolCall,
    ClaudeCodeToolResult,
)
from aegis_swr.claude_code.exceptions import ClaudeCodeUnavailableError
from aegis_swr.claude_code.process import (
    ClaudeCodeProcess,
    ClaudeCodeStreamResult,
    ResolvedCredential,
    parse_stream,
    resolve_credential,
)
from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus

#: Short, independent timeout (seconds) for the startup auth-probe. Deliberately
#: decoupled from ``settings.request_timeout_s`` so a health-check fails fast and
#: a stalled credential endpoint cannot block startup / ``code-intel check``
#: (C7 / threat model Finding 9). Fixed, not operator-tunable in this task.
_PROBE_TIMEOUT_S: Final[float] = 20.0

#: The minimal, side-effect-light prompt the auth-probe feeds the one-shot
#: ``claude`` over stdin. It forces credential resolution without performing a
#: real investigation; it is task text, never argv (C6.1), and never logged.
_PROBE_TASK: Final[str] = "ping"

#: The closed vocabulary of auth-failure reasons the probe may surface, shared
#: with :class:`ClaudeCodeAuthFailed` and :class:`ClaudeCodeUnavailableError`
#: (C7/C10). Never free-form text derived from ``claude`` stderr (C13).
_AUTH_FAIL_REASONS: Final[frozenset[str]] = frozenset({"ambiguous_credential", "no_stored_login", "token_rejected"})

#: Fixed, payload-free message on every auth-probe failure. The actionable signal
#: is the closed-set ``reason``; the message never echoes ``claude`` stderr (C13).
_PROBE_FAILURE_MESSAGE: Final[str] = "the resolved Claude Code credential is not usable"


class ClaudeCodeTool(CodeIntelBackend):
    """A :class:`CodeIntelBackend` that runs a one-shot ``claude`` subprocess.

    Each :meth:`delegate` call spawns a fresh ``claude -p … --output-format
    stream-json`` process, consumes its NDJSON stream, and returns one
    :class:`CodeResult`. The class-level ``description`` concretely satisfies the
    abstract ``description`` property on :class:`CodeIntelBackend`, so the tool is
    accepted anywhere a backend is expected. It never reads ``os.environ``
    (settings own the config) and imports no sibling backend (C3).

    **Read-only enforcement is not owned by a tool-side gate.** Unlike
    ``OpenClaudeTool``, this backend delegates read-only guarding entirely to the
    CLI's own ``--allowedTools`` allowlist, ``permission_mode``, and the mandatory
    disposable scratch cwd (C6.3). There is therefore no ``_check_permission``
    here; the guards live in the argv and in ``ClaudeCodeSettings`` (Task 02.0,
    which rejects ``--dangerously-skip-permissions``).

    **Token accounting is real (C6.2, C9).** ``token_estimate`` is the
    ``usage.input_tokens + usage.output_tokens`` sum from the terminal ``result``
    message, not a length estimate — the field name and ``int`` type are
    unchanged so ``CodeAgent``/``CallBudget`` stay backend-agnostic.

    :cvar name: Stable backend identifier used by ``CodeAgent`` registration.
    :cvar description: Human-readable capability advertised to the agent layer;
        overrides the abstract :class:`CodeIntelBackend` property.
    :ivar _settings: Immutable configuration and allowlists (Task 02.0).
    :ivar _bus: EventBus for ``claude_code.*`` lifecycle/observability emission.
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
        :param bus: EventBus for ``claude_code.*`` emissions.
        :param budget: Per-call boundary :class:`CallBudget`; the pre-check and
            post-charge happen inside :meth:`delegate`.
        """
        self._settings = settings
        self._bus = bus
        self._budget = budget

    async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Delegate *task* to a one-shot ``claude`` process; return a typed result.

        Ordered gates (load-bearing): budget pre-check (no spawn on insufficient
        budget) → ``ctx.dry_run`` short-circuit (no spawn, zero tokens) → the
        timeout-bounded spawn-parse-charge span. The stream span is wrapped in
        :func:`asyncio.wait_for` with ``settings.request_timeout_s``; a timeout, a
        non-zero exit, a missing ``result`` message, a spawn failure, or any
        unexpected error is mapped to a typed failure :class:`CodeResult`. Never
        raises — every path returns a typed result (C13).

        :param task: The open-ended code-navigation prompt (fed to stdin, C6.1).
        :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id``
            and ``dry_run``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        # Step 1 — pre-check BEFORE any spawn; insufficient budget returns a
        # non-retriable failure with ZERO subprocesses spawned.
        if not self._budget.can_afford(self._pre_estimate(task)):
            return self._failure("insufficient_budget", retriable=False)

        # C6.5 — dry-run short-circuits with ZERO spawns and zero tokens; runs
        # AFTER the pre-check so an over-budget dry-run still returns the budget
        # failure.
        if ctx.dry_run:
            return self._dry_run_result()

        try:
            result = await asyncio.wait_for(
                self._run_once(task, ctx),
                timeout=self._settings.request_timeout_s,
            )
            return self._on_result(result, ctx)
        except asyncio.TimeoutError:
            # wait_for cancels _run_once; the async with reaps the child on
            # cancellation (RAII), so no process is orphaned by the timeout.
            return self._on_timeout(ctx)
        except ClaudeCodeUnavailableError as exc:
            return self._on_unavailable(ctx, exc)
        except Exception:
            # Defensive final arm (C13): no exception escapes delegate(); every
            # failure returns a typed CodeResult. Payload-free marker only. This
            # is a must-never-raise resilience boundary (X002 exemption, per
            # OpenClaudeTool). CancelledError is a BaseException and is NOT caught.
            self._emit_error(ctx, error_type="internal_error", code="internal_error")
            return self._failure("internal_error", retriable=False)

    async def probe_auth(self, *, dry_run: bool = False, run_id: Optional[str] = None) -> None:
        """Verify the resolved credential is usable before the first ``delegate()`` (C7).

        Runs a minimal one-shot ``claude`` invocation via
        :class:`ClaudeCodeProcess` (reusing Task 03.0's spawn - argv-safety,
        RAII teardown, filtered subscription env) that forces credential
        resolution without executing an investigation task, bounded by its own
        short :data:`_PROBE_TIMEOUT_S` (independent of ``request_timeout_s``). On
        success returns ``None``.

        On any auth failure it classifies the outcome onto the closed reason
        vocabulary **from exit status and the resolved credential state only -
        never from raw ``claude`` stderr** (C13 / threat model Finding 3b): a
        failure under a stored-login resolution is ``"no_stored_login"``; under a
        forwarded ``CLAUDE_CODE_OAUTH_TOKEN`` (or an ``api_key`` credential) it is
        ``"token_rejected"``; a spawn-time outranking-credential resolution is
        ``"ambiguous_credential"`` (raised by the process env builder). It then
        emits exactly one :class:`ClaudeCodeAuthFailed` carrying only the label
        and raises :class:`ClaudeCodeUnavailableError` with the same label. A
        genuine ``spawn_failed`` (missing binary) is **not** an auth failure and
        propagates unchanged without an ``auth_failed`` event.

        Under *dry_run* the probe short-circuits to success **without spawning any
        process** (C13): a dry-run must never require a live credential. The probe
        is idempotent and safe to call more than once (composition and Task 10.0's
        ``aegis code-intel check``).

        :param dry_run: When ``True``, return immediately without spawning.
        :param run_id: Correlation id for the emitted event; a fresh UUID4 is used
            when omitted.
        :raises ClaudeCodeUnavailableError: When the resolved credential does not
            yield a working session (``"no_stored_login"`` / ``"token_rejected"``
            / ``"ambiguous_credential"``), or when the binary cannot be spawned
            (``"spawn_failed"``, propagated). The message and event carry **no**
            credential value and **no** raw stderr (C7/C13).
        """
        if dry_run:
            return

        rid = run_id if run_id is not None else str(uuid4())
        # Resolve the credential ONCE, up front (C7): the same resolution labels a
        # timeout below and is threaded into _probe_once -> ClaudeCodeProcess for
        # the real env/argv, so label and behaviour cannot diverge (re-review LOW).
        credential = resolve_credential(self._settings)
        try:
            await asyncio.wait_for(self._probe_once(credential), timeout=_PROBE_TIMEOUT_S)
            return
        except asyncio.TimeoutError:
            # A stalled probe means the credential did not resolve to a usable
            # session in time. Branch on the SAME resolved credential state that
            # the non-timeout path uses (never free-form text, C13): a stored-login
            # resolution is "no_stored_login"; a forwarded OAuth token or an
            # api_key credential is "token_rejected" - "no_stored_login" is wrong in
            # api_key mode (no stored-login concept) and misleading for a live
            # api-key timeout.
            reason = "no_stored_login" if credential.relies_on_stored_login else "token_rejected"
        except ClaudeCodeUnavailableError as exc:
            if exc.reason == "spawn_failed":
                # Missing/unspawnable binary is a capability failure, not an auth
                # failure: re-raise unchanged, emit no auth_failed event.
                raise
            reason = exc.reason if exc.reason in _AUTH_FAIL_REASONS else "token_rejected"

        self._bus.publish(ClaudeCodeAuthFailed(run_id=rid, reason=reason, auth_mode=self._settings.auth_mode))
        raise ClaudeCodeUnavailableError(
            _PROBE_FAILURE_MESSAGE,
            binary=self._settings.binary_path,
            reason=reason,
        )

    async def _probe_once(self, credential: ResolvedCredential) -> None:
        """Spawn one probe ``claude`` process and decide usable-vs-auth-failure.

        Spawns the minimal invocation via :class:`ClaudeCodeProcess` under the
        **caller-supplied** *credential* (a single resolution shared with
        :meth:`probe_auth`'s timeout label, re-review LOW; the process performs the
        ``subscription`` spawn-time ambiguous-credential re-check and may raise
        ``reason="ambiguous_credential"``), reduces its stream, and reads the exit
        code. A clean exit with a well-formed, non-error ``result`` message is a
        usable credential (returns ``None``). Any other outcome is an auth failure
        whose reason is derived from the resolved credential state alone -
        ``"no_stored_login"`` when the run relied on a stored login, else
        ``"token_rejected"`` - **never** from ``claude`` stderr (C13).

        :param credential: The single :class:`ResolvedCredential` resolved by
            :meth:`probe_auth`, threaded into the spawn so env/argv and the failure
            label share one resolution.
        :raises ClaudeCodeUnavailableError: On an unusable credential, with a
            closed-set ``reason``; or propagated from the spawn path.
        """
        async with ClaudeCodeProcess(self._settings, _PROBE_TASK, credential=credential) as proc:
            result = await parse_stream(proc.stdout_lines())
            exit_code = await proc.wait_exit()

        if exit_code == 0 and result.usage is not None and not result.is_error:
            return

        reason = "no_stored_login" if credential.relies_on_stored_login else "token_rejected"
        raise ClaudeCodeUnavailableError(
            _PROBE_FAILURE_MESSAGE,
            binary=self._settings.binary_path,
            reason=reason,
        )

    async def _run_once(self, task: str, ctx: CodeTaskContext) -> ClaudeCodeStreamResult:
        """Spawn one ``claude`` process, parse its stream, verify a clean exit.

        Enters :class:`ClaudeCodeProcess` (which feeds *task* over stdin, C6.1),
        emits :class:`ClaudeCodeSpawned`, reduces stdout via :func:`parse_stream`,
        awaits the exit code, then emits the observability tool events and one
        :class:`ClaudeCodeExited`. On a non-zero exit it emits
        ``ClaudeCodeExited(reason="nonzero_exit")`` and raises
        :class:`ClaudeCodeUnavailableError` so :meth:`delegate` maps it to a
        failure. Kept separate from :meth:`delegate` so the whole spawn-parse span
        is the single unit :func:`asyncio.wait_for` bounds.

        :param task: The open-ended prompt (fed to stdin, C6.1).
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :raises ClaudeCodeUnavailableError: On a non-zero child exit code, or when
            the child cannot be spawned (raised from the context manager).
        :return: The reduced :class:`ClaudeCodeStreamResult` on a clean exit.
        """
        async with ClaudeCodeProcess(self._settings, task) as proc:
            self._emit_spawned(ctx)
            result = await parse_stream(proc.stdout_lines())
            exit_code = await proc.wait_exit()

        self._emit_tool_activity(result, ctx)
        if exit_code != 0:
            self._emit_exited(ctx, reason="nonzero_exit", exit_code=exit_code)
            raise ClaudeCodeUnavailableError(
                "the claude one-shot invocation exited non-zero",
                binary=self._settings.binary_path,
                reason="nonzero_exit",
            )
        self._emit_exited(ctx, reason="completed", exit_code=exit_code)
        return result

    def _on_result(self, result: ClaudeCodeStreamResult, ctx: CodeTaskContext) -> CodeResult:
        """Convert a reduced stream into a success or typed-failure result.

        * ``result.usage is None`` (no terminal ``result`` message — the child
          produced no usable result) → non-retriable ``no_result_message``
          failure, zero tokens.
        * ``result.is_error`` set → non-retriable ``result_error`` failure, zero
          tokens.
        * otherwise → charge the **real** ``result.usage.total`` to the budget
          AFTER completion (C6.2, C9), emit :class:`ClaudeCodeCompleted`, and
          return :meth:`_success` with that real ``token_estimate``.

        :param result: The reduced stream from :func:`parse_stream`.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        usage = result.usage
        if usage is None:
            self._emit_error(ctx, error_type="parse_error", code="no_result_message")
            return self._failure("no_result_message", retriable=False)
        if result.is_error:
            self._emit_error(ctx, error_type="parse_error", code="result_error")
            return self._failure("result_error", retriable=False)

        token_estimate = usage.total  # C6.2 / C9 — REAL tokens
        self._budget.charge(token_estimate)  # charged AFTER completion only
        self._bus.publish(
            ClaudeCodeCompleted(
                run_id=str(ctx.run_id),
                token_estimate=token_estimate,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                num_turns=result.num_turns,
            )
        )
        return self._success(
            result.content,
            token_estimate=token_estimate,
            frame_count=result.frame_count,
        )

    def _on_timeout(self, ctx: CodeTaskContext) -> CodeResult:
        """Emit the timeout events and return a retriable ``timeout`` failure.

        A timeout is transient, so the failure is retriable and charges zero
        tokens. The child was reaped on cancellation by the context manager
        (RAII), so no process is orphaned.

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :return: A retriable ``timeout`` failure :class:`CodeResult`.
        """
        self._emit_error(ctx, error_type="timeout", code="DEADLINE_EXCEEDED")
        self._emit_exited(ctx, reason="timeout", exit_code=None)
        return self._failure("timeout", retriable=True)

    def _on_unavailable(self, ctx: CodeTaskContext, exc: ClaudeCodeUnavailableError) -> CodeResult:
        """Map a :class:`ClaudeCodeUnavailableError` to a typed failure result.

        A ``spawn_failed`` reason means the child never started, so no
        :class:`ClaudeCodeSpawned`/:class:`ClaudeCodeExited` pairing was emitted
        by :meth:`_run_once`; this emits the missing ``ClaudeCodeExited`` first.
        A ``nonzero_exit`` reason was already paired with its ``ClaudeCodeExited``
        inside :meth:`_run_once`, so only :class:`ClaudeCodeError` is emitted
        here. Both are non-retriable and charge zero tokens.

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param exc: The raised, payload-free :class:`ClaudeCodeUnavailableError`.
        :return: A non-retriable typed failure :class:`CodeResult`.
        """
        reason = exc.reason or "unavailable"
        if reason == "spawn_failed":
            self._emit_exited(ctx, reason="spawn_failed", exit_code=None)
            self._emit_error(ctx, error_type="spawn_error", code=reason)
        else:
            self._emit_error(ctx, error_type="nonzero_exit", code=reason)
        return self._failure(reason, retriable=False)

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

    def _dry_run_result(self) -> CodeResult:
        """Return the ``[dry-run]`` result: zero tokens, zero spawns (C6.5/C13).

        Short-circuits every external call: no ``claude`` process is spawned and
        the budget is untouched.

        :return: A success :class:`CodeResult` marking a suppressed call.
        """
        return self._success("[dry-run]", token_estimate=0, frame_count=0)

    def _emit_spawned(self, ctx: CodeTaskContext):
        """Emit :class:`ClaudeCodeSpawned` when the one-shot child starts (C10).

        Carries only the run id, the resolved auth mode, and the configured
        binary name — never argv or incident payload (C13).

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        # ``auth_mode`` is always present on a real ``ClaudeCodeSettings`` (C7);
        # ``getattr`` with the ``"auto"`` default keeps Task 03.0's spec-mocked
        # settings (which predate this field) working without change.
        self._bus.publish(
            ClaudeCodeSpawned(
                run_id=str(ctx.run_id),
                auth_mode=getattr(self._settings, "auth_mode", "auto"),
                binary=self._settings.binary_path,
            )
        )

    def _emit_exited(self, ctx: CodeTaskContext, *, reason: str, exit_code: Optional[int]):
        """Emit :class:`ClaudeCodeExited` when the one-shot child is reaped (C10).

        Carries only a payload-free classification and the process return code
        (``None`` when the child never started) — never stderr/stdout text (C13).

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param reason: Short status string (``"completed"``/``"timeout"``/
            ``"spawn_failed"``/``"nonzero_exit"``).
        :param exit_code: The subprocess return code, or ``None`` when unknown.
        """
        self._bus.publish(ClaudeCodeExited(run_id=str(ctx.run_id), reason=reason, exit_code=exit_code))

    def _emit_error(self, ctx: CodeTaskContext, *, error_type: str, code: str):
        """Emit :class:`ClaudeCodeError` on a failure of the call (C10/C13).

        Carries only a classification and a short status code — never the raw
        error text from the ``claude`` process (C13).

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param error_type: Classification (``"timeout"``/``"nonzero_exit"``/
            ``"spawn_error"``/``"parse_error"``/``"internal_error"``).
        :param code: Short, payload-free status code.
        """
        self._bus.publish(ClaudeCodeError(run_id=str(ctx.run_id), error_type=error_type, code=code))

    def _emit_tool_activity(self, result: ClaudeCodeStreamResult, ctx: CodeTaskContext):
        """Emit the per-tool observability events from a reduced stream (C10).

        For each tool-use record emits :class:`ClaudeCodeToolCall`; a tool name
        outside ``settings.allowed_tools`` additionally emits
        :class:`ClaudeCodePermissionDenied` (the CLI attempted a non-allowlisted
        tool). For each tool-result record emits :class:`ClaudeCodeToolResult`.
        Only tool names and counts travel — never tool arguments or output text
        (C13).

        :param result: The reduced stream from :func:`parse_stream`.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        run_id = str(ctx.run_id)
        allowed = set(self._settings.allowed_tools)
        for call in result.tool_calls:
            self._bus.publish(ClaudeCodeToolCall(run_id=run_id, tool=call.tool, arg_count=call.arg_count))
            if call.tool and call.tool not in allowed:
                # ``denied_binary`` is deliberately set to the tool *name* (e.g.
                # "Bash"), not a real binary name: the tool-argument JSON is never
                # retained (C13), so the actual command/binary a "Bash" call would
                # have run does not exist at this point. The event field name
                # predates that constraint; we surface the tool name as the closest
                # payload-free identifier rather than reconstruct a binary we
                # deliberately discarded.
                self._bus.publish(ClaudeCodePermissionDenied(run_id=run_id, tool=call.tool, denied_binary=call.tool))
        for outcome in result.tool_results:
            self._bus.publish(
                ClaudeCodeToolResult(
                    run_id=run_id,
                    tool=outcome.tool,
                    ok=outcome.ok,
                    result_size=outcome.result_size,
                )
            )

    def _failure(self, reason: str, *, retriable: bool) -> CodeResult:
        """Build a typed failure :class:`CodeResult` with a zero token estimate.

        Carries a short non-payload marker; encodes ``{"ok": False, "error":
        reason, "retriable": retriable}`` in ``metadata`` (never raw task/response
        text, C13). ``available=True``: a backend WAS registered — this is a
        per-call failure recorded in metadata (C4).

        :param reason: Short, payload-free failure marker.
        :param retriable: Whether the caller may retry the delegation.
        :return: A typed-failure :class:`CodeResult`.
        """
        return CodeResult(
            content="",
            token_estimate=0,
            available=True,
            truncated=False,
            metadata={"ok": False, "error": reason, "retriable": retriable},
        )

    def _success(self, content: str, *, token_estimate: int, frame_count: int) -> CodeResult:
        """Build a success :class:`CodeResult` carrying observability metadata.

        Sets ``content`` to the accumulated answer, ``token_estimate`` to the real
        ``usage`` sum (C9), and records ``{"ok": True, "frame_count": …}`` in
        ``metadata``. ``truncated`` is always ``False`` for this backend
        (truncation is out of scope for this task).

        :param content: The accumulated assistant answer text.
        :param token_estimate: The real ``usage.input_tokens + output_tokens``.
        :param frame_count: NDJSON frames observed (observability).
        :return: A success :class:`CodeResult`.
        """
        return CodeResult(
            content=content,
            token_estimate=token_estimate,
            available=True,
            truncated=False,
            metadata={"ok": True, "frame_count": frame_count},
        )
