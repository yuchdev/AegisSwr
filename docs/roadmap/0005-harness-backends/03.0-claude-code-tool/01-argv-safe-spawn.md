# 01 - Argv-safe subprocess spawn

**Parent task:** 03.0 Claude Code Subprocess Tool
**State:** ⬜ Not started
**Depends on:** none (consumes `ClaudeCodeSettings` from Task 02.0)
**Blocks:** 02, 03, 04

## Objective

Stand up `aegis_swr/claude_code/process.py` with the argv builder and the
one-shot subprocess lifecycle: `build_argv()` (constructs the `claude` command
line from `ClaudeCodeSettings`, **never** including the task text) and
`ClaudeCodeProcess` (an `async` context manager that spawns the process via
`asyncio.create_subprocess_exec`, writes the task to **stdin**, exposes the
stdout stream for the subtask-02 parser, and reaps the child on every exit path).
This subtask fixes the **argv-safety** contract (C6.1): the task string reaches
the CLI only via stdin (or a disposable temp file), so it can never appear in a
`ps`/process listing on a shared host. No parsing and no `CodeResult` here —
just a safe, RAII-managed spawn whose stdout the next subtask consumes.

## File: `aegis_swr/claude_code/process.py`

```python
from __future__ import annotations

import asyncio
import re
from types import TracebackType
from typing import Final, Optional

from aegis_swr.claude_code.config import ClaudeCodeSettings

#: The only ``--output-format`` this backend uses: newline-delimited JSON so the
#: terminal ``result`` message's real ``usage`` block can be read (C6.2, C9).
_OUTPUT_FORMAT: Final[str] = "stream-json"

# argv-token whitelist: a single ``--allowedTools`` value may contain only these
# characters. A leading ``-`` (flag injection), a ``,``/``=``/whitespace/control
# char is rejected at the argv boundary - fail closed, mirroring OpenClaude's
# ``_validate_argv_token`` (openclaude/process.py).
_ARGV_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\A[A-Za-z0-9._-]+\Z")

# Grace period (seconds) between SIGTERM and the SIGKILL escalation when reaping
# the one-shot child, mirroring OpenClaudeProcess._terminate_managed.
_TERMINATE_GRACE_S: Final[float] = 5.0


def build_argv(settings: ClaudeCodeSettings) -> list[str]:
    """Assemble the argv-safe ``claude`` command line (C6.1, C6.3).

    Constructs ``claude -p --output-format stream-json --verbose
    --allowedTools <csv> --permission-mode <mode> --max-turns <n>`` from
    *settings* only. The **task string is deliberately absent** - it is fed over
    stdin by :class:`ClaudeCodeProcess`, never as a bare CLI argument, so it
    cannot leak via ``ps`` (C6.1). ``-p`` (print / non-interactive) with stdin
    piped makes ``claude`` read the prompt from stdin; ``--verbose`` is required
    by the CLI whenever ``--output-format stream-json`` is used under ``-p``.
    Every ``allowed_tools`` value is passed through :func:`_validate_argv_token`
    (fail closed) before it reaches the argv. ``--dangerously-skip-permissions``
    is never emitted here and was already rejected at ``ClaudeCodeSettings``
    validation (Task 02.0, C6.3).

    **Auth scope (C6.6 / C7):** this builder adds no credential flags and never
    passes ``--bare``; ``auth_mode`` handling (including the
    ``--bare``-never-in-subscription-mode rule) is Task 04.0. Under this task's
    ``auth_mode="auto"`` the process inherits the ambient credential env
    unexamined.

    :param settings: Validated :class:`ClaudeCodeSettings` (Task 02.0).
    :raises ClaudeCodeConfigError: If an ``allowed_tools`` value is not a safe
        single argv token. (Forward-declared alongside
        :class:`ClaudeCodeUnavailableError` in this task; canonical home is
        Task 05.0's ``claude_code/exceptions.py``.)
    :return: The argument vector for :func:`asyncio.create_subprocess_exec`,
        with the task string absent by construction.
    """
    ...


def _validate_argv_token(value: str, *, field: str) -> str:
    """Validate a single ``--allowedTools`` entry at the argv boundary.

    Accepts only ``\\A[A-Za-z0-9._-]+\\Z`` and rejects a leading ``-`` (which
    would be reparsed as a flag). The ``\\A``/``\\Z`` anchors reject a trailing
    newline that ``$`` would admit. Never silently drops a bad value - raises so
    the spawn aborts before any process starts. Directly mirrors
    ``OpenClaudeProcess._validate_argv_token``.

    :param value: A single ``allowed_tools`` entry.
    :param field: Originating settings field, for the payload-free error message.
    :raises ClaudeCodeConfigError: If *value* is not a safe single token.
    :return: *value* unchanged when it is a safe single token.
    """
    ...


class ClaudeCodeProcess:
    """Async context manager owning one one-shot ``claude`` subprocess (C6).

    A fresh process is spawned per :meth:`ClaudeCodeTool.delegate` call and
    reaped when it exits - there is no persistent sidecar, no health-check
    lifecycle (contrast ``OpenClaudeProcess``, which manages a long-lived gRPC
    sidecar). This class owns the **only** ``asyncio.create_subprocess_exec``
    call in the package (C3): ``subprocess.Popen`` is never used on this async
    path (C13). The task text is written to the child's stdin and stdin is then
    closed; the argv (from :func:`build_argv`) carries no task text (C6.1).

    Usage::

        async with ClaudeCodeProcess(settings, task) as proc:
            async for line in proc.stdout_lines():   # subtask 02
                ...

    On exit the child is always reaped (SIGTERM -> grace -> SIGKILL) and stderr
    is drained; no zombie or leaked pipe remains, and no unredacted stderr text
    reaches a log sink (C13).

    :ivar _settings: Validated :class:`ClaudeCodeSettings`.
    :ivar _task: The open-ended task string, written to stdin - never argv (C6.1)
        and never logged (C13).
    :ivar _process: The owned subprocess handle, or ``None`` before entry / after
        reap.
    :ivar _stderr_task: Background task draining the child's stderr, or ``None``
        before the spawn.
    """

    def __init__(self, settings: ClaudeCodeSettings, task: str):
        """Store configuration and the task; perform no I/O and spawn nothing.

        :param settings: Validated :class:`ClaudeCodeSettings` (Task 02.0).
        :param task: The open-ended code-navigation task, fed to stdin at entry.
        """
        self._settings = settings
        self._task = task
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None

    async def __aenter__(self) -> ClaudeCodeProcess:
        """Spawn the child, feed the task over stdin, and return ``self``.

        Builds the argv via :func:`build_argv`, spawns via
        :func:`asyncio.create_subprocess_exec` with ``stdin``/``stdout``/
        ``stderr`` piped and ``cwd`` set to the **mandatory disposable**
        ``settings.scratch_cwd`` (C6.3 - the child never inherits an
        attacker-influenced cwd), writes ``self._task`` to stdin, then closes
        stdin so the child sees EOF and begins. Starts a background stderr drain
        immediately so startup diagnostics are captured and no stderr
        backpressure stalls the child. Any failure *after* the process is live
        reaps it before the exception propagates (always-terminate invariant,
        mirroring ``OpenClaudeProcess``).

        :raises ClaudeCodeConfigError: If argv construction rejects a value.
        :return: ``self``, with stdout ready to iterate (subtask 02).
        """
        ...

    async def _write_task_stdin(self):
        """Write ``self._task`` to the child's stdin, then close it (C6.1).

        The task reaches the CLI **only** here, over stdin - never via argv - so
        it is invisible to ``ps``. The task bytes are never logged (C13). Closing
        stdin signals EOF so ``claude -p`` starts processing the piped prompt.
        A disposable temp-file variant is permitted where a platform cannot
        stream large prompts over a pipe; if used, the file lives under
        ``settings.scratch_cwd`` and is deleted on exit (RAII).
        """
        ...

    def stdout_lines(self) -> asyncio.StreamReader:
        """Return the child's stdout stream for the subtask-02 NDJSON parser.

        :raises RuntimeError: If accessed before ``__aenter__`` has spawned the
            child (no stream exists yet).
        :return: The live ``asyncio.StreamReader`` for stdout.
        """
        ...

    async def _drain_stderr(self):
        """Read the child's stderr to EOF, logging each line at DEBUG only (C13).

        Each line is passed as a bound argument (a value, never the format
        template) so untrusted text cannot inject format directives, and the
        loguru ``SensitiveFilter`` on every sink redacts it. A per-line
        decode/read failure is caught narrowly (``ValueError``/``OSError``/
        ``asyncio.LimitOverrunError``) and the drain continues; ``CancelledError``
        propagates. Mirrors ``OpenClaudeProcess._forward_stderr``.
        """
        ...

    async def _terminate(self):
        """Reap the owned child: SIGTERM, grace wait, then SIGKILL (RAII).

        Operates only on the stored asyncio handle (never ``os.kill`` on a raw
        pid), guards each step on ``returncode is None``, and awaits ``wait()``
        so no zombie remains. Idempotent: a no-op when never spawned or already
        dead. Mirrors ``OpenClaudeProcess._terminate_managed``.
        """
        ...

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Optional[bool]:
        """Reap the child and drain stderr; never suppress an in-flight exception.

        Cancels/awaits the stderr drain and runs :meth:`_terminate` (both
        idempotent), then returns ``None`` so any exception from the ``async
        with`` body propagates unchanged.

        :param exc_type: Exception type raised in the body, if any.
        :param exc: Exception instance raised in the body, if any.
        :param tb: Traceback for the raised exception, if any.
        """
        ...
```

## Implementation notes

- **Argv-safety is the whole point (C6.1).** The task string is *structurally*
  absent from argv because :func:`build_argv` takes only `settings` and never
  the task; the task travels through :meth:`_write_task_stdin`. Task 11.0 asserts
  this by constructing an argv with a sentinel task and checking the sentinel
  substring appears in **no** argv element.
- **`-p` + stdin.** `claude -p` (print / non-interactive) reads the prompt from
  stdin when stdin is piped and no positional prompt is given; this is the
  documented headless entry point. Confirm the exact `--allowedTools` join
  format (comma-joined single token vs repeated flags) and the `--verbose`
  requirement against the installed CLI at implementation time and note any
  deviation.
- **`asyncio.create_subprocess_exec`, never `subprocess.Popen`** on this async
  path (C13). Pass `stdin=PIPE, stdout=PIPE, stderr=PIPE`, `cwd=scratch_cwd`.
  This is the **only** module that spawns the `claude` child (C3).
- **Scratch cwd is mandatory (C6.3).** `settings.scratch_cwd` (Task 02.0) is the
  child's cwd so it never inherits an attacker-influenced working directory. The
  disposable-temp-file prompt variant, if used, must also live under it and be
  deleted on exit.
- **Env is inherited unexamined in this task (C6.6 / C7).** No credential env
  scrubbing or injection here; that is Task 04.0. Do not add `--bare`.
- **RAII / always-terminate.** Every exit path (normal, exception, cancellation)
  reaps the child and drains stderr, mirroring `OpenClaudeProcess`'s
  always-terminate invariant, so a one-shot spawn never orphans a process.
- **Forward-declared exceptions.** `ClaudeCodeConfigError` (argv validation) and
  `ClaudeCodeUnavailableError` (subtasks 03-04) are **forward-declared** in this
  package for now, exactly as Milestone 0004's Task 01.0 forward-declared
  `OpenClaudeConfigError` before its canonical home existed (see the note in
  `openclaude/exceptions.py`). Task 05.0 moves the canonical definitions into
  `claude_code/exceptions.py` and re-exports them so imports keep resolving.

## Constraints

- `from __future__ import annotations`; `Optional[T]` from `typing`, never
  `T | None` (C13).
- `asyncio.create_subprocess_exec` only; no `subprocess.Popen`, no `os.system`,
  no shell (`shell=False` semantics) on this path (C13).
- The task string appears in **no** argv element (C6.1); it is written to stdin
  (or a disposable scratch temp file) only.
- No task bytes, response text, argv, or stderr text is logged unredacted;
  `SensitiveFilter` on every sink; stderr only at DEBUG with the line as a bound
  argument (C13).
- No bare `except:`; per-line stderr failures caught narrowly; every exit path
  reaps the child (SIGTERM -> grace -> SIGKILL) and closes pipes (C13).
- No `Any` in any signature; `ruff` and `replace_optional.py --check` clean.
- Every public class/function has an RST-style docstring (C13).

## Success criteria

- [ ] `build_argv(settings)` returns `claude -p --output-format stream-json
      --verbose --allowedTools … --permission-mode … --max-turns …` with the
      task string absent from every element.
- [ ] Given a sentinel task, the sentinel substring appears in **no** element of
      the constructed argv (C6.1, asserted in Task 11.0).
- [ ] `_validate_argv_token` rejects a leading `-`, a `,`/`=`/whitespace/newline,
      and any control char; accepts `[A-Za-z0-9._-]+`.
- [ ] `--dangerously-skip-permissions` is never present in the argv (and cannot
      be, given Task 02.0's settings rejection) (C6.3).
- [ ] `ClaudeCodeProcess` spawns via `asyncio.create_subprocess_exec` with
      `cwd == settings.scratch_cwd`, writes the task to stdin, and closes stdin.
- [ ] `__aexit__` reaps the child (SIGTERM -> grace -> SIGKILL) and drains
      stderr on the normal, exception, and cancellation paths; no zombie or
      leaked pipe remains.
- [ ] No task/argv/stderr text is logged unredacted; stderr logged only at DEBUG
      via a bound argument (C13).
- [ ] No `subprocess.Popen` / `os.system` / shell invocation appears in the file.
- [ ] `ruff` and `replace_optional.py --check` clean; no `Any` in any signature.
