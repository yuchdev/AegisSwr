"""Unit tests for :class:`aegis_swr.claude_code.tool.ClaudeCodeTool`.

Scenario: the one-shot ``claude`` :class:`CodeIntelBackend` is exercised end to
end with the subprocess and NDJSON parser replaced by injection seams — the
ordered gates of ``delegate`` (budget pre-check → dry-run → timeout-bounded
spawn-parse-charge), real-token accounting (C6.2/C9), the failure taxonomy, and
the emitted ``claude_code.*`` events.

Boundaries: unit — ``ClaudeCodeProcess`` and ``parse_stream`` are monkeypatched;
no real ``claude`` binary is ever spawned. The budget is a real
:class:`CallBudget`; the event bus is a recording :class:`MagicMock`.

On failure: a gate ordering, a token charge, a failure classification, or an
emitted event drifted from the C6/C9/C13 contract.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from loguru import logger

from aegis_swr.claude_code import tool as tool_mod
from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.events import (
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
    ClaudeCodeStreamResult,
    ClaudeCodeToolCallRecord,
    ClaudeCodeToolResultRecord,
    ClaudeCodeUsage,
)
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.backend import CodeIntelBackend, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import EventBus

# A sentinel returned by the fake process's ``stdout_lines``; ``parse_stream`` is
# patched and never actually reads it.
_STDOUT_SENTINEL = object()


def _published(bus: MagicMock) -> list[object]:
    """Return the events passed to ``bus.publish`` across all calls.

    :param bus: the recording event-bus mock.
    :return: the list of published event objects, in order.
    """
    return [call.args[0] for call in bus.publish.call_args_list]


def _events_of(bus: MagicMock, event_type: type) -> list[object]:
    """Return the published events that are instances of *event_type*.

    :param bus: the recording event-bus mock.
    :param event_type: the event class to filter by.
    :return: the matching published events.
    """
    return [event for event in _published(bus) if isinstance(event, event_type)]


class _FakeProcess:
    """Async-context fake standing in for :class:`ClaudeCodeProcess`."""

    def __init__(self, *, exit_code: int = 0, spawn_error: object = None):
        """Configure the exit code and an optional spawn-time error.

        :param exit_code: the exit code returned by ``wait_exit``.
        :param spawn_error: an exception to raise from ``__aenter__``, or ``None``.
        """
        self._exit_code = exit_code
        self._spawn_error = spawn_error
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> _FakeProcess:
        """Enter the fake context, raising the configured spawn error if any."""
        if self._spawn_error is not None:
            raise self._spawn_error
        self.entered = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object):
        """Record context exit; never suppress an in-flight exception."""
        self.exited = True

    def stdout_lines(self) -> object:
        """Return the stdout sentinel (``parse_stream`` is patched)."""
        return _STDOUT_SENTINEL

    async def wait_exit(self) -> int:
        """Return the configured exit code."""
        return self._exit_code


def _patch_process(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: object = None,
    exit_code: int = 0,
    spawn_error: object = None,
) -> list[str]:
    """Patch ``ClaudeCodeProcess`` and ``parse_stream`` in the tool module.

    :param monkeypatch: the pytest monkeypatch fixture.
    :param result: the :class:`ClaudeCodeStreamResult` ``parse_stream`` returns.
    :param exit_code: the exit code the fake process reports.
    :param spawn_error: an exception the fake process raises on entry, or ``None``.
    :return: a list recording the task passed to each spawned process.
    """
    spawns: list[str] = []
    fake = _FakeProcess(exit_code=exit_code, spawn_error=spawn_error)

    def _factory(settings: object, task: str) -> _FakeProcess:
        """Record the task and return the fake process (records C6.1 delivery)."""
        spawns.append(task)
        return fake

    async def _parse(stdout: object) -> object:
        """Return the scripted stream result, ignoring the sentinel stdout."""
        return result

    monkeypatch.setattr(tool_mod, "ClaudeCodeProcess", _factory)
    monkeypatch.setattr(tool_mod, "parse_stream", _parse)
    return spawns


def _make_tool(budget: CallBudget, **settings_overrides: object) -> tuple[ClaudeCodeTool, MagicMock, MagicMock]:
    """Build a tool with a mock settings, a recording bus, and a real budget.

    :param budget: the real :class:`CallBudget` under test.
    :param settings_overrides: attribute overrides for the mock settings.
    :return: the tool, the settings mock, and the bus mock.
    """
    settings = MagicMock(spec=ClaudeCodeSettings)
    settings.binary_path = "claude"
    settings.allowed_tools = ["Read", "Grep", "Glob"]
    settings.permission_mode = "default"
    settings.max_turns = 8
    settings.request_timeout_s = 30
    settings.scratch_cwd = None
    for key, value in settings_overrides.items():
        setattr(settings, key, value)
    bus = MagicMock(spec=EventBus)
    return ClaudeCodeTool(settings, bus, budget), settings, bus


def _clean_result(
    *,
    content: str = "answer",
    input_tokens: int = 100,
    output_tokens: int = 40,
    tool_calls: tuple = (),
    tool_results: tuple = (),
    num_turns: object = 3,
) -> ClaudeCodeStreamResult:
    """Build a clean, usage-bearing :class:`ClaudeCodeStreamResult`.

    :param content: the accumulated assistant answer.
    :param input_tokens: the reported input token count.
    :param output_tokens: the reported output token count.
    :param tool_calls: the surfaced tool-call records.
    :param tool_results: the surfaced tool-result records.
    :param num_turns: the reported turn count.
    :return: a well-formed stream result.
    """
    return ClaudeCodeStreamResult(
        content=content,
        usage=ClaudeCodeUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        is_error=False,
        frame_count=5,
        assistant_count=2,
        tool_calls=tool_calls,
        tool_results=tool_results,
        num_turns=num_turns,
    )


# --------------------------------------------------------------------------- #
# construction & protocol surface
# --------------------------------------------------------------------------- #


def test_constructs_without_io_and_touches_no_budget():
    """[Unit] tool: construction stores collaborators and touches no budget.

    Scenario: a tool is built from a mock settings, bus, and a real budget.

    Boundaries: no process is spawned and the budget is untouched.

    On failure, first check: the collaborators must be stored and the budget spend
    must remain zero.
    """
    budget = CallBudget(max_tokens=1000)
    tool, settings, bus = _make_tool(budget)

    assert tool._settings is settings
    assert tool._bus is bus
    assert tool._budget is budget
    assert budget.spent == 0
    assert bus.mock_calls == []


def test_is_instantiable_code_intel_backend():
    """[Unit] tool: the tool is a concrete CodeIntelBackend accepted structurally.

    Scenario: a tool instance is checked against the backend ABC.

    Boundaries: exercises protocol conformance only.

    On failure, first check: ``isinstance`` against ``CodeIntelBackend`` must hold.
    """
    tool, _, _ = _make_tool(CallBudget(max_tokens=1000))

    assert isinstance(tool, CodeIntelBackend)


def test_name_and_description_advertise_the_backend():
    """[Unit] tool: ``name``/``description`` advertise the one-shot CLI backend.

    Scenario: the class-level metadata is read.

    Boundaries: static class metadata only.

    On failure, first check: ``name`` must be ``claude_code`` and the description
    must mention the one-shot stream-json invocation.
    """
    assert ClaudeCodeTool.name == "claude_code"
    assert "stream-json" in ClaudeCodeTool.description


def test_source_has_no_tool_side_permission_gate():
    """[Unit] tool: the module has no tool-side permission/allowlist gate (C6.3).

    Scenario: the ``tool.py`` source is scanned for a permission-check method.

    Boundaries: a static source scan; read-only enforcement is the CLI's job.

    On failure, first check: the source must define no ``_check_permission`` or
    ``_is_allowlisted`` method.
    """
    source = Path(inspect.getfile(ClaudeCodeTool)).read_text(encoding="utf-8")

    assert "def _check_permission" not in source
    assert "def _is_allowlisted" not in source


# --------------------------------------------------------------------------- #
# delegate — ordered gates & branch coverage
# --------------------------------------------------------------------------- #


async def test_delegate_insufficient_budget_fails_without_spawning(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: an unaffordable budget fails non-retriably with zero spawns.

    Scenario: a zero-token budget delegates a task.

    Boundaries: enforces the pre-check before any spawn.

    On failure, first check: the metadata must report ``insufficient_budget``, no
    process is spawned, budget spend is zero, and no events publish.
    """
    budget = CallBudget(max_tokens=0)
    tool, _, bus = _make_tool(budget)
    spawns = _patch_process(monkeypatch, result=_clean_result())

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "insufficient_budget", "retriable": False}
    assert result.token_estimate == 0
    assert spawns == []
    assert budget.spent == 0
    assert _published(bus) == []


async def test_delegate_dry_run_short_circuits_without_spawning(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a dry run returns ``[dry-run]`` and never spawns (C6.5).

    Scenario: a dry-run context is delegated with ample budget.

    Boundaries: proves dry-run short-circuits before any spawn or budget mutation.

    On failure, first check: content must be ``[dry-run]`` with zero tokens, no
    spawn, zero budget spend, and no events.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    spawns = _patch_process(monkeypatch, result=_clean_result())

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4(), dry_run=True))

    assert result.content == "[dry-run]"
    assert result.token_estimate == 0
    assert result.metadata["ok"] is True
    assert spawns == []
    assert budget.spent == 0
    assert _published(bus) == []


async def test_delegate_pre_check_precedes_dry_run(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: an over-budget dry run still returns the budget failure first.

    Scenario: a zero-token budget is delegated with a dry-run context.

    Boundaries: pins gate ordering — the pre-check precedes the dry-run branch.

    On failure, first check: the metadata error must be ``insufficient_budget`` and
    the content must not be ``[dry-run]``.
    """
    budget = CallBudget(max_tokens=0)
    tool, _, _ = _make_tool(budget)
    spawns = _patch_process(monkeypatch, result=_clean_result())

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4(), dry_run=True))

    assert result.metadata["error"] == "insufficient_budget"
    assert result.content != "[dry-run]"
    assert spawns == []


async def test_delegate_clean_stream_charges_real_tokens_after_completion(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] tool: a clean stream charges the real usage sum after completion (C9).

    Scenario: a usage-bearing stream (input 100, output 40) is delegated with
    ample budget.

    Boundaries: enforces C6.2/C9 — token_estimate is the real usage sum, charged
    after the stream.

    On failure, first check: content must be the answer, token_estimate and budget
    spend must be 140, and the task must have been fed to the spawned process.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    result_obj = _clean_result(content="the answer", input_tokens=100, output_tokens=40)
    spawns = _patch_process(monkeypatch, result=result_obj)

    result = await tool.delegate("navigate the repo", CodeTaskContext(run_id=uuid4()))

    assert result.metadata["ok"] is True
    assert result.content == "the answer"
    assert result.token_estimate == 140  # C9: real usage.input + usage.output
    assert budget.spent == 140  # charged AFTER completion
    assert result.metadata["frame_count"] == 5
    assert spawns == ["navigate the repo"]  # C6.1: task delivered to the process
    completed = _events_of(bus, ClaudeCodeCompleted)
    assert len(completed) == 1
    assert completed[0].token_estimate == 140
    assert completed[0].input_tokens == 100
    assert completed[0].output_tokens == 40
    assert completed[0].num_turns == 3


async def test_delegate_clean_stream_emits_spawn_and_exit_lifecycle(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a clean run emits the spawned/exited lifecycle events (C10).

    Scenario: a usage-bearing stream is delegated and the emitted events scanned.

    Boundaries: the bus is a recording mock; the process is faked.

    On failure, first check: exactly one ``ClaudeCodeSpawned`` and one
    ``ClaudeCodeExited`` (reason ``completed``, exit code 0) must be emitted.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    _patch_process(monkeypatch, result=_clean_result(), exit_code=0)

    await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    spawned = _events_of(bus, ClaudeCodeSpawned)
    exited = _events_of(bus, ClaudeCodeExited)
    assert len(spawned) == 1
    assert spawned[0].auth_mode == "auto"
    assert spawned[0].binary == "claude"
    assert len(exited) == 1
    assert exited[0].reason == "completed"
    assert exited[0].exit_code == 0


async def test_delegate_emits_tool_call_and_result_events(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: tool-use/tool-result records emit their observability events.

    Scenario: a clean stream carries one allowlisted tool call and one tool
    result.

    Boundaries: only tool names and counts travel on the events (C13).

    On failure, first check: one ``ClaudeCodeToolCall`` and one
    ``ClaudeCodeToolResult`` must be emitted with the recorded names and counts,
    and no permission-denied event fires for an allowlisted tool.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    result_obj = _clean_result(
        tool_calls=(ClaudeCodeToolCallRecord(tool="Grep", arg_count=2),),
        tool_results=(ClaudeCodeToolResultRecord(tool="Grep", ok=True, result_size=42),),
    )
    _patch_process(monkeypatch, result=result_obj)

    await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    calls = _events_of(bus, ClaudeCodeToolCall)
    results = _events_of(bus, ClaudeCodeToolResult)
    assert len(calls) == 1
    assert calls[0].tool == "Grep"
    assert calls[0].arg_count == 2
    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].result_size == 42
    assert _events_of(bus, ClaudeCodePermissionDenied) == []


async def test_delegate_non_allowlisted_tool_emits_permission_denied(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a tool-call outside the allowlist emits a permission-denied event.

    Scenario: a clean stream attempts a ``Bash`` tool not in the allowlist.

    Boundaries: the allowlist guard is the CLI's; this surfaces the observed
    breach as an event (C6.3/C10).

    On failure, first check: one ``ClaudeCodePermissionDenied`` must be emitted for
    the non-allowlisted tool while the call still succeeds.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget, allowed_tools=["Read"])
    result_obj = _clean_result(
        tool_calls=(ClaudeCodeToolCallRecord(tool="Bash", arg_count=1),),
    )
    _patch_process(monkeypatch, result=result_obj)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    denied = _events_of(bus, ClaudeCodePermissionDenied)
    assert len(denied) == 1
    assert denied[0].tool == "Bash"
    assert denied[0].denied_binary == "Bash"
    assert result.metadata["ok"] is True


async def test_delegate_no_result_message_fails_non_retriable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a stream with no terminal result fails ``no_result_message``.

    Scenario: a stream reduces to ``usage is None`` (child produced no result).

    Boundaries: enforces the missing-result failure path with zero charge.

    On failure, first check: the metadata must report ``no_result_message``
    non-retriable, budget spend zero, and a ``ClaudeCodeError`` emitted.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    no_usage = ClaudeCodeStreamResult(content="", usage=None, is_error=False, frame_count=1)
    _patch_process(monkeypatch, result=no_usage, exit_code=0)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "no_result_message", "retriable": False}
    assert budget.spent == 0
    errors = _events_of(bus, ClaudeCodeError)
    assert any(e.code == "no_result_message" for e in errors)


async def test_delegate_result_error_fails_non_retriable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a result frame flagged as an error fails ``result_error``.

    Scenario: a usage-bearing stream carries ``is_error`` True.

    Boundaries: enforces the error-result failure path with zero charge.

    On failure, first check: the metadata must report ``result_error``
    non-retriable, budget spend zero, and a ``ClaudeCodeError`` emitted.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    errored = ClaudeCodeStreamResult(
        content="partial",
        usage=ClaudeCodeUsage(input_tokens=5, output_tokens=5),
        is_error=True,
        frame_count=2,
    )
    _patch_process(monkeypatch, result=errored, exit_code=0)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "result_error", "retriable": False}
    assert budget.spent == 0
    assert any(e.code == "result_error" for e in _events_of(bus, ClaudeCodeError))


async def test_delegate_nonzero_exit_fails_non_retriable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a non-zero child exit fails ``nonzero_exit`` non-retriably.

    Scenario: a usage-bearing stream is produced but the process exits with code 2.

    Boundaries: the exit code is checked after the stream drains.

    On failure, first check: the metadata must report ``nonzero_exit``
    non-retriable, budget spend zero, and both an ``exited`` (nonzero_exit) and an
    ``error`` event emitted.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    _patch_process(monkeypatch, result=_clean_result(), exit_code=2)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "nonzero_exit", "retriable": False}
    assert budget.spent == 0
    exited = _events_of(bus, ClaudeCodeExited)
    assert any(e.reason == "nonzero_exit" and e.exit_code == 2 for e in exited)
    assert any(e.error_type == "nonzero_exit" for e in _events_of(bus, ClaudeCodeError))


async def test_delegate_spawn_failure_fails_non_retriable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a spawn failure fails ``spawn_failed`` non-retriably.

    Scenario: the fake process raises ``ClaudeCodeUnavailableError`` on entry.

    Boundaries: the child never started; delegate maps the raise to a failure.

    On failure, first check: the metadata must report ``spawn_failed``
    non-retriable, budget spend zero, and both an ``exited`` (spawn_failed) and an
    ``error`` (spawn_error) event emitted.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    spawn_error = ClaudeCodeUnavailableError("spawn failed", binary="claude", reason="spawn_failed")
    _patch_process(monkeypatch, result=_clean_result(), spawn_error=spawn_error)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "spawn_failed", "retriable": False}
    assert budget.spent == 0
    assert any(e.reason == "spawn_failed" for e in _events_of(bus, ClaudeCodeExited))
    assert any(e.error_type == "spawn_error" for e in _events_of(bus, ClaudeCodeError))


async def test_delegate_timeout_fails_retriable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a request-timeout fails ``timeout`` retriably and reaps cleanly.

    Scenario: ``_run_once`` is patched to outlast a tiny ``request_timeout_s``.

    Boundaries: enforces the ``asyncio.wait_for`` deadline with zero charge.

    On failure, first check: the metadata must report ``timeout`` retriable, budget
    spend zero, and both a ``timeout`` error and a ``timeout`` exited event.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget, request_timeout_s=0.01)

    async def _slow(task: str, ctx: CodeTaskContext) -> ClaudeCodeStreamResult:
        """Sleep past the deadline to trigger the timeout branch."""
        await asyncio.sleep(1)
        return _clean_result()  # pragma: no cover - cancelled before returning

    monkeypatch.setattr(tool, "_run_once", _slow)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "timeout", "retriable": True}
    assert budget.spent == 0
    assert any(e.error_type == "timeout" for e in _events_of(bus, ClaudeCodeError))
    assert any(e.reason == "timeout" and e.exit_code is None for e in _events_of(bus, ClaudeCodeExited))


async def test_delegate_defensive_arm_returns_typed_failure(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: a fault-injected run never escapes ``delegate`` (C13).

    Scenario: ``_run_once`` is patched to raise a plain ``RuntimeError``.

    Boundaries: exercises the defensive ``except Exception`` arm of ``delegate``.

    On failure, first check: the metadata must report ``internal_error``
    non-retriable, budget spend zero, and a ``ClaudeCodeError`` emitted.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)

    async def _boom(task: str, ctx: CodeTaskContext) -> ClaudeCodeStreamResult:
        """Raise a plain exception to exercise the defensive arm."""
        raise RuntimeError("unexpected internal fault")

    monkeypatch.setattr(tool, "_run_once", _boom)

    result = await tool.delegate("task", CodeTaskContext(run_id=uuid4()))

    assert result.metadata == {"ok": False, "error": "internal_error", "retriable": False}
    assert result.available is True
    assert budget.spent == 0
    assert any(e.error_type == "internal_error" for e in _events_of(bus, ClaudeCodeError))


async def test_delegate_does_not_swallow_cancelled_error(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: ``CancelledError`` is not caught by the defensive arm (C13).

    Scenario: ``_run_once`` raises ``asyncio.CancelledError`` directly.

    Boundaries: ``CancelledError`` is a ``BaseException`` outside ``except
    Exception`` and must propagate.

    On failure, first check: ``delegate`` must re-raise ``CancelledError`` rather
    than returning a failure result.
    """
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, _ = _make_tool(budget)

    async def _cancel(task: str, ctx: CodeTaskContext) -> ClaudeCodeStreamResult:
        """Raise ``CancelledError`` to prove it is not swallowed."""
        raise asyncio.CancelledError

    monkeypatch.setattr(tool, "_run_once", _cancel)

    with pytest.raises(asyncio.CancelledError):
        await tool.delegate("task", CodeTaskContext(run_id=uuid4()))


async def test_delegate_never_logs_task_or_response_text(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: no task or response text reaches any log sink or event (C13).

    Scenario: a task and answer carrying secret markers flow through a clean
    delegation while a DEBUG sink captures logs.

    Boundaries: enforces C13 — payload is returned but never logged or emitted.

    On failure, first check: neither marker may appear in any captured log record
    or in any published event's string form.
    """
    task_marker = "TASK-MARKER-SECRET"
    answer_marker = "ANSWER-MARKER-SECRET"
    budget = CallBudget(max_tokens=1_000_000)
    tool, _, bus = _make_tool(budget)
    _patch_process(monkeypatch, result=_clean_result(content=answer_marker))

    records: list[str] = []
    sink_id = logger.add(records.append, level="DEBUG", format="{message}")
    try:
        result = await tool.delegate(task_marker, CodeTaskContext(run_id=uuid4()))
    finally:
        logger.remove(sink_id)

    assert result.content == answer_marker  # payload returned, never logged
    for marker in (task_marker, answer_marker):
        assert all(marker not in line for line in records)
        assert all(marker not in str(event) for event in _published(bus))
