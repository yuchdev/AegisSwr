# 01 - Tool skeleton + Action/Observation stream consumption

**Parent task:** 08.0 OpenHands Tool Implementor
**State:** ⬜ Not started
**Depends on:** 07.0 (`openhands/client.py`, `openhands/process.py`)
**Blocks:** 02

## Objective

Stand up `aegis_swr/openhands/tool.py` with the `OpenHandsTool` class shell and
its core stream loop. This subtask defines construction and the
protocol-conformant surface (the injected collaborators, `name` / `description`,
the public `delegate()` entry declared but not orchestrated), and it fleshes out
`_consume_stream()` — the loop that iterates the OpenHands **Action/Observation
event stream** from `client.stream(task, run_id)`, accumulates the assistant's
text up to the terminal event, emits an `EventBus` event per action/observation
(C10), and reduces the stream to a preliminary `CodeResult`. The budget
pre-check, the `ctx.dry_run` short-circuit, token-estimate resolution, the
`OpenHandsStreamCompleted` emission, and truncation are layered onto the same
loop by subtask 02 **without changing its shape**. Keep every event-kind branch
a single flat handler arm so the 100%-branch bar (task 11.0) stays tractable.

This mirrors `OpenClaudeTool._consume_stream` (0004 task 04.0, subtask 02)
structurally — a `dict[EventKind, handler]` dispatch with a typed terminal
sentinel — adapted for OpenHands' Action/Observation vocabulary instead of
gRPC frames.

## File: `aegis_swr/openhands/tool.py`

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import ClassVar, Final, Optional, Union

from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus
from aegis_swr.openhands.client import (
    EventKind,
    OpenHandsClient,
    OpenHandsEvent,
)
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import (
    OpenHandsAction,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
    OpenHandsStreamCompleted,
    OpenHandsStreamError,
)
from aegis_swr.openhands.exceptions import (
    OpenHandsPermissionDeniedError,
    OpenHandsUnavailableError,
)


class _Done:
    """Typed, unique terminal sentinel for the stream-loop dispatch handlers.

    A single module-level instance (:data:`_DONE`) signals normal termination
    from :meth:`OpenHandsTool._consume_stream`'s terminal (``FINISH``) handler.
    Using a dedicated singleton type keeps the handler return type honest (a
    handler returns a :class:`CodeResult`, the sentinel, or ``None``) and makes
    the loop's ``is``-identity break unambiguous: a real :class:`CodeResult` can
    never be mistaken for it. Same pattern as ``OpenClaudeTool._Done`` (0004).
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
    :mod:`aegis_swr.openhands.client` (task 07.0). All failure paths return a
    typed :class:`CodeResult`; no exception escapes :meth:`delegate` (C13).

    **Read-only enforcement is not owned by this tool.** OpenHands executes its
    navigation tools inside a **Docker sandbox** (C8 item 2); the container
    filesystem and the runtime's own allowlist are the authoritative read-only
    boundary. The tool-side action gate here is *defense in depth plus
    observability*: it emits :class:`OpenHandsAction` / :class:`OpenHandsObservation`
    for audit and, if the server surfaces a non-allowlisted action, emits
    :class:`OpenHandsPermissionDenied` and halts - it does not itself authorize
    sandbox execution.

    :cvar name: Stable backend identifier used by ``CodeAgent`` registration.
    :cvar description: Human-readable capability advertised to the agent layer;
        concretely satisfies the abstract :class:`CodeIntelBackend` property.
    :ivar _client: REST/WS stream adapter (task 07.0); the only path to OpenHands.
    :ivar _settings: Immutable configuration, including the allowlist (C8 item 5).
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
            :class:`~aegis_swr.openhands.client.OpenHandsEvent` frames (task 07.0).
            The connection is the sidecar's concern (``process.py``); constructing
            the tool starts no traffic.
        :param settings: OpenHands configuration and allowlist (task 06.0).
        :param bus: EventBus for ``openhands.*`` emissions (task 09.0 events).
        :param budget: Per-call boundary :class:`CallBudget`. Left untouched here;
            the pre-check/charge happen inside :meth:`delegate` (subtask 02).
        """
        self._client = client
        self._settings = settings
        self._bus = bus
        self._budget = budget

    async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Delegate *task* to OpenHands and return a single text result.

        Public :class:`CodeIntelBackend` entry point. Orchestration - the budget
        pre-check, the ``ctx.dry_run`` short-circuit, delegation to
        :meth:`_consume_stream`, token-estimate resolution, and the post-charge -
        is finalised in subtask 02. Never raises: every failure path returns a
        typed :class:`CodeResult` (C13).

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation :class:`CodeTaskContext` carrying ``run_id``
            (a :class:`~uuid.UUID`) and ``dry_run``.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        ...  # finalised in subtask 02

    async def _consume_stream(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Consume the OpenHands Action/Observation stream to a single result.

        Iterates the events yielded by ``self._client.stream(task,
        str(ctx.run_id))`` (C8 item 4): accumulates the assistant's text
        (``MESSAGE`` events from the agent, plus the terminal event's final text)
        into the result, counts ``ACTION`` / ``OBSERVATION`` events for
        observability metadata, and emits one ``openhands.*`` event per frame
        (C10). Returns on the terminal ``FINISH`` event. The terminal-event
        token-estimate resolution, truncation, charge, and
        :class:`OpenHandsStreamCompleted` emission are added to the ``FINISH``
        exit by subtask 02 (via ``_on_finish``); the ``ERROR`` and transport
        failure paths are finalised there too.

        :param task: The open-ended code-navigation prompt.
        :param ctx: Per-invocation :class:`CodeTaskContext`.
        :return: A success or typed-failure :class:`CodeResult`.
        """
        chunks: list[str] = []
        action_count = 0
        observation_count = 0
        event_count = 0
        server_usage: Optional[object] = None  # OpenHandsUsage; resolved in 02

        async def _handle_message(event: OpenHandsEvent) -> _HandlerResult:
            """Accumulate agent-authored assistant text (never logged, C13)."""
            if event.source == "agent":
                chunks.append(event.content)
            return None

        async def _handle_action(event: OpenHandsEvent) -> _HandlerResult:
            """Count an ``ACTION`` event, gate it, and emit its audit event (C10)."""
            nonlocal action_count
            action_count += 1
            self._check_action(event, ctx)  # may raise (defense in depth)
            self._emit_action(event, ctx)
            return None

        async def _handle_observation(event: OpenHandsEvent) -> _HandlerResult:
            """Count an ``OBSERVATION`` event and emit its audit event (C10)."""
            nonlocal observation_count
            observation_count += 1
            self._emit_observation(event, ctx)
            return None

        async def _handle_finish(event: OpenHandsEvent) -> _HandlerResult:
            """Capture terminal server usage, then signal normal termination."""
            nonlocal server_usage
            server_usage = event.usage  # None unless the server reported it (C9)
            if event.content:
                chunks.append(event.content)
            return _DONE  # typed sentinel: break from loop

        async def _handle_error(event: OpenHandsEvent) -> _HandlerResult:
            """Handle a terminal ``ERROR`` event; capture the live ``event_count``."""
            return self._on_error_event(ctx, event_count)  # subtask 02

        handlers: dict[EventKind, Callable[[OpenHandsEvent], Awaitable[_HandlerResult]]] = {
            EventKind.MESSAGE: _handle_message,
            EventKind.ACTION: _handle_action,
            EventKind.OBSERVATION: _handle_observation,
            EventKind.FINISH: _handle_finish,
            EventKind.ERROR: _handle_error,  # subtask 02
        }

        async for event in self._client.stream(task, str(ctx.run_id)):
            event_count += 1
            handler = handlers.get(event.event_kind)
            if handler is None:
                continue  # unknown event kind; skip silently
            result = await handler(event)
            if isinstance(result, _Done):
                break  # narrows the sentinel out of the union below
            elif result is not None:
                return result  # early exit (error or other terminal state)

        content = "".join(chunks)
        # subtask 02: resolve token_estimate (server_usage vs boundary), truncate,
        # charge, emit OpenHandsStreamCompleted, and succeed via _on_finish.
        return self._on_finish(
            content,
            ctx,
            server_usage=server_usage,
            action_count=action_count,
            observation_count=observation_count,
            event_count=event_count,
        )

    def _emit_action(self, event: OpenHandsEvent, ctx: CodeTaskContext):
        """Emit :class:`OpenHandsAction` for an ``ACTION`` event (C10).

        Carries only the run id, the action type name, and a derived argument
        count - never the raw action arguments, which may echo incident payload
        (C13).

        :param event: The ``ACTION`` event; ``event.action`` names the action
            type and ``event.content`` holds the (never-emitted) argument JSON.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        self._bus.publish(
            OpenHandsAction(
                run_id=str(ctx.run_id),
                action=event.action or "",
                arg_count=self._arg_count(event.content),
            )
        )

    def _emit_observation(self, event: OpenHandsEvent, ctx: CodeTaskContext):
        """Emit :class:`OpenHandsObservation` for an ``OBSERVATION`` event (C10).

        Carries only the run id, the observation type name, and the output size
        (a count) - never the raw observation content, which may contain incident
        payload (C13).

        :param event: The ``OBSERVATION`` event; ``event.content`` holds the
            (never-emitted) observation output.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        """
        self._bus.publish(
            OpenHandsObservation(
                run_id=str(ctx.run_id),
                observation=event.observation or "",
                result_size=len(event.content),
            )
        )

    def _check_action(self, event: OpenHandsEvent, ctx: CodeTaskContext):
        """Deny a surfaced non-allowlisted action; allow anything else.

        Defense in depth over the sandbox (the container is the authoritative
        guard, C8 item 2). When the runtime surfaces an action whose type is not
        in ``settings.allowed_tools``, emit :class:`OpenHandsPermissionDenied`
        and raise so the invocation halts read-only; :meth:`delegate` maps the
        raise to a non-retriable failure (subtask 02). Only the action type name
        (never its arguments) is placed on the event and exception (C13).

        :param event: The ``ACTION`` event; ``event.action`` names the type.
        :param ctx: Per-invocation :class:`CodeTaskContext` supplying ``run_id``.
        :raises OpenHandsPermissionDeniedError: When the action type is not
            allowlisted.
        """
        action = event.action or ""
        if action in self._settings.allowed_tools:
            return
        self._bus.publish(
            OpenHandsPermissionDenied(run_id=str(ctx.run_id), action=action)
        )
        raise OpenHandsPermissionDeniedError(action=action)

    @staticmethod
    def _arg_count(content: str) -> int:
        """Count action arguments without exposing the payload (C13).

        Parses *content* as JSON and returns the number of top-level members of a
        JSON object or array; non-JSON or scalar content yields ``0``. The parsed
        content is never logged or emitted - only the count leaves this method.

        :param content: The ``ACTION`` event's argument JSON (never emitted).
        :return: The top-level argument count, or ``0`` when indeterminate.
        """
        ...
```

## Implementation notes

- **Client surface is task 07.0's, assumed here and flagged.** `openhands/client.py`
  (task 07.0) is the sole importer of the OpenHands HTTP/WS client library and
  is responsible for **normalising** OpenHands' native Action/Observation model
  into the small, transport-free `OpenHandsEvent` frames this tool consumes.
  Assumed surface (task 07.0 must confirm the exact names):
  - `OpenHandsClient.stream(task: str, run_id: str)` — an async generator
    yielding `OpenHandsEvent`.
  - `OpenHandsEvent` with `event_kind: EventKind`, `content: str`,
    `source: str` (``"agent"`` | ``"user"`` | ``"environment"``),
    `action: Optional[str]`, `observation: Optional[str]`, and
    `usage: Optional[OpenHandsUsage]` (present on the terminal event **only when
    the server reports real usage**, C9).
  - `EventKind` enum: `MESSAGE`, `ACTION`, `OBSERVATION`, `FINISH`, `ERROR`.
  The tool imports these from the client module and **never** touches the
  OpenHands client library or `websockets`/`httpx` directly (C3).
- **Mapping OpenHands' native vocabulary is the client's job, not the tool's.**
  OpenHands emits `MessageAction` (agent text), tool `*Action`s, `*Observation`s,
  and an `AgentFinishAction` / `FINISHED` state transition. The client collapses
  these into the five `EventKind`s above so the tool loop stays flat. Flag: task
  07.0/09.0 must pin how the agent's final answer surfaces (a trailing `MESSAGE`,
  the `FINISH` event's `content`, or both) — this subtask accumulates **both** to
  be safe, so a double-counted final message is the only benign edge.
- **Accumulation is O(n):** agent text is appended to `chunks`; the join is
  deferred to loop exit so truncation (subtask 02) operates on the full string
  once. `ACTION` / `OBSERVATION` events contribute to counts and emissions only —
  never to the result text.
- **Terminal-event usage capture (C9):** `_handle_finish` stashes
  `event.usage` into the `server_usage` local (a `nonlocal` binding). Subtask 02
  reads it: real usage → `usage.input_tokens + usage.output_tokens`; `None` →
  boundary estimate `max(1, len(content) // 4)`. This subtask only *captures* it.
- **Handler dict pattern** (as in 0004 04.0/02): each event kind maps to an async
  handler returning `None` (continue), the `_DONE` sentinel (normal
  termination), or a `CodeResult` (early exit). Unknown kinds are skipped via
  `.get()` + `None` check. The tool holds **no** per-call mutable state; counters
  and `chunks` are function-local with `nonlocal` bindings.
- `OpenHandsAction`, `OpenHandsObservation`, `OpenHandsPermissionDenied`,
  `OpenHandsStreamCompleted`, `OpenHandsStreamError`, and
  `OpenHandsPermissionDeniedError` are defined in **task 09.0** and imported
  here — never redefined. `_on_finish`, `_on_error_event`, and the exception
  translation land in subtask 02.
- **Action-gate divergence to carry:** OpenClaude's C7 permission gate is a
  first-class, load-bearing read-only guarantee because OpenClaude runs with host
  permissions. For OpenHands the **container is the authoritative guard** (C8
  item 2), so `_check_action` here is intentionally lighter — audit +
  defense-in-depth only. If task 06.0's `OpenHandsSettings` omits `allowed_tools`
  or the client never surfaces a gate-able action, `_check_action` degenerates to
  a no-op allow; task 09.0/11.0 must reconcile whether the gate is exercised at
  all. It is included so C10's `openhands.permission_denied` has an emitter.
- **Never log** `event.content`, `event.usage`, accumulated text, or action
  arguments — all untrusted response payload (C13). Emissions carry counts,
  type/status strings, and ids only.

## Constraints

- `from __future__ import annotations`; `Optional[T]` from `typing`, never
  `T | None`, including in subscripts (C13).
- No import of the OpenHands client library, `httpx`, `websockets`, or any
  transport stub in this file (C3); every event type comes from
  `aegis_swr.openhands.client`.
- No `Any` in any signature; `ruff` and `replace_optional.py --check` clean.
- Event handlers are nested async functions within `_consume_stream`, each
  handling a single event kind — independently coverable (task 11.0).
- Counters and `chunks`/`server_usage` are function-local with `nonlocal`
  bindings; the tool holds no per-call mutable state.
- No `event.content` / observation output / action arguments / accumulated text
  reaches any log sink or event payload (C13).
- Constructor opens no connection, starts no process, and does not touch the
  budget.

## Success criteria

- [ ] `OpenHandsTool(client, settings, bus, budget)` constructs with all four
      collaborators injected and performs no I/O.
- [ ] `OpenHandsTool` is a `CodeIntelBackend` accepted anywhere one is expected;
      `name == "openhands"` and `description` advertises Docker-sandboxed
      multi-file navigation.
- [ ] `_consume_stream` calls `self._client.stream(task, str(ctx.run_id))`
      exactly once and iterates it with `async for`.
- [ ] `MESSAGE` events with `source == "agent"` are concatenated in order into
      the result text; other sources are ignored.
- [ ] `ACTION` and `OBSERVATION` events increment their respective counters and
      publish exactly one `OpenHandsAction(run_id, action, arg_count)` /
      `OpenHandsObservation(run_id, observation, result_size)`.
- [ ] A total `event_count` is tracked across every event kind.
- [ ] `FINISH` captures `event.usage` into `server_usage`, appends any final
      `event.content`, and terminates the loop.
- [ ] A surfaced non-allowlisted `ACTION` publishes
      `OpenHandsPermissionDenied(run_id, action)` and raises
      `OpenHandsPermissionDeniedError`.
- [ ] No `import` of the OpenHands client library / `httpx` / `websockets`
      appears in the file (C3 grep check).
- [ ] No `event.content`, observation output, action arguments, or accumulated
      text is logged or attached to any event.
- [ ] `ruff` and `replace_optional.py --check` clean; no `Any` in any signature.
