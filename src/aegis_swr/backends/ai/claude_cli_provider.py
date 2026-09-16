"""Local ``claude`` CLI AI backend (no API key required).

Drives the locally-installed ``claude`` command headlessly so the agentic panel
can run with **no** ``ANTHROPIC_API_KEY``: authentication is the CLI's own
subscription / OAuth login and Aegis never reads or forwards a credential. A
fresh one-shot process is spawned per :meth:`~aegis_swr.backends.ai.base._BaseAIBackend.generate`
round-trip::

    claude -p --output-format json --model <model> \
        --system-prompt <persona> --allowedTools "" --restricted

Security and safety invariants:

* **The incident transcript never touches argv** (repo rule C13 / security §3):
  the flattened ``messages`` travel over the child's stdin, so payload text can
  never leak via a ``ps`` / process listing. Only the *persona* system prompt is
  passed on argv (via ``--system-prompt``), which is not incident payload.
* **``--bare`` is never emitted** - it would force ``ANTHROPIC_API_KEY`` /
  ``apiKeyHelper`` auth and defeat the no-API-key purpose.
* **Every external call has a timeout and a defined failure path**: the child is
  reaped (terminate -> grace -> kill) and any per-call temporary working
  directory is removed on every exit path (success, error, timeout,
  cancellation). Process-level failures surface as
  :class:`~aegis_swr.core.exceptions.AIBackendError`.
* **No raw prompt/response text is ever logged** (``loguru`` with the project
  ``SensitiveFilter``); only the model, argv *shape*, exit code, and durations.

Structured output is prompt-driven: the CLI exposes no forced tool use, so a
schema request appends a "reply with ONLY this JSON" instruction to the system
prompt and lets :class:`~aegis_swr.backends.ai.base._BaseAIBackend` validate the
result and run its one-shot correction retry.

The NDJSON stream parser reuses the frame helpers from
:mod:`aegis_swr.claude_code.process` (the Code Intelligence harness) rather than
inventing a second parser, while staying decoupled from that harness's settings
types.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Final, Optional, Union

from loguru import logger
from pydantic import BaseModel

from aegis_swr.backends.ai.base import _BaseAIBackend
from aegis_swr.claude_code.process import _extract_assistant_text, _extract_usage
from aegis_swr.config.settings import ClaudeCliSettings
from aegis_swr.core.exceptions import AIBackendError

#: ``--output-format`` for the one-shot ``generate`` path: a single JSON envelope
#: carrying ``result`` (assistant text), ``usage`` (real token counts),
#: ``is_error`` and ``subtype``.
_OUTPUT_FORMAT_JSON: Final[str] = "json"

#: ``--output-format`` for the streaming path: newline-delimited JSON frames.
_OUTPUT_FORMAT_STREAM: Final[str] = "stream-json"

#: Grace period (seconds) between terminate and the hard kill when reaping the
#: one-shot child, mirroring the Claude Code harness.
_TERMINATE_GRACE_S: Final[float] = 5.0

#: Base backoff (seconds) for the process-level retry; doubled per attempt.
_BACKOFF_BASE_S: Final[float] = 0.5

#: The ``result`` envelope ``subtype`` denoting a clean run; any other subtype is
#: treated as an error alongside the ``is_error`` flag.
_RESULT_SUCCESS_SUBTYPE: Final[str] = "success"

#: Cap on the CLI-reported error reason echoed into an :class:`AIBackendError`,
#: so a long or payload-bearing body can never be dumped whole (security §3).
_MAX_ERROR_REASON_CHARS: Final[int] = 300

#: Claude families that expose an extended-thinking trace, mirroring the
#: Anthropic backend's capability markers. Kept local so this provider does not
#: depend on the Anthropic backend's internals.
_REASONING_MODEL_MARKERS: Final[tuple[str, ...]] = (
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",
    "claude-3-7",
)


def _find_repo_root() -> Path:
    """Locate the repository root by walking up from the current directory.

    Walks upward from ``Path.cwd()`` looking for a ``.git`` marker; falls back to
    ``Path.cwd()`` when none is found and treats that as the root to protect.
    Used to reject an explicit ``cwd`` that would let a one-shot ``claude``
    process operate over the live source tree (mirrors the harness guard).

    :return: The resolved repository root path.
    """
    start = Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def _flatten_messages(messages: list[dict[str, Any]]) -> str:
    """Render the provider-neutral *messages* into a single stdin transcript.

    A lone user message is sent verbatim; a multi-turn conversation is rendered
    as clearly delimited, role-labelled turns so the CLI (which reads one prompt
    from stdin) sees the full context.

    :param messages: The conversation messages (``{"role", "content"}`` dicts).
    :return: The transcript string to feed to the child's stdin.
    """
    if len(messages) == 1 and messages[0].get("role") == "user":
        return str(messages[0].get("content", ""))
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role", "user")).upper()
        content = str(message.get("content", ""))
        parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts)


def _strip_code_fence(text: str) -> str:
    """Strip a wrapping Markdown code fence from a structured-output *text*.

    Structured output on this backend is prompt-driven - the CLI exposes no
    forced tool use - so the model frequently honours the schema but still wraps
    the object in a `````json`` fence. The API-backed providers cannot hit this
    (they use a JSON/tool-use mode that returns a bare object), so the fence is
    peeled here rather than in
    :class:`~aegis_swr.backends.ai.base._BaseAIBackend`, whose ``json.loads``
    would otherwise raise and burn the one-shot correction retry on a reply that
    was already correct.

    Only a fence that opens the first line and closes the last is removed, with
    an optional language tag (``json``) after the backticks. Text without a
    wrapping fence is returned unchanged, so a bare object is never altered.

    :param text: The raw assistant text from the CLI envelope.
    :return: The text with a wrapping code fence removed, stripped of
        surrounding whitespace.
    """
    stripped = text.strip()
    if not stripped.startswith("```") or not stripped.endswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) < 2:  # noqa: PLR2004 - a lone "```…```" line carries no body
        return stripped
    # Drop the opening fence (plus any language tag) and the closing fence.
    return "\n".join(lines[1:-1]).strip()


def _error_envelope_reason(envelope: dict[str, Any]) -> str:
    """Summarise *why* an error envelope failed, for a payload-free message.

    On an error envelope the CLI puts its own human-readable cause (usage limit
    reached, credit balance too low, upstream API error, …) in ``result``. That
    is CLI/transport diagnostics rather than incident payload, but it is
    truncated and single-lined here so an oversized or multi-line body can never
    dump a transcript into a log or exception (repo security §3).

    :param envelope: The parsed ``result`` envelope.
    :return: A short ``reason=…`` fragment, or an empty string when the envelope
        carries no usable reason.
    """
    reason = envelope.get("result")
    if not isinstance(reason, str) or not reason.strip():
        reason = envelope.get("error") if isinstance(envelope.get("error"), str) else None
    if not isinstance(reason, str) or not reason.strip():
        return ""
    flattened = " ".join(reason.split())
    if len(flattened) > _MAX_ERROR_REASON_CHARS:
        flattened = f"{flattened[:_MAX_ERROR_REASON_CHARS]}…"
    return f", reason={flattened!r}"


def _extract_partial_text(frame: dict[str, Any]) -> Optional[str]:
    """Return the incremental text of a ``stream_event`` ``text_delta`` frame.

    Handles the partial-message frames emitted under
    ``--include-partial-messages`` (``{"type": "stream_event", "event":
    {"type": "content_block_delta", "delta": {"type": "text_delta", "text":
    ...}}}``). Any other shape yields ``None`` (never raises).

    :param frame: One parsed NDJSON frame.
    :return: The delta text, or ``None`` when the frame is not a text delta.
    """
    if frame.get("type") != "stream_event":
        return None
    event = frame.get("event")
    if not isinstance(event, dict) or event.get("type") != "content_block_delta":
        return None
    delta = event.get("delta")
    if not isinstance(delta, dict) or delta.get("type") != "text_delta":
        return None
    text = delta.get("text")
    return text if isinstance(text, str) else None


class _ClaudeCliProcess:
    """RAII async context manager owning one one-shot ``claude`` subprocess.

    Spawns the child with stdin/stdout/stderr piped, feeds the transcript over
    stdin, drains stderr in the background (DEBUG only, redacted), and always
    reaps the child (terminate -> grace -> kill) and removes any per-call
    temporary working directory on exit - success, error, timeout, or
    cancellation.

    :ivar _argv: The fully-built command line (task text is absent by design).
    :ivar _stdin_text: The transcript written to the child's stdin, then closed.
    :ivar _explicit_cwd: A validated explicit working directory, or ``None`` to
        use a fresh per-call temporary directory.
    :ivar _model_name: The resolved model, for payload-free error/log messages.
    """

    def __init__(
        self,
        argv: list[str],
        stdin_text: str,
        explicit_cwd: Optional[str],
        model_name: str,
    ):
        """Store the spawn parameters; perform no I/O and spawn nothing."""
        self._argv = argv
        self._stdin_text = stdin_text
        self._explicit_cwd = explicit_cwd
        self._model_name = model_name
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None
        self._temp_dir: Optional[str] = None

    async def __aenter__(self) -> _ClaudeCliProcess:
        """Spawn the child, feed stdin, and return ``self`` (always-reap on error).

        :raises AIBackendError: When the ``claude`` binary cannot be spawned.
        :return: ``self`` with stdout ready to read.
        """
        cwd = self._explicit_cwd
        if cwd is None:
            self._temp_dir = tempfile.mkdtemp(prefix="aegis-claude-cli-")
            cwd = self._temp_dir

        logger.debug(
            "claude_cli spawn: model={} argv_tokens={} temp_cwd={}",
            self._model_name,
            len(self._argv),
            self._temp_dir is not None,
        )
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
        except OSError as exc:
            self._cleanup_temp_dir()
            raise AIBackendError(f"claude CLI ({self._model_name}) subprocess could not be spawned") from exc

        self._stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            await self._write_stdin()
        except BaseException:
            # Always-terminate: once the child is live, any failure feeding stdin
            # (including cancellation) reaps it and cleans up before propagating.
            await self._stop_stderr_drain()
            await self._terminate()
            self._cleanup_temp_dir()
            raise
        return self

    async def __aexit__(self, *exc_info: Any) -> Optional[bool]:
        """Reap the child, drain stderr, and remove the temp dir; never suppress."""
        await self._stop_stderr_drain()
        await self._terminate()
        self._cleanup_temp_dir()
        return None

    @property
    def stdout(self) -> asyncio.StreamReader:
        """Return the child's stdout stream for the caller to read.

        :raises RuntimeError: If accessed before the child has spawned.
        :return: The live stdout ``asyncio.StreamReader``.
        """
        process = self._process
        if process is None or process.stdout is None:
            raise RuntimeError("claude CLI stdout is not available until the child has spawned")
        return process.stdout

    async def read_stdout(self) -> bytes:
        """Read the child's stdout to EOF and return the raw bytes."""
        return await self.stdout.read()

    async def wait_exit(self) -> int:
        """Await the child's exit and return its exit code.

        :raises RuntimeError: If called before the child has spawned.
        :return: The process exit code.
        """
        process = self._process
        if process is None:
            raise RuntimeError("claude CLI wait_exit called before the child spawned")
        if process.returncode is not None:
            return process.returncode
        return await process.wait()

    async def _write_stdin(self):
        """Write the transcript to the child's stdin, then close it (C13).

        The transcript reaches the CLI **only** here, over stdin - never via argv -
        so it is invisible to ``ps``, and its bytes are never logged.
        """
        process = self._process
        if process is None or process.stdin is None:
            return
        process.stdin.write(self._stdin_text.encode())
        await process.stdin.drain()
        process.stdin.close()

    async def _drain_stderr(self):
        """Read the child's stderr to EOF, logging each line at DEBUG only.

        Each line is passed as a bound argument (never the format template) so
        untrusted text cannot inject format directives, and the ``loguru``
        ``SensitiveFilter`` on every sink redacts it. Per-line read failures are
        caught narrowly and the drain continues; ``CancelledError`` propagates.
        """
        process = self._process
        if process is None or process.stderr is None:
            return
        stream = process.stderr
        while True:
            try:
                line = await stream.readline()
                if not line:
                    return
                logger.debug("claude CLI stderr: {}", line.decode(errors="replace").rstrip())
            except (ValueError, OSError, asyncio.LimitOverrunError) as exc:
                logger.debug("claude CLI stderr drain: transient read error: {}", type(exc).__name__)
                continue

    async def _stop_stderr_drain(self):
        """Cancel the stderr-draining task and await its clean shutdown (idempotent)."""
        task = self._stderr_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _terminate(self):
        """Reap the owned child: terminate, grace wait, then kill (idempotent)."""
        process = self._process
        if process is None or process.returncode is not None:
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_S)
        except asyncio.TimeoutError:
            if process.returncode is None:
                with contextlib.suppress(ProcessLookupError, OSError):
                    process.kill()
            await process.wait()

    def _cleanup_temp_dir(self):
        """Remove the per-call temporary working directory, if one was created."""
        if self._temp_dir is not None:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None


class ClaudeCliBackend(_BaseAIBackend[ClaudeCliSettings]):
    """AI backend that drives the local ``claude`` CLI headlessly (no API key).

    :param settings: The ``claude_cli`` provider sub-config; the model identity is
        read from :attr:`~aegis_swr.config.settings.ClaudeCliSettings.resolved_model`
        and all other knobs (binary, timeout, retries, cwd) from the typed fields.
    :raises AIBackendError: When ``settings.cwd`` is the repository root or an
        ancestor of it.
    """

    def __init__(self, settings: ClaudeCliSettings):
        """Store *settings* and validate any explicit working directory."""
        super().__init__(settings)
        self._explicit_cwd = self._validate_cwd(settings.cwd)

    @staticmethod
    def _validate_cwd(cwd: Optional[str]) -> Optional[str]:
        """Reject a ``cwd`` that is the repository root or an ancestor of it.

        :param cwd: The configured working directory, or ``None`` for a per-call
            temporary directory.
        :return: The resolved absolute path, or ``None`` when unset.
        :raises AIBackendError: When *cwd* would let the one-shot process operate
            over the live source tree.
        """
        if cwd is None:
            return None
        resolved = Path(cwd).expanduser().resolve()
        repo_root = _find_repo_root()
        if repo_root == resolved or repo_root.is_relative_to(resolved):
            raise AIBackendError("claude_cli cwd must not be the repository root or an ancestor of it")
        return str(resolved)

    @property
    def has_reasoning(self) -> bool:
        """``True`` when the configured Claude model exposes a reasoning trace."""
        return any(marker in self.model_name for marker in _REASONING_MODEL_MARKERS)

    def _augment_system_prompt(
        self,
        system_prompt: str,
        output_schema: Optional[type[BaseModel]],
    ) -> str:
        """Append a JSON-only instruction to *system_prompt* for structured output.

        The CLI has no forced tool use, so schema conformance is prompt-driven;
        :class:`~aegis_swr.backends.ai.base._BaseAIBackend` validates the reply and
        runs the correction retry.

        :param system_prompt: The persona system prompt.
        :param output_schema: The requested output schema, or ``None`` for
            free-form text.
        :return: The system prompt, augmented when a schema is requested.
        """
        if output_schema is None:
            return system_prompt
        schema_json = json.dumps(output_schema.model_json_schema())
        return (
            f"{system_prompt}\n\n"
            "Reply with ONLY a single JSON object (no prose, no markdown code fences) "
            f"that validates against this JSON Schema:\n{schema_json}"
        )

    def _build_argv(
        self,
        system_prompt: str,
        output_format: str,
        output_schema: Optional[type[BaseModel]],
    ) -> list[str]:
        """Assemble the argv (task text is deliberately absent - it goes via stdin).

        ``--bare`` is never emitted (it would force API-key auth). ``--restricted``
        removes Bash/PowerShell/REPL tools and ``--allowedTools ""`` grants none,
        so the one-shot process is a pure text generator.

        :param system_prompt: The persona system prompt (augmented for schemas).
        :param output_format: ``json`` (one envelope) or ``stream-json`` (NDJSON).
        :param output_schema: The requested schema, or ``None`` for free-form text.
        :return: The argument vector for :func:`asyncio.create_subprocess_exec`.
        """
        argv = [
            self._settings.binary,
            "-p",
            "--output-format",
            output_format,
            "--model",
            self.model_name,
            "--system-prompt",
            self._augment_system_prompt(system_prompt, output_schema),
            "--allowedTools",
            "",
            "--restricted",
        ]
        if output_format == _OUTPUT_FORMAT_STREAM:
            # ``--verbose`` is required by the CLI whenever stream-json is used
            # under ``-p``; ``--include-partial-messages`` yields token deltas.
            argv += ["--verbose", "--include-partial-messages"]
        return argv

    def _parse_json_envelope(
        self,
        stdout_bytes: bytes,
        exit_code: int,
    ) -> tuple[str, dict[str, int]]:
        """Parse the single JSON envelope from ``--output-format json``.

        :param stdout_bytes: The child's raw stdout.
        :param exit_code: The child's exit code.
        :return: ``(result_text, usage)`` where ``usage`` carries
            ``input_tokens`` / ``output_tokens``.
        :raises AIBackendError: On a non-zero exit, unparseable output, an
            ``is_error`` / non-``success`` envelope, or a missing result. The
            message names the model and a short reason - never prompt/payload text.
        """
        text = stdout_bytes.decode(errors="replace").strip()
        try:
            envelope = json.loads(text)
        except ValueError as exc:
            if exit_code != 0:
                raise AIBackendError(
                    f"claude CLI ({self.model_name}) exited with code {exit_code} and no parseable output"
                ) from exc
            raise AIBackendError(f"claude CLI ({self.model_name}) returned unparseable output") from exc

        if not isinstance(envelope, dict):
            raise AIBackendError(f"claude CLI ({self.model_name}) returned a non-object result")

        subtype = envelope.get("subtype")
        if bool(envelope.get("is_error", False)) or (isinstance(subtype, str) and subtype != _RESULT_SUCCESS_SUBTYPE):
            raise AIBackendError(
                f"claude CLI ({self.model_name}) reported an error "
                f"(subtype={subtype}, exit={exit_code}){_error_envelope_reason(envelope)}"
            )

        if exit_code != 0:
            raise AIBackendError(f"claude CLI ({self.model_name}) exited with code {exit_code}")

        result = envelope.get("result")
        if not isinstance(result, str):
            raise AIBackendError(f"claude CLI ({self.model_name}) returned no result text")

        usage = _extract_usage(envelope)
        usage_dict = (
            {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}
            if usage is not None
            else {"input_tokens": 0, "output_tokens": 0}
        )
        return result, usage_dict

    async def _run_once(
        self,
        argv: list[str],
        stdin_text: str,
    ) -> tuple[str, dict[str, int]]:
        """Run one one-shot ``claude`` process to completion and parse its envelope.

        :param argv: The command line (task text absent).
        :param stdin_text: The transcript to feed over stdin.
        :return: ``(result_text, usage)`` from :meth:`_parse_json_envelope`.
        :raises AIBackendError: On spawn failure, timeout, or an error envelope.
        """
        async with _ClaudeCliProcess(argv, stdin_text, self._explicit_cwd, self.model_name) as proc:
            try:
                stdout_bytes = await asyncio.wait_for(
                    proc.read_stdout(),
                    timeout=self._settings.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise AIBackendError(
                    f"claude CLI ({self.model_name}) timed out after {self._settings.timeout_seconds}s"
                ) from exc
            exit_code = await proc.wait_exit()
        return self._parse_json_envelope(stdout_bytes, exit_code)

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]],
    ) -> tuple[Union[str, dict[str, Any]], dict[str, int]]:
        """Run one CLI round-trip, retrying on process-level failure with backoff.

        :param system_prompt: The persona system prompt.
        :param messages: The conversation messages (flattened onto stdin).
        :param output_schema: When given, a JSON-only instruction is appended to
            the system prompt; the base class validates the reply.
        :return: ``(result_text, usage)``; for a schema request ``result_text`` is
            the model's JSON string, which the base class parses and validates.
        :raises AIBackendError: When every attempt fails at the process level.
        """
        argv = self._build_argv(system_prompt, _OUTPUT_FORMAT_JSON, output_schema)
        stdin_text = _flatten_messages(messages)

        last_exc: Optional[AIBackendError] = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                text, usage = await self._run_once(argv, stdin_text)
                # Only a schema request must be bare JSON for the base class to
                # parse; free-form text keeps any fence the model meant to send.
                if output_schema is not None:
                    text = _strip_code_fence(text)
                return text, usage
            except AIBackendError as exc:
                last_exc = exc
                if attempt >= self._settings.max_retries:
                    raise
                backoff = _BACKOFF_BASE_S * (2**attempt)
                logger.warning(
                    "claude CLI ({}) attempt {}/{} failed at the process level; retrying in {}s",
                    self.model_name,
                    attempt + 1,
                    self._settings.max_retries + 1,
                    backoff,
                )
                await asyncio.sleep(backoff)
        # Unreachable: the final attempt re-raises above. Present for the type
        # checker and as defence in depth.
        raise last_exc if last_exc is not None else AIBackendError(f"claude CLI ({self.model_name}) failed")

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """Stream free-form response text as it arrives from the CLI.

        Parses the NDJSON (``stream-json`` + ``--include-partial-messages``)
        output and yields only assistant text deltas: ``text_delta`` frames when
        the CLI emits partial messages, else the text of complete ``assistant``
        frames (never both, so no token is duplicated).

        :param system_prompt: The persona system prompt.
        :param messages: The conversation messages (flattened onto stdin).
        :raises AIBackendError: On spawn failure, timeout, or a non-zero exit.
        """
        argv = self._build_argv(system_prompt, _OUTPUT_FORMAT_STREAM, None)
        stdin_text = _flatten_messages(messages)

        async with _ClaudeCliProcess(argv, stdin_text, self._explicit_cwd, self.model_name) as proc:
            reader = proc.stdout
            saw_partial = False
            while True:
                try:
                    raw = await asyncio.wait_for(reader.readline(), timeout=self._settings.timeout_seconds)
                except asyncio.TimeoutError as exc:
                    raise AIBackendError(
                        f"claude CLI stream ({self.model_name}) timed out after {self._settings.timeout_seconds}s"
                    ) from exc
                except (ValueError, asyncio.LimitOverrunError) as exc:
                    # An over-long or transiently unreadable line is non-fatal:
                    # skip it and keep streaming. Log the reason (type only) with
                    # the model - never the line content, which is payload (C13).
                    logger.debug(
                        "claude CLI stream ({}): skipping unreadable line ({})",
                        self.model_name,
                        type(exc).__name__,
                    )
                    continue
                if not raw:
                    break
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    frame = json.loads(line)
                except ValueError:
                    # A malformed NDJSON frame is skipped defensively so a CLI
                    # minor-version drift never crashes the stream. The offending
                    # line is payload and is never logged (C13).
                    logger.debug("claude CLI stream ({}): skipping malformed NDJSON frame", self.model_name)
                    continue
                if not isinstance(frame, dict):
                    continue

                delta = _extract_partial_text(frame)
                if delta:
                    saw_partial = True
                    yield delta
                    continue
                if not saw_partial and frame.get("type") == "assistant":
                    text = _extract_assistant_text(frame)
                    if text:
                        yield text
            exit_code = await proc.wait_exit()

        if exit_code != 0:
            raise AIBackendError(f"claude CLI stream ({self.model_name}) exited with code {exit_code}")
