"""Unit tests for :mod:`aegis_swr.claude_code.process`.

Scenario: the one-shot ``claude`` spawn helper and the ``stream-json`` (NDJSON)
parser are exercised in isolation — argv construction (with the load-bearing
argv-safety assertion, C6.1), the RAII subprocess lifecycle over a fake process,
and the NDJSON reduction to real token usage (C6.2/C9).

Boundaries: unit — ``asyncio.create_subprocess_exec`` is monkeypatched to a fake;
no real ``claude`` binary is ever spawned. The NDJSON parser runs against a fake
``StreamReader`` of scripted byte lines.

On failure: argv-safety, RAII reaping, or the real-token extraction drifted from
the C6/C9 contract, or payload text reached a log sink (C13).
"""

from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from typing import Optional

import pytest
from loguru import logger

from aegis_swr.claude_code import process as process_mod
from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError, ClaudeCodeUnavailableError
from aegis_swr.claude_code.process import (
    ClaudeCodeProcess,
    ClaudeCodeStreamResult,
    ClaudeCodeUsage,
    build_argv,
    parse_stream,
    resolve_credential,
)

# A distinctive substring standing in for the open-ended task text; it must never
# appear in any constructed argv element (C6.1).
_SENTINEL_TASK = "PS-VISIBLE-SENTINEL-TASK-TEXT-12345"


def _capture_debug_logs() -> tuple[list[str], int]:
    """Attach a DEBUG-level loguru sink capturing rendered messages.

    :return: the captured-records list and the sink id to remove afterwards.
    """
    records: list[str] = []
    sink_id = logger.add(records.append, level="DEBUG", format="{message}")
    return records, sink_id


def _ndjson(*frames: object) -> list[bytes]:
    """Encode each frame object as one NDJSON byte line.

    :param frames: JSON-serialisable frame objects.
    :return: a list of newline-terminated UTF-8 byte lines.
    """
    return [json.dumps(frame).encode() + b"\n" for frame in frames]


def _settings(**overrides: object) -> ClaudeCodeSettings:
    """Build a disabled :class:`ClaudeCodeSettings` for argv-only tests.

    :param overrides: field overrides forwarded to the constructor.
    :return: a constructed settings object (``enabled`` defaults False).
    """
    values: dict[str, object] = {
        "binary_path": "claude",
        "allowed_tools": ["Read", "Grep"],
        "permission_mode": "default",
        "max_turns": 5,
    }
    values.update(overrides)
    return ClaudeCodeSettings(**values)


def _enabled_settings(tmp_path: Path, **overrides: object) -> ClaudeCodeSettings:
    """Build an enabled :class:`ClaudeCodeSettings` with a disposable scratch cwd.

    :param tmp_path: the pytest temp directory used as the scratch cwd.
    :param overrides: field overrides forwarded to the constructor.
    :return: a constructed enabled settings object.
    """
    values: dict[str, object] = {
        "enabled": True,
        "scratch_cwd": tmp_path,
        "allowed_tools": ["Read"],
        "binary_path": "claude",
    }
    values.update(overrides)
    return ClaudeCodeSettings(**values)


# --------------------------------------------------------------------------- #
# build_argv / _validate_argv_token — argv-safety (C6.1, C6.3)
# --------------------------------------------------------------------------- #


def test_build_argv_has_expected_shape():
    """[Unit] process: build_argv emits the documented one-shot stream-json argv.

    Scenario: an argv is built from settings with two allowlisted tools.

    Boundaries: pure argv construction; no process is spawned.

    On failure, first check: the argv must start with the binary and ``-p``, use
    ``--output-format stream-json --verbose``, and carry the allowlist,
    permission mode, and max-turns flags.
    """
    argv = build_argv(_settings(allowed_tools=["Read", "Grep"], permission_mode="plan", max_turns=7))

    assert argv[0] == "claude"
    assert argv[1] == "-p"
    assert "--output-format" in argv
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Read,Grep"
    assert argv[argv.index("--permission-mode") + 1] == "plan"
    assert argv[argv.index("--max-turns") + 1] == "7"


def test_build_argv_takes_only_settings_and_omits_task():
    """[Unit] process: build_argv has no task parameter and never carries task text.

    Scenario: the reflected signature is inspected and an argv is scanned for a
    sentinel task substring (C6.1).

    Boundaries: static signature plus argv-content scan; the whole point is
    structural absence of the task from argv.

    On failure, first check: ``build_argv`` must accept only ``settings`` and the
    sentinel task substring must appear in no argv element.
    """
    assert list(inspect.signature(build_argv).parameters) == ["settings"]

    argv = build_argv(_settings())

    # The task string is never passed to build_argv, so it cannot appear in argv.
    assert all(_SENTINEL_TASK not in element for element in argv)


def test_build_argv_never_emits_dangerous_skip_permissions():
    """[Unit] process: build_argv never emits a permission-bypass flag (C6.3).

    Scenario: an argv is built and scanned for the bypass flag.

    Boundaries: pure argv construction; the settings validator already rejects
    bypass values at construction time.

    On failure, first check: no argv element may contain
    ``dangerously-skip-permissions``.
    """
    argv = build_argv(_settings())

    assert all("dangerously-skip-permissions" not in element for element in argv)


def test_build_argv_always_emits_allowed_tools_flag():
    """[Unit] process: build_argv always emits ``--allowedTools`` (FIX 6, fail closed).

    Scenario: an argv is built from a validly-constructed settings object.

    Boundaries: pure argv construction; a valid ``ClaudeCodeSettings`` can never
    carry an empty allowlist (rejected at construction), so the flag is never
    conditionally omitted.

    On failure, first check: ``--allowedTools`` must always be present - omitting it
    would grant the CLI unrestricted tool access (the inverse of the read-only
    guard).
    """
    argv = build_argv(_settings(allowed_tools=["Read"]))

    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Read"


def test_empty_allowed_tools_rejected_at_construction():
    """[Unit] process: an explicit empty ``allowed_tools`` is rejected (FIX 6).

    Scenario: ``ClaudeCodeSettings`` is constructed with ``allowed_tools=[]``.

    Boundaries: exercises the settings-level fail-closed guard that stands in for
    the argv layer - an empty allowlist must never reach ``build_argv`` and cause
    ``--allowedTools`` to be omitted (which would fail open).

    On failure, first check: construction must raise ``ClaudeCodeConfigError`` for
    the ``allowed_tools`` field rather than silently accepting an empty allowlist.
    """
    with pytest.raises(ClaudeCodeConfigError) as exc:
        _settings(allowed_tools=[])
    assert exc.value.field == "allowed_tools"


@pytest.mark.parametrize("bad", ["-rm", "a,b", "a=b", "a b", "a\n", "a$b", ""])
def test_build_argv_rejects_unsafe_allowlist_token(bad: str):
    """[Unit] process: an unsafe allowlist token fails argv construction closed.

    Scenario: settings whose ``allowed_tools`` include an unsafe token build an
    argv.

    Boundaries: the token allowlist regex rejects flags, separators, whitespace,
    and control chars; construction must fail before any spawn.

    On failure, first check: ``build_argv`` must raise ``ClaudeCodeConfigError``.
    """
    # Bypass the settings validator (which only allows known tool names) by
    # constructing a valid settings object, then injecting the hostile token onto
    # the attribute so build_argv's own boundary check is exercised.
    settings = _settings(allowed_tools=["Read"])
    object.__setattr__(settings, "allowed_tools", [bad])

    with pytest.raises(ClaudeCodeConfigError):
        build_argv(settings)


# --------------------------------------------------------------------------- #
# ClaudeCodeProcess — RAII spawn/reap over a fake subprocess
# --------------------------------------------------------------------------- #


class _FakeStdin:
    """Fake ``StreamWriter`` recording the bytes written to the child's stdin."""

    def __init__(self):
        """Initialise empty buffer, closed flag, and drain counter."""
        self.data = b""
        self.closed = False
        self.drains = 0

    def write(self, chunk: bytes):
        """Record *chunk* written to the fake stdin."""
        self.data += chunk

    async def drain(self):
        """Record a drain of the fake stdin buffer."""
        self.drains += 1

    def close(self):
        """Mark the fake stdin as closed (EOF to the child)."""
        self.closed = True


class _FakeReader:
    """Fake ``asyncio.StreamReader`` yielding queued byte lines then EOF."""

    def __init__(self, lines: Optional[list[bytes]] = None):
        """Queue *lines* and initialise the read counter."""
        self._lines = list(lines or [])
        self.readline_calls = 0

    async def readline(self) -> bytes:
        """Return the next queued line, or ``b""`` (EOF) when drained."""
        self.readline_calls += 1
        if self._lines:
            return self._lines.pop(0)
        return b""


class _FakeProcess:
    """Fake ``asyncio.subprocess.Process`` modelling the one-shot reap contract."""

    def __init__(
        self,
        *,
        stdout_lines: Optional[list[bytes]] = None,
        stderr_lines: Optional[list[bytes]] = None,
        exit_code: int = 0,
        terminate_exits: bool = True,
        completes: bool = True,
    ):
        """Configure the scripted stdout/stderr, exit code, and reap behaviour.

        :param stdout_lines: scripted stdout NDJSON byte lines.
        :param stderr_lines: scripted stderr byte lines.
        :param exit_code: the return code reported on completion / terminate.
        :param terminate_exits: when True, ``terminate`` reaps the process.
        :param completes: when True, ``wait`` returns the exit code immediately;
            when False it blocks until ``terminate``/``kill`` reaps the process.
        """
        self.stdin = _FakeStdin()
        self.stdout = _FakeReader(stdout_lines)
        self.stderr = _FakeReader(stderr_lines)
        self.returncode: Optional[int] = None
        self._exit_code = exit_code
        self._terminate_exits = terminate_exits
        self._completes = completes
        self._exited = asyncio.Event()
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def terminate(self):
        """Record a SIGTERM; reap the process when ``terminate_exits`` is set."""
        self.terminate_calls += 1
        if self._terminate_exits:
            self.returncode = self._exit_code
            self._exited.set()

    def kill(self):
        """Record a SIGKILL and reap the process immediately."""
        self.kill_calls += 1
        self.returncode = -9
        self._exited.set()

    async def wait(self) -> int:
        """Return the exit code, blocking until reaped when not auto-completing."""
        self.wait_calls += 1
        if self.returncode is not None:
            return self.returncode
        if self._completes:
            self.returncode = self._exit_code
            return self.returncode
        await self._exited.wait()
        assert self.returncode is not None
        return self.returncode


def _patch_spawn(monkeypatch: pytest.MonkeyPatch, fake: _FakeProcess) -> list[dict]:
    """Monkeypatch ``asyncio.create_subprocess_exec`` to return *fake*.

    :param monkeypatch: the pytest monkeypatch fixture.
    :param fake: the fake process to hand back from each spawn.
    :return: a list recording the kwargs of each spawn call.
    """
    calls: list[dict] = []

    async def _spawn(*args: object, **kwargs: object) -> _FakeProcess:
        """Record the spawn kwargs and return the fake process."""
        calls.append({"args": args, "kwargs": kwargs})
        return fake

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return calls


async def test_process_spawns_with_scratch_cwd_and_feeds_task_over_stdin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: entry spawns with the scratch cwd and writes the task to stdin.

    Scenario: a process is entered with a sentinel task and a fake spawn records
    the spawn kwargs and stdin bytes.

    Boundaries: the spawn primitive is faked; no real binary runs (C6.1).

    On failure, first check: the spawn ``cwd`` must equal ``scratch_cwd``, the
    sentinel task must be written to stdin and stdin closed, and the sentinel must
    appear in no spawn argv element.
    """
    settings = _enabled_settings(tmp_path)
    fake = _FakeProcess(stdout_lines=[b""])
    calls = _patch_spawn(monkeypatch, fake)

    async with ClaudeCodeProcess(settings, _SENTINEL_TASK) as proc:
        assert proc.stdout_lines() is fake.stdout

    assert len(calls) == 1
    assert calls[0]["kwargs"]["cwd"] == settings.scratch_cwd
    # C6.1: the task is delivered over stdin, never on argv.
    assert fake.stdin.data == _SENTINEL_TASK.encode()
    assert fake.stdin.closed is True
    spawn_argv = calls[0]["args"]
    assert all(_SENTINEL_TASK not in str(element) for element in spawn_argv)


async def test_process_wait_exit_returns_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: wait_exit returns the child's exit code after the stream.

    Scenario: a process with exit code 3 is entered and ``wait_exit`` awaited.

    Boundaries: the spawn primitive is faked.

    On failure, first check: ``wait_exit`` must return 3.
    """
    settings = _enabled_settings(tmp_path)
    fake = _FakeProcess(exit_code=3)
    _patch_spawn(monkeypatch, fake)

    async with ClaudeCodeProcess(settings, "task") as proc:
        code = await proc.wait_exit()

    assert code == 3


async def test_process_uses_and_exposes_injected_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: an injected credential is used and exposed (FIX 9, single resolution).

    Scenario: a pre-resolved credential is passed to ``ClaudeCodeProcess`` and the
    process is entered over a fake spawn.

    Boundaries: the spawn primitive is faked; exercises the ``credential=``
    injection branch of ``__aenter__`` and the ``credential`` property.

    On failure, first check: ``proc.credential`` must be the *same* injected object
    (the process consulted the caller's single resolution rather than resolving a
    second time - the label-vs-behaviour seam FIX 9 closes).
    """
    settings = _enabled_settings(tmp_path)
    injected = resolve_credential(settings)
    fake = _FakeProcess(stdout_lines=[b""])
    _patch_spawn(monkeypatch, fake)

    async with ClaudeCodeProcess(settings, "task", credential=injected) as proc:
        assert proc.credential is injected


def test_process_credential_before_entry_raises(tmp_path: Path):
    """[Unit] process: the credential property raises before __aenter__ resolves it.

    Scenario: ``credential`` is read on a freshly constructed, un-entered process.

    Boundaries: exercises the not-yet-resolved guard of the ``credential`` property.

    On failure, first check: a ``RuntimeError`` must be raised - the resolution only
    exists after ``__aenter__``.
    """
    proc = ClaudeCodeProcess(_enabled_settings(tmp_path), "task")
    with pytest.raises(RuntimeError):
        _ = proc.credential


async def test_process_reaps_child_on_exception_in_body(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: an exception in the body still reaps the child (RAII).

    Scenario: a body raises before ``wait_exit`` so the child has not exited.

    Boundaries: the spawn primitive is faked; ``terminate`` reaps the process.

    On failure, first check: ``terminate`` must have been called exactly once and
    the process reaped.
    """
    settings = _enabled_settings(tmp_path)
    fake = _FakeProcess(completes=False, terminate_exits=True)
    _patch_spawn(monkeypatch, fake)

    class _BodyError(RuntimeError):
        """Marker error raised inside the ``async with`` body."""

    with pytest.raises(_BodyError):
        async with ClaudeCodeProcess(settings, "task"):
            raise _BodyError

    assert fake.terminate_calls == 1
    assert fake.returncode is not None


async def test_process_escalates_to_sigkill_after_grace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: a child ignoring SIGTERM is escalated to SIGKILL (RAII).

    Scenario: a fake that does not exit on terminate is reaped with a tiny grace
    period.

    Boundaries: the grace constant is shrunk so the escalation path is fast.

    On failure, first check: both ``terminate`` and ``kill`` must have been called
    and the process reaped.
    """
    monkeypatch.setattr(process_mod, "_TERMINATE_GRACE_S", 0.01)
    settings = _enabled_settings(tmp_path)
    fake = _FakeProcess(completes=False, terminate_exits=False)
    _patch_spawn(monkeypatch, fake)

    class _BodyError(RuntimeError):
        """Marker error raised inside the ``async with`` body."""

    with pytest.raises(_BodyError):
        async with ClaudeCodeProcess(settings, "task"):
            raise _BodyError

    assert fake.terminate_calls == 1
    assert fake.kill_calls == 1
    assert fake.returncode == -9


async def test_process_spawn_oserror_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: a spawn OSError becomes a typed unavailable error.

    Scenario: ``create_subprocess_exec`` raises ``FileNotFoundError`` (missing
    binary).

    Boundaries: the spawn primitive is faked to raise.

    On failure, first check: entry must raise ``ClaudeCodeUnavailableError`` with
    ``reason == "spawn_failed"`` and the configured binary name.
    """
    settings = _enabled_settings(tmp_path)

    async def _spawn(*args: object, **kwargs: object) -> object:
        """Raise a missing-binary error from the spawn primitive."""
        raise FileNotFoundError("claude: not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)

    with pytest.raises(ClaudeCodeUnavailableError) as excinfo:
        async with ClaudeCodeProcess(settings, "task"):
            pass  # pragma: no cover - entry raises before the body runs

    assert excinfo.value.reason == "spawn_failed"
    assert excinfo.value.binary == "claude"


async def test_process_reaps_child_when_stdin_write_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: a stdin failure after spawn reaps the child (RAII).

    Scenario: the child is live but ``stdin.drain`` raises, so entry fails after
    the process is spawned.

    Boundaries: the always-terminate invariant must reap the live child before the
    exception leaves ``__aenter__``.

    On failure, first check: entry must re-raise and the child must have been
    reaped (``terminate`` called).
    """
    settings = _enabled_settings(tmp_path)
    fake = _FakeProcess()

    class _BrokenStdin(_FakeStdin):
        """Stdin whose drain raises to fail entry after the spawn."""

        async def drain(self):
            """Raise a broken-pipe error to abort the stdin write."""
            raise BrokenPipeError("stdin closed early")

    fake.stdin = _BrokenStdin()
    _patch_spawn(monkeypatch, fake)

    with pytest.raises(BrokenPipeError):
        async with ClaudeCodeProcess(settings, "task"):
            pass  # pragma: no cover - entry raises before the body runs

    assert fake.terminate_calls == 1


async def test_process_stdout_lines_before_spawn_raises():
    """[Unit] process: reading stdout before spawn raises RuntimeError.

    Scenario: ``stdout_lines`` is called on an un-entered process.

    Boundaries: no spawn has occurred, so there is no stream.

    On failure, first check: the call must raise ``RuntimeError``.
    """
    settings = _settings()

    with pytest.raises(RuntimeError):
        ClaudeCodeProcess(settings, "task").stdout_lines()


async def test_process_never_logs_task_or_response_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: neither the task nor stdout payload reaches a log sink (C13).

    Scenario: a process is entered with a secret task while stdout carries a
    secret answer; a DEBUG sink captures all logs.

    Boundaries: enforces C13 — the task travels over stdin and stdout is the
    parser's concern; neither is logged.

    On failure, first check: neither secret substring may appear in any captured
    log record.
    """
    settings = _enabled_settings(tmp_path)
    leaky_stdout = b'{"type":"assistant","message":{"content":[{"type":"text","text":"LEAKY-ANSWER"}]}}\n'
    fake = _FakeProcess(stdout_lines=[leaky_stdout])
    _patch_spawn(monkeypatch, fake)

    records, sink_id = _capture_debug_logs()
    try:
        async with ClaudeCodeProcess(settings, _SENTINEL_TASK) as proc:
            await proc.wait_exit()
    finally:
        logger.remove(sink_id)

    assert all(_SENTINEL_TASK not in line for line in records)
    assert all("LEAKY-ANSWER" not in line for line in records)


async def test_process_drains_stderr_at_debug_with_bound_argument(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """[Unit] process: stderr lines are drained and logged at DEBUG (C13).

    Scenario: a process whose stderr yields one diagnostic line is entered while a
    DEBUG sink captures logs.

    Boundaries: stderr is logged only at DEBUG as a bound argument so the
    ``SensitiveFilter`` can redact it.

    On failure, first check: the stderr diagnostic text must appear in a captured
    DEBUG record.
    """
    settings = _enabled_settings(tmp_path)
    fake = _FakeProcess(stderr_lines=[b"startup diagnostic line\n"])
    _patch_spawn(monkeypatch, fake)

    records, sink_id = _capture_debug_logs()
    try:
        async with ClaudeCodeProcess(settings, "task") as proc:
            await proc.wait_exit()
            # Let the background stderr drain run before context exit cancels it.
            await asyncio.sleep(0)
    finally:
        logger.remove(sink_id)

    assert any("startup diagnostic line" in line for line in records)


# --------------------------------------------------------------------------- #
# parse_stream — NDJSON reduction + real token accounting (C6.2, C9)
# --------------------------------------------------------------------------- #


async def test_parse_stream_accumulates_text_and_reads_real_usage():
    """[Unit] process: parse_stream joins assistant text and reads real usage (C9).

    Scenario: a system frame, two assistant text frames, and a terminal result
    frame are parsed.

    Boundaries: the parser runs over a fake reader; no process is involved.

    On failure, first check: content must be the ordered concatenation and
    ``usage.total`` must equal the input+output token sum from the result frame.
    """
    lines = _ndjson(
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "alpha "}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "beta"}]}},
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": 4,
            "usage": {"input_tokens": 120, "output_tokens": 30},
        },
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.content == "alpha beta"
    assert isinstance(result.usage, ClaudeCodeUsage)
    assert result.usage.total == 150
    assert result.usage.input_tokens == 120
    assert result.usage.output_tokens == 30
    assert result.is_error is False
    assert result.num_turns == 4
    assert result.assistant_count == 2
    assert result.frame_count == 4


async def test_parse_stream_no_result_message_yields_usage_none():
    """[Unit] process: a stream with no terminal result frame yields usage None.

    Scenario: only assistant frames are parsed, with no result frame.

    Boundaries: the parser runs over a fake reader.

    On failure, first check: ``usage`` must be ``None`` (the failure signal).
    """
    lines = _ndjson(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "partial"}]}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.usage is None
    assert result.content == "partial"


async def test_parse_stream_result_is_error_flag_sets_is_error():
    """[Unit] process: a result frame's ``is_error`` flag sets is_error.

    Scenario: a terminal result frame with ``is_error`` true is parsed.

    Boundaries: the parser runs over a fake reader.

    On failure, first check: ``is_error`` must be True even though usage is
    present.
    """
    lines = _ndjson(
        {"type": "result", "subtype": "success", "is_error": True, "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.is_error is True
    assert result.usage is not None


async def test_parse_stream_error_subtype_sets_is_error():
    """[Unit] process: a non-success result ``subtype`` sets is_error.

    Scenario: a terminal result frame with an error subtype and no ``is_error``
    flag is parsed.

    Boundaries: the parser runs over a fake reader.

    On failure, first check: ``is_error`` must be True from the subtype alone.
    """
    lines = _ndjson(
        {"type": "result", "subtype": "error_during_execution", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.is_error is True


async def test_parse_stream_skips_malformed_lines_without_raising():
    """[Unit] process: malformed and non-object lines are skipped defensively (C13).

    Scenario: a non-JSON line and a JSON-scalar line surround valid frames.

    Boundaries: the parser must never raise on malformed output.

    On failure, first check: the surrounding valid frames must still parse and the
    content must equal the valid assistant text.
    """
    lines = [
        b"this is not json\n",
        b"12345\n",
        *_ndjson({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}),
        *_ndjson({"type": "result", "subtype": "success", "usage": {"input_tokens": 2, "output_tokens": 2}}),
    ]

    result = await parse_stream(_FakeReader(lines))

    assert result.content == "ok"
    assert result.usage is not None
    assert result.usage.total == 4


async def test_parse_stream_ignores_non_text_blocks_in_text_extraction():
    """[Unit] process: tool-use blocks are ignored by assistant text extraction.

    Scenario: an assistant frame mixes a text block and a tool-use block.

    Boundaries: the parser runs over a fake reader.

    On failure, first check: content must contain only the text block, while the
    tool-use block is surfaced as a tool-call record.
    """
    lines = _ndjson(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "answer"},
                    {"type": "tool_use", "id": "t1", "name": "Grep", "input": {"pattern": "x", "path": "src"}},
                ]
            },
        },
        {"type": "result", "subtype": "success", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.content == "answer"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool == "Grep"
    assert result.tool_calls[0].arg_count == 2


async def test_parse_stream_surfaces_tool_results_with_resolved_names():
    """[Unit] process: tool-result blocks resolve their tool name and success flag.

    Scenario: a tool-use frame is followed by a matching tool-result frame flagged
    as an error.

    Boundaries: the parser maps ``tool_use_id`` to the earlier tool name.

    On failure, first check: the surfaced tool-result record must carry the
    resolved tool name, ``ok=False``, and the output size — never the output text.
    """
    lines = _ndjson(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "abc", "name": "Read", "input": {}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "abc", "content": "boom", "is_error": True},
                ]
            },
        },
        {"type": "result", "subtype": "success", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert len(result.tool_results) == 1
    outcome = result.tool_results[0]
    assert outcome.tool == "Read"
    assert outcome.ok is False
    assert outcome.result_size == len("boom")


async def test_parse_stream_missing_usage_block_yields_usage_none():
    """[Unit] process: a result frame without a usage block yields usage None.

    Scenario: a terminal result frame carries no ``usage`` object.

    Boundaries: the parser runs over a fake reader.

    On failure, first check: ``usage`` must be ``None`` while ``is_error`` stays
    False.
    """
    lines = _ndjson({"type": "result", "subtype": "success"})

    result = await parse_stream(_FakeReader(lines))

    assert result.usage is None
    assert result.is_error is False


async def test_parse_stream_never_logs_content():
    """[Unit] process: assistant content never reaches a log sink (C13).

    Scenario: an assistant frame carrying a secret answer is parsed while a DEBUG
    sink captures logs.

    Boundaries: enforces C13 — content is returned but never logged.

    On failure, first check: the marker must appear in the returned content but in
    no captured log record.
    """
    leak_marker = "LEAKY-RESPONSE-PAYLOAD"
    lines = _ndjson(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": leak_marker}]}},
        {"type": "result", "subtype": "success", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    records, sink_id = _capture_debug_logs()
    try:
        result = await parse_stream(_FakeReader(lines))
    finally:
        logger.remove(sink_id)

    assert result.content == leak_marker
    assert all(leak_marker not in line for line in records)


class _RaisingReader:
    """Fake reader whose first ``readline`` raises, then reports EOF."""

    def __init__(self, exc: Exception):
        """Store the exception to raise on the first read and an EOF flag."""
        self._exc = exc
        self._raised = False

    async def readline(self) -> bytes:
        """Raise once, then return ``b""`` (EOF) on subsequent calls."""
        if not self._raised:
            self._raised = True
            raise self._exc
        return b""


async def test_parse_stream_tolerates_malformed_turn_frames():
    """[Unit] process: turn frames with malformed message/content are tolerated.

    Scenario: assistant/user frames whose ``message`` is not a dict or whose
    ``content`` is not a list precede a valid result frame.

    Boundaries: the content-block extractor must degrade to "no blocks".

    On failure, first check: the parse must not raise and must surface no tool
    calls or results while still reading usage.
    """
    lines = _ndjson(
        {"type": "assistant", "message": ["not", "a", "dict"]},
        {"type": "assistant", "message": {"content": "not-a-list"}},
        {"type": "user", "message": {"content": [{"type": "text", "text": "x"}]}},
        {"type": "result", "subtype": "success", "usage": {"input_tokens": 1, "output_tokens": 1}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.tool_calls == ()
    assert result.tool_results == ()
    assert result.usage is not None


async def test_parse_stream_non_integer_usage_yields_none():
    """[Unit] process: a result frame with non-integer tokens yields usage None.

    Scenario: a result frame whose ``input_tokens`` is a non-numeric string is
    parsed.

    Boundaries: the usage extractor coerces to int and returns None on failure.

    On failure, first check: ``usage`` must be ``None``.
    """
    lines = _ndjson(
        {"type": "result", "subtype": "success", "usage": {"input_tokens": "nan", "output_tokens": 2}},
    )

    result = await parse_stream(_FakeReader(lines))

    assert result.usage is None


async def test_parse_stream_readline_error_is_skipped():
    """[Unit] process: a transient readline error is skipped, not fatal (C13).

    Scenario: the reader's first ``readline`` raises ``ValueError`` (over-long
    line), then reports EOF.

    Boundaries: the parser must never crash on a per-line read failure.

    On failure, first check: the parse must return a result with ``usage`` None and
    no frames.
    """
    result = await parse_stream(_RaisingReader(ValueError("line too long")))

    assert result.usage is None
    assert result.frame_count == 0


async def test_write_task_stdin_noop_when_stdin_absent():
    """[Unit] process: _write_task_stdin is a no-op when stdin is absent.

    Scenario: the process holds a fake with ``stdin=None``.

    Boundaries: the guard must return without writing.

    On failure, first check: the call must complete without raising.
    """
    proc = ClaudeCodeProcess(_settings(), "task")
    fake = _FakeProcess()
    fake.stdin = None  # type: ignore[assignment]
    proc._process = fake  # type: ignore[assignment]

    await proc._write_task_stdin()  # must not raise


async def test_drain_stderr_noop_when_stderr_absent():
    """[Unit] process: _drain_stderr is a no-op when stderr is absent.

    Scenario: the process holds a fake with ``stderr=None``.

    Boundaries: the guard must return without reading.

    On failure, first check: the call must complete without raising.
    """
    proc = ClaudeCodeProcess(_settings(), "task")
    fake = _FakeProcess()
    fake.stderr = None  # type: ignore[assignment]
    proc._process = fake  # type: ignore[assignment]

    await proc._drain_stderr()  # must not raise


async def test_drain_stderr_skips_transient_read_error():
    """[Unit] process: _drain_stderr skips a transient read error and continues.

    Scenario: the stderr reader raises ``ValueError`` once, then reports EOF.

    Boundaries: a per-line read failure is caught narrowly and the drain continues.

    On failure, first check: the drain must complete without raising.
    """
    proc = ClaudeCodeProcess(_settings(), "task")
    fake = _FakeProcess()
    fake.stderr = _RaisingReader(ValueError("stderr line too long"))  # type: ignore[assignment]
    proc._process = fake  # type: ignore[assignment]

    await proc._drain_stderr()  # raises once internally, then reaches EOF


async def test_wait_exit_returns_recorded_code_when_already_reaped():
    """[Unit] process: wait_exit returns the recorded code without awaiting wait.

    Scenario: the process's fake already carries a return code.

    Boundaries: the fast path returns the recorded code.

    On failure, first check: ``wait_exit`` must return the recorded code and never
    call ``wait``.
    """
    proc = ClaudeCodeProcess(_settings(), "task")
    fake = _FakeProcess(exit_code=0)
    fake.returncode = 7
    proc._process = fake  # type: ignore[assignment]

    assert await proc.wait_exit() == 7
    assert fake.wait_calls == 0


async def test_wait_exit_before_spawn_raises():
    """[Unit] process: wait_exit before spawn raises RuntimeError.

    Scenario: ``wait_exit`` is awaited on an un-entered process.

    Boundaries: no child has spawned.

    On failure, first check: the call must raise ``RuntimeError``.
    """
    with pytest.raises(RuntimeError):
        await ClaudeCodeProcess(_settings(), "task").wait_exit()


async def test_terminate_swallows_kill_oserror(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: a SIGKILL OSError is swallowed and the child still reaped.

    Scenario: a child ignores SIGTERM and its ``kill`` raises ``OSError`` (a
    SIGCHLD race), with a tiny grace period.

    Boundaries: the OSError from ``kill`` is caught narrowly; the child is reaped.

    On failure, first check: the terminate must complete and the child be reaped.
    """
    monkeypatch.setattr(process_mod, "_TERMINATE_GRACE_S", 0.01)
    proc = ClaudeCodeProcess(_settings(), "task")
    fake = _FakeProcess(completes=False, terminate_exits=False)

    def _kill_raises():
        """Record a SIGKILL that races with the child's own exit."""
        fake.kill_calls += 1
        fake.returncode = -9
        fake._exited.set()
        raise OSError("no such process")

    fake.kill = _kill_raises  # type: ignore[assignment]
    proc._process = fake  # type: ignore[assignment]

    await proc._terminate()  # must not raise despite kill() raising

    assert fake.kill_calls == 1
    assert fake.returncode == -9


async def test_terminate_noop_when_already_dead():
    """[Unit] process: _terminate is a no-op when the child already exited.

    Scenario: the process's fake already carries a return code.

    Boundaries: the guard short-circuits before sending any signal.

    On failure, first check: neither ``terminate`` nor ``kill`` may be called.
    """
    proc = ClaudeCodeProcess(_settings(), "task")
    fake = _FakeProcess()
    fake.returncode = 0
    proc._process = fake  # type: ignore[assignment]

    await proc._terminate()

    assert fake.terminate_calls == 0
    assert fake.kill_calls == 0


def test_stream_result_defaults_are_empty():
    """[Unit] process: ClaudeCodeStreamResult defaults to empty observability data.

    Scenario: a stream result is built with only the required fields.

    Boundaries: pure dataclass construction.

    On failure, first check: the tool-call/result tuples must be empty and the
    counts zero.
    """
    result = ClaudeCodeStreamResult(content="", usage=None, is_error=False)

    assert result.tool_calls == ()
    assert result.tool_results == ()
    assert result.frame_count == 0
    assert result.num_turns is None
