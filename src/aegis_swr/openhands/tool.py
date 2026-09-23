"""The OpenHands :class:`CodeIntelBackend`: sandboxed multi-file navigation.

This module hosts :class:`OpenHandsTool`, a concrete
:class:`~aegis_swr.code_intel.backend.CodeIntelBackend` (contract C8) backed by
the long-lived OpenHands sidecar over REST/WS. It takes an open-ended task
string, delegates it to OpenHands, consumes the Docker-sandboxed runtime's
Action/Observation event stream, and reduces it to a single
:class:`~aegis_swr.code_intel.backend.CodeResult`. There is no multi-tool
selection on the Aegis SWR side (C8).

It is the direct structural sibling of
:class:`~aegis_swr.openclaude.tool.OpenClaudeTool`: the same ``delegate(task,
ctx) -> CodeResult`` seam, the same ordered gates (budget pre-check -> dry-run ->
stream), and the same "never raises; every failure is a typed ``CodeResult``"
guarantee. The one genuine deviation is C9's **dual token-accounting source**:
OpenHands may report real usage on its terminal event, so ``token_estimate`` is
the server-reported figure when present and the boundary estimate
``max(1, len(content) // 4)`` otherwise - either way through the unchanged
``CodeResult.token_estimate`` ``int`` field.

The tool never imports the OpenHands HTTP/WS client library (``socketio`` /
``httpx``); every event type it consumes comes from
:mod:`aegis_swr.openhands.client` (C3). No task text, observation text,
``server_url`` value, or credential ever reaches a log sink, an exception
message, or an event payload - names, sizes, and counts only (C13).

.. note::
   ``delegate`` carries a deliberate final ``except Exception`` catch-all so no
   exception escapes the ``CodeIntelBackend`` boundary (C13). ``asyncio``'s
   ``CancelledError`` is a ``BaseException`` and is therefore **not** caught, so
   cooperative cancellation is preserved. This module is listed in
   ``[tool.flakeforge].exclude`` (pyproject.toml) exactly as
   ``openclaude/tool.py`` and ``claude_code/tool.py`` are, so the custom ``X002``
   rule permits that single, load-bearing catch-all.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import ClassVar, Final, Optional, Union

from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus
from aegis_swr.openhands.client import AgentEvent, EventKind, OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import (
    OpenHandsAction,
    OpenHandsCompleted,
    OpenHandsError,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
)
from aegis_swr.openhands.exceptions import (
    OpenHandsUnavailableError,
    PermissionDeniedError,
)


class _Done:
    """Typed, unique terminal sentinel for the stream-loop dispatch handlers.

    A single module-level instance (:data:`_DONE`) signals normal termination
    from :meth:`OpenHandsTool._consume_stream`'s terminal (``FINISHED``) handler.
    A dedicated singleton type keeps the handler return type honest (a handler
    returns a :class:`CodeResult`, the sentinel, or ``None``) and makes the loop's
    ``isinstance`` break unambiguous: a real :class:`CodeResult` can never be
    mistaken for it. Same pattern as ``OpenClaudeTool._Done`` (0004).
    """


_DONE: Final[_Done] = _Done()

#: Return type shared by every stream-loop event handler: an early-exit
#: :class:`CodeResult`, the terminal :data:`_DONE` sentinel, or ``None`` to
#: continue iterating.
_HandlerResult = Optional[Union[CodeResult, _Done]]


class OpenHandsTool(CodeIntelBackend):
    """A :class:`CodeIntelBackend` delegating open-ended code navigation to the
    Docker-sandboxed OpenHands sidecar over REST/WS and returning one text result.

    There is no multi-tool selection on the Aegis SWR side (C8). The class owns
    an injected client, settings, event bus, and per-call budget; it never reads
    ``os.environ`` and never imports the OpenHands client library directly (C3) -
    every event type it consumes comes from
    :mod:`aegis_swr.openhands.client`. All failure paths return a typed
    :class:`CodeResult`; no exception escapes :meth:`delegate` (C13).

    **Read-only enforcement is not owned by this tool.** OpenHands executes its
    navigation tools inside a Docker sandbox (C8); the container filesystem and
    the runtime's own allowlist are the authoritative read-only boundary. The
    tool-side gate here is *defense in depth plus observability*: it emits
    :class:`OpenHandsAction` / :class:`OpenHandsObservation` for audit and, when
    the runtime surfaces a non-allowlisted action as a ``PERMISSION`` event, emits
    :class:`OpenHandsPermissionDenied` and halts - it does not itself authorize
    sandbox execution.

    :cvar name: Stable backend identifier used by ``CodeAgent`` registration.
    :cvar description: Human-readable capability advertised to the agent layer;
        concretely satisfies the abstract :class:`CodeIntelBackend` property.
    :ivar _client: REST/WS stream adapter; the only path to OpenHands.
    :ivar _settings: Immutable configuration, including the allowlist (C8).
    :ivar _bus: EventBus for ``openhands.*`` observability emissions (C10).
    :ivar _budget: Boundary-level token/cost accounting for one delegated call.
    """

    name: ClassVar[str] = "openhands"
    description: ClassVar[str] = (
        "Open-ended multi-file code navigation backed by OpenHands' own agentic "
        "loop, executed inside a Docker sandbox (Action/Observation event stream)."
    )

    def __init__(
        self,
        client: OpenHandsClient,
        settings: OpenHandsSettings,
        bus: EventBus,
        budget: CallBudget,
    ):
        """Store injected collaborators; open no connection and touch no budget.

        :param client: REST/WS stream adapter that yields normalised
            :class:`~aegis_swr.openhands.client.AgentEvent` frames. Constructing
            the tool starts no traffic (the connection is the sidecar's concern).
        :param settings: OpenHands configuration and allowlist.
        :param bus: EventBus for ``openhands.*`` emissions.
        :param budget: Per-call boundary :class:`CallBudget`. Left untouched here;
            the pre-check/charge happen inside :meth:`delegate`.
        """
        self._client = client
        self._settings = settings
        self._bus = bus
        self._budget = budget

    async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Delegate *task* to OpenHands; return a typed :class:`CodeResult`.

        Ordered gates (load-bearing): budget pre-check (no connection on
        insufficient budget) -> ``ctx.dry_run`` short-circuit (no connection,
        zero tokens) -> the timeout-bounded REST/WS stream. The stream span is
        wrapped in :func:`asyncio.wait_for` with ``settings.request_timeout_s``;
        the client is closed on every path that opened it (RAII). Never raises:
        every failure path returns a typed :class:`CodeResult` (C13).

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id``
            (a :class:`~uuid.UUID`) and ``dry_run``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        # Step 1 - pre-check BEFORE any connection is opened. An insufficient
        # budget returns a non-retriable failure with ZERO REST/WS calls; the
        # pre-check reserves nothing (charge is post-completion only). Optimistic
        # floor, as in OpenClaude: the worst-case post-charge is
        # ~max_response_tokens (~4x this).
        pre_estimate = self._settings.max_response_tokens // 4
        if not self._budget.can_afford(pre_estimate):
            return self._failure("insufficient_budget", retriable=False)

        # C8 - dry-run short-circuits with ZERO network calls and zero tokens.
        # Runs AFTER the pre-check, so an over-budget dry-run still returns the
        # budget failure (pre-check precedence).
        if ctx.dry_run:
            return self._dry_run_result()

        try:
            return await asyncio.wait_for(
                self._consume_stream(task, ctx),
                timeout=self._settings.request_timeout_s,
            )
        except asyncio.TimeoutError:
            # The whole stream exceeded the per-request deadline; transient, so
            # retriable, and it charges zero tokens.
            self._emit_error(ctx, error_type="timeout", code="DEADLINE_EXCEEDED")
            return self._failure("timeout", retriable=True)
        except PermissionDeniedError:
            # Event already emitted in _check_permission.
            return self._failure("permission_denied", retriable=False)
        except OpenHandsUnavailableError as exc:
            self._emit_error(ctx, error_type="transport", code=exc.status_code or "UNAVAILABLE")
            return self._failure("transport_error", retriable=exc.retriable)
        except Exception:
            # Defensive final arm (C13): no exception escapes delegate(); every
            # failure returns a typed CodeResult. Must-never-raise resilience
            # boundary (mirrors OpenClaudeTool's X002-exempt final arm).
            # CancelledError is a BaseException and is deliberately NOT caught.
            self._emit_error(ctx, error_type="internal_error", code="internal_error")
            return self._failure("internal_error", retriable=False)
        finally:
            # RAII: release the REST/WS session on every path that reached the
            # stream, including the failure and timeout arms. ``close`` is
            # idempotent and never surfaces raw transport errors.
            await self._client.close()

    async def _consume_stream(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Consume the OpenHands Action/Observation stream to a single result.

        Iterates the events yielded by ``self._client.run(task,
        str(ctx.run_id))`` (C8): accumulates the assistant's ``MESSAGE`` text (and
        the terminal event's final text) into the result, counts ``ACTION`` /
        ``OBSERVATION`` events for observability metadata, gates a surfaced
        ``PERMISSION`` request against the allowlist, and emits one ``openhands.*``
        event per frame (C10). Returns on the terminal ``FINISHED`` event via
        :meth:`_on_finish`; an ``ERROR`` event exits early via
        :meth:`_on_error_event`.

        The client's :class:`~aegis_swr.openhands.client.AgentEvent` projection is
        closed over the six :class:`~aegis_swr.openhands.client.EventKind` members
        (an unmappable raw kind is surfaced by the client as a terminal ``ERROR``,
        never a foreign kind), so the handler dispatch indexes directly and needs
        no unknown-kind fallthrough.

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation :class:`CodeTaskContext`.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        chunks: list[str] = []
        action_count = 0
        observation_count = 0
        event_count = 0
        server_usage: Optional[int] = None  # server-reported token total; C9

        async def _handle_message(event: AgentEvent) -> _HandlerResult:
            """Accumulate assistant text (never logged, C13)."""
            chunks.append(event.content)
            return None

        async def _handle_action(event: AgentEvent) -> _HandlerResult:
            """Count an ``ACTION`` event and emit its audit event (C10)."""
            nonlocal action_count
            action_count += 1
            self._emit_action(event, ctx)
            return None

        async def _handle_observation(event: AgentEvent) -> _HandlerResult:
            """Count an ``OBSERVATION`` event and emit its audit event (C10)."""
            nonlocal observation_count
            observation_count += 1
            self._emit_observation(event, ctx)
            return None

        async def _handle_permission(event: AgentEvent) -> _HandlerResult:
            """Gate a surfaced ``PERMISSION`` request; may raise (defense in depth)."""
            self._check_permission(event, ctx)  # may raise PermissionDeniedError
            return None

        async def _handle_finished(event: AgentEvent) -> _HandlerResult:
            """Capture terminal server usage, then signal normal termination."""
            nonlocal server_usage
            server_usage = event.token_usage  # None unless the server reported it (C9)
            if event.content:
                chunks.append(event.content)
            return _DONE  # typed sentinel: break from loop

        async def _handle_error(event: AgentEvent) -> _HandlerResult:
            """Handle a terminal ``ERROR`` event; capture the live ``event_count``."""
            return self._on_error_event(ctx, event_count)

        handlers: dict[EventKind, Callable[[AgentEvent], Awaitable[_HandlerResult]]] = {
            EventKind.MESSAGE: _handle_message,
            EventKind.ACTION: _handle_action,
            EventKind.OBSERVATION: _handle_observation,
            EventKind.PERMISSION: _handle_permission,
            EventKind.FINISHED: _handle_finished,
            EventKind.ERROR: _handle_error,
        }

        async for event in self._client.run(task, str(ctx.run_id)):
            event_count += 1
            result = await handlers[event.kind](event)
            if isinstance(result, _Done):
                break  # narrows the sentinel out of the union below
            if result is not None:
                return result  # early exit (terminal ERROR)

        content = "".join(chunks)
        return self._on_finish(
            content,
            ctx,
            server_usage=server_usage,
            action_count=action_count,
            observation_count=observation_count,
            event_count=event_count,
        )

    def _emit_action(self, event: AgentEvent, ctx: CodeTaskContext):
        """Emit :class:`OpenHandsAction` for an ``ACTION`` event (C10).

        Carries only the run id, the action/tool name, and a derived argument
        count - never the raw action content, which may echo incident payload
        (C13).

        :param event: The ``ACTION`` event; ``event.tool`` names the action type
            and ``event.content`` holds the (never-emitted) argument summary.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        self._bus.publish(
            OpenHandsAction(
                run_id=str(ctx.run_id),
                action=event.tool or "",
                arg_count=self._arg_count(event.content),
            )
        )

    def _emit_observation(self, event: AgentEvent, ctx: CodeTaskContext):
        """Emit :class:`OpenHandsObservation` for an ``OBSERVATION`` event (C10).

        Carries only the run id, the observation/tool name, a success flag, and
        the output size (a count) - never the raw observation content, which may
        contain incident payload (C13). ``ok`` is ``True`` here because a distinct
        ``ERROR`` event conveys failure at this layer (mirrors OpenClaude).

        :param event: The ``OBSERVATION`` event; ``event.content`` holds the
            (never-emitted) observation output.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        self._bus.publish(
            OpenHandsObservation(
                run_id=str(ctx.run_id),
                observation=event.tool or "",
                ok=True,
                content_size=len(event.content),
            )
        )

    def _check_permission(self, event: AgentEvent, ctx: CodeTaskContext):
        """Allow an allowlisted ``PERMISSION`` request; deny anything else.

        Defense in depth over the sandbox (the container is the authoritative
        guard, C8). The client surfaces a confirmation-gated or non-allowlisted
        action as a ``PERMISSION`` event; when its tool is not in
        ``settings.allowed_tools``, emit :class:`OpenHandsPermissionDenied` and
        raise so the invocation halts read-only. :meth:`delegate` maps the raise
        to a non-retriable failure. Only the action/tool name (never its
        arguments) is placed on the event and exception (C13).

        :param event: The ``PERMISSION`` event; ``event.tool`` names the type.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :raises PermissionDeniedError: When the requested tool is not allowlisted.
        """
        tool = event.tool or ""
        if tool in self._settings.allowed_tools:
            return
        # ``denied_binary`` is deliberately the tool NAME: the action arguments
        # (which would name a real binary) are never retained (C13), so the tool
        # name is the closest payload-free identifier.
        self._bus.publish(
            OpenHandsPermissionDenied(
                run_id=str(ctx.run_id),
                action=tool,
                denied_binary=tool,
            )
        )
        raise PermissionDeniedError(action=tool, denied_binary=tool)

    @staticmethod
    def _arg_count(content: str) -> int:
        """Count action arguments without exposing the payload (C13).

        Parses *content* as JSON and returns the number of top-level members of a
        JSON object or array; non-JSON or scalar content yields ``0``. The parsed
        content is never logged or emitted - only the count leaves this method.

        :param content: The ``ACTION`` event's argument summary (never emitted).
        :return: The top-level argument count, or ``0`` when indeterminate.
        """
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return 0
        return len(parsed) if isinstance(parsed, (dict, list)) else 0

    def _dry_run_result(self) -> CodeResult:
        """Return the ``[dry-run]`` result with a zero token estimate (C8/C13).

        Short-circuits every external call: no ``client.run`` is issued and the
        budget is untouched. ``content`` is a fixed non-payload marker and
        ``token_estimate`` is ``0``.

        :return: A success :class:`CodeResult` marking a suppressed call.
        """
        return self._success(
            "[dry-run]",
            truncated=False,
            token_estimate=0,
            action_count=0,
            observation_count=0,
            event_count=0,
        )

    def _on_finish(
        self,
        content: str,
        ctx: CodeTaskContext,
        *,
        server_usage: Optional[int],
        action_count: int,
        observation_count: int,
        event_count: int,
    ) -> CodeResult:
        """Resolve tokens, truncate, charge, emit completion, and succeed.

        Runs only on the clean ``FINISHED`` success path. Truncates the
        accumulated text, resolves ``token_estimate`` on the *truncated* text (C9
        - server usage if present, else the boundary estimate), charges the budget
        AFTER the stream (never pre-charged), and emits the sole event carrying
        the token figure (:class:`OpenHandsCompleted`, C10).

        :param content: The accumulated assistant-text concatenation.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param server_usage: Server-reported token total captured on the
            ``FINISHED`` event, or ``None`` when the server reported none (C9).
        :param action_count: Number of ``ACTION`` events observed.
        :param observation_count: Number of ``OBSERVATION`` events observed.
        :param event_count: Total number of events observed in the stream.
        :return: A success :class:`CodeResult` with observability metadata.
        """
        text, truncated = self._truncate(content)
        token_estimate = self._resolve_token_estimate(text, server_usage)  # C9
        usage_reported = server_usage is not None
        self._budget.charge(token_estimate)  # charged AFTER stream, success only
        self._bus.publish(
            OpenHandsCompleted(
                run_id=str(ctx.run_id),
                token_estimate=token_estimate,
                usage_reported=usage_reported,
                event_count=event_count,
                truncated=truncated,
            )
        )
        return self._success(
            text,
            truncated=truncated,
            token_estimate=token_estimate,
            action_count=action_count,
            observation_count=observation_count,
            event_count=event_count,
        )

    def _resolve_token_estimate(self, content: str, server_usage: Optional[int]) -> int:
        """Resolve ``CodeResult.token_estimate`` from real usage or the estimate (C9).

        Prefers the server-reported real usage when the stream carried it;
        otherwise falls back to the boundary estimate ``max(1, len(content) // 4)``
        - the same OpenClaude convention. Either way the return is a plain ``int``
        on the unchanged ``token_estimate`` field, so ``CodeAgent`` / ``CallBudget``
        stay fully backend-agnostic (C9 hard invariant).

        :param content: The accumulated (already truncated) response text.
        :param server_usage: Real token total from the terminal event, or ``None``.
        :return: ``server_usage`` when present, else ``max(1, len(content) // 4)``.
        """
        if server_usage is not None:
            return server_usage
        return max(1, len(content) // 4)

    def _on_error_event(self, ctx: CodeTaskContext, event_count: int) -> CodeResult:
        """Handle a terminal ``ERROR`` event: emit and fail non-retriably (C13).

        Emits :class:`OpenHandsError` carrying only a classification, a status
        code, and the event count (never the raw error text, C13), then returns a
        non-retriable failure. The budget is untouched: an ``ERROR`` event charges
        zero tokens.

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param event_count: Number of events consumed up to and including the
            terminal ``ERROR`` event.
        :return: A non-retriable failure :class:`CodeResult`.
        """
        self._bus.publish(
            OpenHandsError(
                run_id=str(ctx.run_id),
                error_type="stream_error",
                code="error_event",
                event_count=event_count,
            )
        )
        return self._failure("stream_error", retriable=False)

    def _emit_error(self, ctx: CodeTaskContext, *, error_type: str, code: str):
        """Emit :class:`OpenHandsError` on a delegate-level failure (C10/C13).

        Carries only a classification, a short status code, and a zero
        ``event_count`` (the count is lost once the exception unwinds the stream
        loop) - never the raw error text, which may echo payload (C13).

        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :param error_type: Classification (``"timeout"`` / ``"transport"`` /
            ``"internal_error"``).
        :param code: Short, payload-free status code.
        """
        self._bus.publish(
            OpenHandsError(
                run_id=str(ctx.run_id),
                error_type=error_type,
                code=code,
                event_count=0,
            )
        )

    def _truncate(self, content: str) -> tuple[str, bool]:
        """Clamp *content* to ``settings.max_response_tokens`` (character-equivalent).

        Uses the same ``// 4`` char/token approximation as the boundary estimate,
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

        Carries an empty non-payload ``content``, ``token_estimate=0``, and encodes
        ``{"ok": False, "error": reason, "retriable": retriable}`` in ``metadata``
        (never raw payload text, C13). ``available=True``: a backend WAS
        registered; this is a per-call failure recorded in metadata (C4), not an
        unavailable-capability result.

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

    def _success(
        self,
        content: str,
        *,
        truncated: bool,
        token_estimate: int,
        action_count: int,
        observation_count: int,
        event_count: int,
    ) -> CodeResult:
        """Build a success :class:`CodeResult` carrying observability metadata.

        Records ``{"ok": True, "action_count": ..., "observation_count": ...,
        "event_count": ...}`` in ``metadata`` (counts only, never payload, C13).

        :param content: The accumulated (already truncated) response text.
        :param truncated: Whether ``content`` was clipped at the response cap.
        :param token_estimate: Resolved token estimate for the call (C9).
        :param action_count: Number of ``ACTION`` events observed.
        :param observation_count: Number of ``OBSERVATION`` events observed.
        :param event_count: Total number of events observed in the stream.
        :return: A success :class:`CodeResult`.
        """
        return CodeResult(
            content=content,
            token_estimate=token_estimate,
            available=True,
            truncated=truncated,
            metadata={
                "ok": True,
                "action_count": action_count,
                "observation_count": observation_count,
                "event_count": event_count,
            },
        )
