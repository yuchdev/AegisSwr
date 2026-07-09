"""The sole :class:`CodeBackend`: the OpenClaude code-navigation tool.

This module hosts :class:`OpenClaudeTool`, the single concrete
:class:`~aegis_swr.code_intel.backend.CodeBackend` in Milestone 0004. It
delegates an open-ended, multi-file code-navigation task to the OpenClaude
sidecar over gRPC and returns one :class:`~aegis_swr.code_intel.backend.CodeResult`.

There is no multi-tool selection on the Aegis SWR side (C4). The tool owns an
injected gRPC client, settings, event bus, and per-call budget; it never reads
``os.environ`` and never reaches for the transport stubs directly (C3) - every
frame type it needs is taken from the typed client module
:mod:`aegis_swr.openclaude.grpc.client`. All failure paths return a typed
:class:`~aegis_swr.code_intel.backend.CodeResult`; no exception escapes
:meth:`OpenClaudeTool.delegate` (C9).

This subtask (04.0/01) stands up the construction and the protocol-conformant
surface only; the stream loop, permission/tool handling, budget pre-check,
dry-run, and truncation land in subtasks 02-04 without changing these
signatures.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from typing import ClassVar, Final, Optional, Union

from aegis_swr.code_intel.backend import CodeBackend, CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.events import (
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
)
from aegis_swr.openclaude.exceptions import (
    OpenClaudeUnavailableError,
    PermissionDeniedError,
)
from aegis_swr.openclaude.grpc.client import (
    AgentFrame,
    FrameKind,
    OpenClaudeGrpcClient,
)

# Shell metacharacters that, if present anywhere in a requested command, force a
# permission DENY before the allowlist is consulted (Fix 3 - defense in depth).
# Any of these enables command chaining, substitution, redirection, or grouping
# that would let an allowlisted first token smuggle a non-allowlisted action
# (e.g. ``rg; curl evil``, ``rg $(curl x)``, ``rg | sh``).
_SHELL_METACHARACTERS: Final[frozenset[str]] = frozenset(
    {";", "&", "|", "$", "`", "\n", "\r", "(", ")", "{", "}", "<", ">"}
)


class _Done:
    """Typed, unique terminal sentinel for the stream-loop dispatch handlers.

    A single module-level instance (:data:`_DONE`) signals normal termination
    from :meth:`OpenClaudeTool._consume_stream`'s ``DONE`` handler. Using a
    dedicated singleton type - rather than the former ``"DONE"`` string - keeps
    the handler return type honest (a handler returns a :class:`CodeResult`, the
    sentinel, or ``None``) and makes the loop's ``is``-identity break
    unambiguous: a real :class:`CodeResult` can never be mistaken for it.
    """


_DONE: Final[_Done] = _Done()

#: Return type shared by every stream-loop frame handler: an early-exit
#: :class:`CodeResult`, the terminal :data:`_DONE` sentinel, or ``None`` to
#: continue iterating.
_HandlerResult = Optional[Union[CodeResult, _Done]]


class OpenClaudeTool(CodeBackend):
    """The sole :class:`CodeBackend`: delegate an open-ended code-navigation
    task to the OpenClaude sidecar over gRPC and return a single text result.

    There is no multi-tool selection on the Aegis SWR side (C4). The class owns
    an injected gRPC client, settings, event bus, and per-call budget; it never
    reads ``os.environ`` and never imports ``grpc`` (C3). All failure paths
    return a typed :class:`CodeResult`; no exception escapes :meth:`delegate`
    (C9).

    The class-level ``description`` attribute concretely satisfies the abstract
    ``description`` property declared on :class:`CodeBackend`, so the tool is an
    instantiable backend accepted anywhere a :class:`CodeBackend` is expected.

    **Read-only enforcement is not owned by this gate.** The authoritative
    read-only boundary is the OpenClaude sidecar's own launch-flag allowlist
    (``--allowed-tools`` / the sidecar bash allowlist in managed mode); that
    is what actually authorizes or refuses tool execution. The tool-side
    permission check here (:meth:`_check_permission`) is *defense in depth plus
    observability*: an additional filter and the source of the audit
    :class:`OpenClaudePermissionDenied` event. It does not itself authorize
    sidecar execution and must not be relied on as the sole guarantee that
    OpenClaude cannot mutate the repository. In external mode (a sidecar started
    without Aegis-managed launch flags) this tool-side gate may be the only
    Aegis-visible check, which is exactly why it is hardened against shell
    metacharacter and path-confusion bypasses (Fix 3).

    :cvar name: Stable backend identifier used by ``CodeAgent`` registration.
    :cvar description: Human-readable capability advertised to the agent layer;
        overrides the abstract :class:`CodeBackend` property.
    :ivar _client: gRPC stream adapter (task 02.0); the only path to OpenClaude.
    :ivar _settings: Immutable configuration, including the allowlists (C1).
    :ivar _bus: EventBus for per-frame observability emissions (C8).
    :ivar _budget: Boundary-level token/cost accounting for one delegated call.
    """

    name: ClassVar[str] = "openclaude"
    description: ClassVar[str] = (
        "Open-ended multi-file code navigation backed by OpenClaude's own "
        "agentic loop (Read/Grep/Glob/Bash over the repository under analysis)."
    )

    def __init__(
        self,
        client: OpenClaudeGrpcClient,
        settings: OpenClaudeSettings,
        bus: EventBus,
        budget: CallBudget,
    ) -> None:
        """Store injected collaborators; open no connection and touch no budget.

        :param client: gRPC stream adapter that yields parsed
            :class:`~aegis_swr.openclaude.grpc.client.AgentFrame` frames (task
            02.0). The gRPC channel is created lazily on first ``query()``, so
            construction starts no process.
        :param settings: OpenClaude configuration and allowlists (task 01.0).
        :param bus: EventBus for ``openclaude.*`` emissions (task 05.0 events).
        :param budget: Per-call boundary :class:`CallBudget` (task 06.0). Left
            untouched here; the pre-check/charge happen inside :meth:`delegate`.
        """
        self._client = client
        self._settings = settings
        self._bus = bus
        self._budget = budget

    async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Delegate *task* to OpenClaude and return a single text result.

        Public :class:`CodeBackend` entry point. Behaviour is layered across
        subtasks 02-04: stream iteration and content accumulation (02),
        permission and tool-event handling (03), and budget pre-check /
        dry-run / truncation / terminal-frame handling (04). Orchestration -
        the budget pre-check, ``ctx.dry_run`` short-circuit, delegation to
        :meth:`_consume_stream`, and post-charge - lands in subtask 04. Never
        raises: every failure path returns a typed :class:`CodeResult` (C9).

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id``
            (a :class:`~uuid.UUID`) and ``dry_run``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        # C5 step 1 - pre-check BEFORE any connection is opened. An
        # insufficient budget returns a non-retriable failure with ZERO gRPC
        # calls; the pre-check reserves nothing (charge is post-completion only).
        # NOTE: this is an OPTIMISTIC pre-check, not a conservative one - the
        # actual worst-case post-completion charge is ~max_response_tokens
        # (the truncation cap), roughly 4x this ``// 4`` pre-estimate. It only
        # rejects calls that cannot afford even the optimistic floor.
        pre_estimate = self._settings.max_response_tokens // 4
        if not self._budget.can_afford(pre_estimate):
            return self._failure("insufficient_budget", retriable=False)

        # C9 - dry-run short-circuits with ZERO gRPC calls and zero tokens. It
        # runs AFTER the pre-check, so an over-budget dry-run still returns the
        # budget failure (pre-check precedence).
        if ctx.dry_run:
            return self._dry_run_result()

        try:
            return await self._consume_stream(task, ctx)
        except PermissionDeniedError:
            # Event already emitted in _check_permission (subtask 03).
            return self._failure("permission_denied", retriable=False)
        except OpenClaudeUnavailableError as exc:
            self._bus.publish(
                OpenClaudeStreamError(
                    run_id=str(ctx.run_id),
                    error_type="grpc_status",
                    code=exc.status_code or "UNAVAILABLE",
                    frame_count=0,
                )
            )
            return self._failure("grpc_error", retriable=exc.retriable)
        except Exception:
            # Defensive final arm (C9): no exception escapes delegate(); every
            # failure returns a typed CodeResult. This is a must-never-raise
            # resilience boundary (see the X002 exemption in pyproject.toml).
            return self._failure("internal_error", retriable=False)

    async def _consume_stream(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Open the stream and consume frames to a result (subtasks 02-04).

        Iterates the frames yielded by ``self._client.query(task,
        str(ctx.run_id))``, accumulating text, handling tool/permission frames,
        and reducing the stream to a single :class:`CodeResult`. Renamed from
        the spec's ``_delegate`` to avoid a near-collision with the public
        :meth:`delegate`.

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation :class:`CodeTaskContext`.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        chunks: list[str] = []
        tool_call_count = 0
        tool_result_count = 0
        frame_count = 0

        async def _handle_text_chunk(msg: AgentFrame) -> _HandlerResult:
            """Accumulate a ``TEXT_CHUNK`` frame's payload (never logged, C9)."""
            chunks.append(msg.content)
            return None

        async def _handle_tool_call(msg: AgentFrame) -> _HandlerResult:
            """Count a ``TOOL_CALL`` frame and emit its observability event (03)."""
            nonlocal tool_call_count
            tool_call_count += 1
            self._emit_tool_call(msg, ctx)  # subtask 03
            return None

        async def _handle_tool_result(msg: AgentFrame) -> _HandlerResult:
            """Count a ``TOOL_RESULT`` frame and emit its observability event (03)."""
            nonlocal tool_result_count
            tool_result_count += 1
            self._emit_tool_result(msg, ctx)  # subtask 03
            return None

        async def _handle_permission_req(msg: AgentFrame) -> _HandlerResult:
            """Gate a ``PERMISSION_REQ`` frame; may raise/deny in subtask 03."""
            self._check_permission(msg, ctx)  # subtask 03 (may raise)
            return None

        async def _handle_done(msg: AgentFrame) -> _HandlerResult:
            """Signal normal termination via the typed :data:`_DONE` sentinel."""
            return _DONE  # typed sentinel: break from loop

        async def _handle_error(msg: AgentFrame) -> _HandlerResult:
            """Handle a terminal ``ERROR`` frame; capture the live ``frame_count``.

            Closes over ``frame_count`` so the emitted
            :class:`OpenClaudeStreamError` carries the number of frames observed
            up to and including this terminal error.
            """
            return self._on_error_frame(ctx, frame_count)

        handlers: dict[FrameKind, Callable[[AgentFrame], Awaitable[_HandlerResult]]] = {
            FrameKind.TEXT_CHUNK: _handle_text_chunk,
            FrameKind.TOOL_CALL: _handle_tool_call,
            FrameKind.TOOL_RESULT: _handle_tool_result,
            FrameKind.PERMISSION_REQ: _handle_permission_req,
            FrameKind.DONE: _handle_done,
            FrameKind.ERROR: _handle_error,  # subtask 04
        }

        async for msg in self._client.query(task, str(ctx.run_id)):
            frame_count += 1
            handler = handlers.get(msg.frame_type)
            if handler is None:
                continue  # unknown frame type; skip silently
            result = await handler(msg)
            if result is _DONE:
                break  # identity check on the typed terminal sentinel
            elif result is not None:
                return result  # early exit (error or other terminal state)

        content = "".join(chunks)
        # C5: truncate, charge the boundary estimate, emit completion, succeed.
        return self._on_done(
            content,
            ctx,
            tool_call_count=tool_call_count,
            tool_result_count=tool_result_count,
            frame_count=frame_count,
        )

    def _emit_tool_call(self, msg: AgentFrame, ctx: CodeTaskContext) -> None:
        """Emit :class:`OpenClaudeToolCall` for a ``TOOL_CALL`` frame (C8).

        Carries only the run id, the tool name, and a derived argument count -
        never the raw ``msg.content`` args JSON, which may echo incident payload
        (C9).

        :param msg: The ``TOOL_CALL`` frame; ``msg.tool`` names the invoked tool
            and ``msg.content`` holds the (never-emitted) args JSON.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        self._bus.publish(
            OpenClaudeToolCall(
                run_id=str(ctx.run_id),
                tool=msg.tool or "",
                arg_count=self._arg_count(msg.content),
            )
        )

    def _emit_tool_result(self, msg: AgentFrame, ctx: CodeTaskContext) -> None:
        """Emit :class:`OpenClaudeToolResult` for a ``TOOL_RESULT`` frame (C8).

        Carries only the run id, the tool name, a success flag, and the output
        size (a count) - never the raw ``msg.content`` output text, which may
        contain incident payload (C9). ``ok`` is ``True`` here because a distinct
        ``ERROR`` frame conveys failure at this layer.

        :param msg: The ``TOOL_RESULT`` frame; ``msg.content`` holds the
            (never-emitted) tool output.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        self._bus.publish(
            OpenClaudeToolResult(
                run_id=str(ctx.run_id),
                tool=msg.tool or "",
                ok=True,
                result_size=len(msg.content),
            )
        )

    @staticmethod
    def _arg_count(content: str) -> int:
        """Count tool-call arguments without exposing the payload (C9).

        Parses *content* as JSON and returns the number of top-level members of
        a JSON object or array; any content that is not JSON, or is a JSON
        scalar, yields ``0``. The parsed content is never logged or emitted -
        only the count leaves this method.

        :param content: The ``TOOL_CALL`` frame's args JSON (never emitted).
        :return: The top-level argument count, or ``0`` when indeterminate.
        """
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return 0
        return len(parsed) if isinstance(parsed, (dict, list)) else 0

    def _check_permission(self, msg: AgentFrame, ctx: CodeTaskContext) -> None:
        """Allow an allowlisted ``PERMISSION_REQ``; deny anything else (C7).

        Auto-approval is implicit: an allowlisted command returns and stream
        iteration continues (the approval handshake back to OpenClaude is the
        gRPC client's concern, task 02.0). A non-allowlisted command emits
        :class:`OpenClaudePermissionDenied` and raises so the invocation halts
        read-only; :meth:`delegate` maps the raise to a non-retriable failure.
        The deny path never mutates :attr:`_budget` (C5/C7).

        Only the offending binary name (never the full command line) is placed
        on the event and the exception (C9).

        :param msg: The ``PERMISSION_REQ`` frame; ``msg.content`` carries the
            requested command.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :raises PermissionDeniedError: When the command's binary is not in
            ``settings.bash_allowlist``.
        """
        command = self._requested_command(msg)
        if self._is_allowlisted(command):
            return
        denied_binary = self._binary_of(command)
        tool = msg.tool or "Bash"
        self._bus.publish(
            OpenClaudePermissionDenied(
                run_id=str(ctx.run_id),
                tool=tool,
                denied_binary=denied_binary,
            )
        )
        raise PermissionDeniedError(tool=tool, denied_binary=denied_binary)

    def _requested_command(self, msg: AgentFrame) -> str:
        """Return the requested command string from a ``PERMISSION_REQ`` frame.

        :param msg: The ``PERMISSION_REQ`` frame; ``msg.content`` is the command.
        :return: The requested shell command string.
        """
        return msg.content

    @staticmethod
    def _binary_of(command: str) -> str:
        """Reduce *command* to the basename of its first whitespace token.

        Shared by :meth:`_is_allowlisted` and :meth:`_check_permission` so the
        allowlist decision and the recorded ``denied_binary`` derive from the
        exact same binary. A command with no extractable token yields ``""``.

        :param command: The requested shell command (e.g. ``"/usr/bin/rg foo"``).
        :return: The basename of the leading token, or ``""`` when none exists.
        """
        tokens = command.split()
        if not tokens:
            return ""
        return os.path.basename(tokens[0])

    def _dry_run_result(self) -> CodeResult:
        """Return the ``[dry-run]`` result with a zero token estimate (C5/C9).

        Short-circuits every external call: no gRPC ``query`` is issued and the
        budget is untouched. The ``content`` marker is a fixed non-payload
        string and ``token_estimate`` is ``0`` (a dry run charges nothing).

        :return: A success :class:`CodeResult` marking a suppressed call.
        """
        return self._success(
            "[dry-run]",
            truncated=False,
            token_estimate=0,
            tool_call_count=0,
            tool_result_count=0,
            frame_count=0,
        )

    def _on_done(
        self,
        content: str,
        ctx: CodeTaskContext,
        *,
        tool_call_count: int,
        tool_result_count: int,
        frame_count: int,
    ) -> CodeResult:
        """Truncate, charge the boundary estimate, emit completion, succeed.

        Runs only on the clean ``DONE`` success path. Truncates the accumulated
        text (C5 step 4), computes the boundary ``token_estimate`` on the
        *truncated* text so it never exceeds the cap (C5 step 2), charges the
        budget AFTER the stream (never pre-charged), and emits the sole event
        carrying ``token_estimate`` (:class:`OpenClaudeStreamCompleted`, C8).

        :param content: The accumulated ``TEXT_CHUNK`` concatenation.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param tool_call_count: Number of ``TOOL_CALL`` frames observed.
        :param tool_result_count: Number of ``TOOL_RESULT`` frames observed.
        :param frame_count: Total number of frames observed in the stream.
        :return: A success :class:`CodeResult` with observability metadata.
        """
        text, truncated = self._truncate(content)  # C5 step 4
        token_estimate = max(1, len(text) // 4)  # C5 step 2
        self._budget.charge(token_estimate)  # charged AFTER stream, success only
        self._bus.publish(
            OpenClaudeStreamCompleted(
                run_id=str(ctx.run_id),
                token_estimate=token_estimate,
                frame_count=frame_count,
                truncated=truncated,
            )
        )
        return self._success(
            text,
            truncated=truncated,
            token_estimate=token_estimate,
            tool_call_count=tool_call_count,
            tool_result_count=tool_result_count,
            frame_count=frame_count,
        )

    def _on_error_frame(self, ctx: CodeTaskContext, frame_count: int) -> CodeResult:
        """Handle a terminal ``ERROR`` frame: emit and fail non-retriably (C5/C9).

        Emits :class:`OpenClaudeStreamError` carrying only a classification, a
        status code, and the frame count (never the raw error text, C9), then
        returns a non-retriable failure. The budget is untouched: an ``ERROR``
        frame charges zero tokens (C5).

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param frame_count: Number of frames consumed up to and including the
            terminal ``ERROR`` frame.
        :return: A non-retriable failure :class:`CodeResult`.
        """
        self._bus.publish(
            OpenClaudeStreamError(
                run_id=str(ctx.run_id),
                error_type="stream_error",
                code="error_frame",
                frame_count=frame_count,
            )
        )
        return self._failure("stream_error", retriable=False)

    @staticmethod
    def _is_safe_command(command: str) -> bool:
        """Pre-filter denying shell-metacharacter and path-qualified commands.

        Runs BEFORE the basename/allowlist check so that a benign-looking
        allowlisted first token cannot smuggle a non-allowlisted action. A
        command is unsafe (returns ``False``) when either:

        * it contains ANY character in :data:`_SHELL_METACHARACTERS`
          (``; & | $ `` `` \n \r ( ) { } < >``) - these enable command
          chaining, substitution, redirection, or grouping (e.g. ``rg; curl
          evil``, ``rg $(curl x)``, ``rg | sh``, backticks, embedded newlines);
          or
        * its FIRST whitespace token contains ``/`` - a path-qualified binary
          (e.g. ``../../bin/rg`` or ``/usr/bin/rg``). Allowlist entries are bare
          names, so a path-qualified invocation is denied to defeat
          path-confusion bypasses. Only the first token is checked, so an
          allowlisted binary whose later arguments carry ``/`` (e.g. ``find src
          -name x``, ``cat file``) still passes.

        :param command: The requested shell command.
        :return: ``True`` iff *command* carries no metacharacters and its first
            token is a bare (non-path) name.
        """
        if any(ch in command for ch in _SHELL_METACHARACTERS):
            return False
        tokens = command.split()
        if not tokens:
            return False
        return "/" not in tokens[0]

    def _is_allowlisted(self, command: str) -> bool:
        """Return whether *command*'s binary is in ``settings.bash_allowlist``.

        First applies :meth:`_is_safe_command`: a command carrying any shell
        metacharacter, or whose first token is path-qualified (contains ``/``),
        is denied outright - regardless of its basename - to defeat command
        chaining, substitution, redirection, and path-confusion bypasses. A
        command with no extractable token (empty/whitespace) is likewise denied
        by that pre-filter. Only then does it take the first whitespace-delimited
        token, reduce it to its basename, and test exact, case-sensitive
        membership against ``settings.bash_allowlist``. Because a safe command
        always has a non-empty, non-path first token, its basename is always
        non-empty here.

        :param command: The requested shell command (e.g. ``"rg -n foo src/"``).
        :return: ``True`` iff *command* is safe and its leading token's basename
            is allowlisted.
        """
        if not self._is_safe_command(command):
            return False
        binary = self._binary_of(command)
        return binary in self._settings.bash_allowlist

    def _truncate(self, content: str) -> tuple[str, bool]:
        """Clamp *content* to ``settings.max_response_tokens`` (C5 step 4).

        Uses the same ``//4`` char/token approximation as the budget estimate,
        so the character clamp is ``max_response_tokens * 4``. Content within the
        clamp is returned unchanged; longer content is clipped and flagged.

        :param content: The accumulated response text.
        :return: ``(possibly_truncated_content, was_truncated)``.
        """
        clamp = self._settings.max_response_tokens * 4
        if len(content) <= clamp:
            return content, False
        return content[:clamp], True

    def _failure(self, reason: str, *, retriable: bool) -> CodeResult:
        """Build a typed failure :class:`CodeResult` with a zero token estimate.

        The returned result carries a short non-payload marker in ``content``,
        ``token_estimate=0``, and encodes ``{"ok": False, "error": reason,
        "retriable": retriable}`` in ``metadata`` (never raw payload text, C9).
        Body implemented in a later subtask.

        :param reason: Short, payload-free failure marker.
        :param retriable: Whether the caller may retry the delegation.
        :return: A typed-failure :class:`CodeResult`.
        """
        # available=True: a backend WAS registered; this is a per-call failure
        # recorded in metadata (C4). token_estimate=0: failures charge nothing.
        return CodeResult(
            content="",
            token_estimate=0,
            available=True,
            truncated=False,
            metadata={"ok": False, "error": reason, "retriable": retriable},
        )

    def _success(
        self,
        content: str,
        *,
        truncated: bool,
        token_estimate: int,
        tool_call_count: int,
        tool_result_count: int,
        frame_count: int,
    ) -> CodeResult:
        """Build a success :class:`CodeResult` carrying observability metadata.

        The returned result sets ``content`` to the accumulated text and records
        ``{"ok": True, "tool_call_count": ..., "tool_result_count": ...,
        "frame_count": ...}`` in ``metadata``. Body implemented in a later
        subtask.

        :param content: The accumulated (already truncated) response text.
        :param truncated: Whether ``content`` was clipped at the response cap.
        :param token_estimate: Boundary token estimate for the call.
        :param tool_call_count: Number of ``TOOL_CALL`` frames observed.
        :param tool_result_count: Number of ``TOOL_RESULT`` frames observed.
        :param frame_count: Total number of frames observed in the stream.
        :return: A success :class:`CodeResult`.
        """
        return CodeResult(
            content=content,
            token_estimate=token_estimate,
            available=True,
            truncated=truncated,
            metadata={
                "ok": True,
                "tool_call_count": tool_call_count,
                "tool_result_count": tool_result_count,
                "frame_count": frame_count,
            },
        )
