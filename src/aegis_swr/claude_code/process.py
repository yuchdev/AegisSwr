"""One-shot ``claude`` subprocess spawn and ``stream-json`` (NDJSON) parsing.

This module owns the **only** ``asyncio.create_subprocess_exec`` call in the
Claude Code backend (contract C3): a fresh ``claude -p … --output-format
stream-json`` process is spawned per :meth:`~aegis_swr.claude_code.tool.ClaudeCodeTool.delegate`
call and reaped on every exit path (SIGTERM → grace → SIGKILL). It provides:

* :func:`build_argv` — the argv-safe command-line builder. The task string is
  **structurally absent** from argv (it takes only ``settings``), so it can never
  leak via a ``ps``/process listing on a shared host (C6.1). The task travels
  over the child's stdin instead (:meth:`ClaudeCodeProcess._write_task_stdin`).
* :class:`ClaudeCodeProcess` — the RAII async context manager that spawns the
  child, feeds the task over stdin, exposes stdout for the parser, drains stderr,
  and always reaps the child.
* :func:`parse_stream` — the NDJSON reducer that turns the whole stdout stream
  into one frozen :class:`ClaudeCodeStreamResult` carrying the accumulated
  assistant text and the **real** token usage from the terminal ``result``
  message (``usage.input_tokens + usage.output_tokens``, C6.2/C9).

No raw task text, response text, argv, or stderr text is ever logged unredacted;
``loguru`` with the project ``SensitiveFilter`` guards every sink and stderr is
logged only at ``DEBUG`` as a bound argument (C13). No bare ``except:``; per-line
failures are caught narrowly (``ValueError``/``OSError``/``LimitOverrunError``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from dataclasses import dataclass
from types import TracebackType
from typing import Final, Optional

from loguru import logger

from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError, ClaudeCodeUnavailableError

#: The only ``--output-format`` this backend uses: newline-delimited JSON so the
#: terminal ``result`` message's real ``usage`` block can be read (C6.2, C9).
_OUTPUT_FORMAT: Final[str] = "stream-json"

#: NDJSON ``type`` discriminators emitted by ``claude --output-format
#: stream-json``: ``system`` (init/meta, ignored), ``assistant``/``user`` (turn
#: messages), and the single terminal ``result`` message carrying real ``usage``.
_TYPE_ASSISTANT: Final[str] = "assistant"
_TYPE_USER: Final[str] = "user"
_TYPE_RESULT: Final[str] = "result"

#: The ``result`` message ``subtype`` denoting a clean run; any other subtype is
#: treated as an error signal alongside the ``is_error`` flag.
_RESULT_SUCCESS_SUBTYPE: Final[str] = "success"

#: argv-token whitelist: a single ``--allowedTools`` value may contain only these
#: characters. A leading ``-`` (flag injection), a ``,``/``=``/whitespace/control
#: char is rejected at the argv boundary — fail closed, mirroring OpenClaude's
#: ``_validate_argv_token`` (openclaude/process.py).
_ARGV_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\A[A-Za-z0-9._-]+\Z")

#: Grace period (seconds) between SIGTERM and the SIGKILL escalation when reaping
#: the one-shot child, mirroring ``OpenClaudeProcess._terminate_managed``.
_TERMINATE_GRACE_S: Final[float] = 5.0

#: The single env var that carries a Claude.ai subscription login credential for
#: non-interactive use (``claude setup-token``). Forwarded **by name** in
#: subscription mode; its value is never read by Aegis (C7/C13).
_SUBSCRIPTION_TOKEN_VAR: Final[str] = "CLAUDE_CODE_OAUTH_TOKEN"

#: Credential/routing env vars that outrank a subscription login (C7 precedence
#: ranks 1-3): the C7 rank-1 cloud-provider *routing toggles*
#: (``CLAUDE_CODE_USE_BEDROCK`` / ``CLAUDE_CODE_USE_VERTEX``) and the underlying
#: Bedrock bearer, plus the two Anthropic API-key surfaces (ranks 2-3). In
#: ``subscription`` mode these are **stripped** from the child environment so a
#: value injected *after* settings construction cannot silently displace the
#: operator's login (threat model Finding 1 - TOCTOU / re-review MEDIUM: a stray
#: ``CLAUDE_CODE_USE_BEDROCK=1`` at rank 1 would otherwise silently route the child
#: to Bedrock and ignore the OAuth login). Kept deliberately small and explicit;
#: the child inherits everything else (Windows platform vars included).
#:
#: ``apiKeyHelper`` (C7 rank 4) is a ``settings.json`` script rather than an
#: environment variable, so it cannot be neutralised by env filtering; it is out of
#: scope here and documented as an accepted residual risk (recommend not
#: configuring ``apiKeyHelper`` alongside ``subscription`` mode - Task 13.0 setup
#: guide).
_STRIPPED_IN_SUBSCRIPTION: Final[tuple[str, ...]] = (
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "AWS_BEARER_TOKEN_BEDROCK",
)


@dataclass(frozen=True, slots=True)
class ResolvedCredential:
    """The credential surface derived from a validated ``auth_mode`` (C7).

    Consumed by :class:`ClaudeCodeProcess`'s spawn path to finalise the child
    environment and argv. Carries **no** secret value - only a mode label, argv
    flags, env-var *names*, and boolean signals (C7/C13).

    :ivar mode: The resolving ``auth_mode`` (``"auto"`` / ``"api_key"`` /
        ``"subscription"``), for event/diagnostic labelling.
    :ivar extra_argv: Flags to append to the ``claude`` argv - ``("--bare",)``
        only when bare mode is both requested and eligible (``api_key`` only),
        else empty. **Never** contains a credential value.
    :ivar env_passthrough: **Diagnostic-only** record of the environment-variable
        *names* intended to reach the child (e.g. ``CLAUDE_CODE_OAUTH_TOKEN`` in
        subscription mode when set). It is deliberately **not** the forwarding
        mechanism: :meth:`ClaudeCodeProcess._build_child_env` forwards the OAuth
        token by *inheritance-minus-strip* (it copies ``os.environ`` and removes
        only the outranking credentials, so ``CLAUDE_CODE_OAUTH_TOKEN`` survives),
        not by reading this field. Kept as an observability/audit signal of the
        resolver's intent; carries **names only**, never a value (C13). Documented
        as diagnostic-only rather than removed because it is fixed by the C7
        contract test matrix (re-review LOW).
    :ivar relies_on_stored_login: ``True`` in subscription mode when no
        ``CLAUDE_CODE_OAUTH_TOKEN`` is set, so the subprocess depends on a stored
        ``claude login`` session - the case the auth-probe must verify before the
        first ``delegate()``.
    """

    mode: str
    extra_argv: tuple[str, ...] = ()
    env_passthrough: tuple[str, ...] = ()
    relies_on_stored_login: bool = False


def resolve_credential(settings: ClaudeCodeSettings) -> ResolvedCredential:
    """Derive the subprocess credential surface from ``settings.auth_mode`` (C7).

    Pure and side-effect-free: it reads *settings* and probes only for the
    *presence* of ``CLAUDE_CODE_OAUTH_TOKEN`` (never its value, with the same
    empty==absent semantics as the settings validators). It performs no config
    validation (subtask 01 already rejected an ambiguous ``subscription`` config
    at construction) and no liveness check (the auth-probe owns that).

    Behaviour by mode:

    * ``"auto"`` - a genuine no-op: empty ``extra_argv`` / ``env_passthrough`` and
      ``relies_on_stored_login=False``. The child inherits the ambient environment
      unexamined, exactly as Task 03.0 shipped it.
    * ``"api_key"`` - ``--bare`` is appended iff ``settings.bare`` is ``True``;
      no OAuth token is ever forwarded.
    * ``"subscription"`` - **never** ``--bare`` (defence-in-depth on the C7 rule,
      already impossible after subtask 01's rejection). ``CLAUDE_CODE_OAUTH_TOKEN``
      is forwarded by name when set (``relies_on_stored_login=False``); otherwise
      the child relies on a stored ``claude login`` session
      (``relies_on_stored_login=True``, empty passthrough - the session lives in
      the credential store, not an env var).

    :param settings: A fully validated :class:`ClaudeCodeSettings`.
    :return: The :class:`ResolvedCredential` the spawn path consumes.
    """
    if settings.auth_mode == "subscription":
        token_present = bool(os.environ.get(_SUBSCRIPTION_TOKEN_VAR, "").strip())
        return ResolvedCredential(
            mode="subscription",
            extra_argv=(),
            env_passthrough=(_SUBSCRIPTION_TOKEN_VAR,) if token_present else (),
            relies_on_stored_login=not token_present,
        )
    if settings.auth_mode == "api_key":
        return ResolvedCredential(
            mode="api_key",
            extra_argv=("--bare",) if settings.bare else (),
        )
    return ResolvedCredential(mode="auto")


def build_argv(settings: ClaudeCodeSettings) -> list[str]:
    """Assemble the argv-safe ``claude`` command line (C6.1, C6.3).

    Constructs ``claude -p --output-format stream-json --verbose --allowedTools
    <csv> --permission-mode <mode> --max-turns <n>`` from *settings* only. The
    **task string is deliberately absent** — it is fed over stdin by
    :class:`ClaudeCodeProcess`, never as a bare CLI argument, so it cannot leak
    via ``ps`` (C6.1). ``-p`` (print / non-interactive) with stdin piped makes
    ``claude`` read the prompt from stdin; ``--verbose`` is required by the CLI
    whenever ``--output-format stream-json`` is used under ``-p``. Every
    ``allowed_tools`` value is passed through :func:`_validate_argv_token` (fail
    closed) before it reaches the argv. ``--dangerously-skip-permissions`` is
    never emitted here and was already rejected at ``ClaudeCodeSettings``
    validation (Task 02.0, C6.3).

    This builder adds **no** credential flags and it is **structurally
    impossible** for it to emit ``--bare`` (defence in depth on the C7 rule):
    credential argv flags are the credential resolver's concern
    (:func:`resolve_credential`), appended by :class:`ClaudeCodeProcess` after this
    argv is built, and ``--bare`` is only ever appended in ``api_key`` mode -
    never in ``subscription`` mode.

    :param settings: Validated :class:`ClaudeCodeSettings` (Task 02.0).
    :raises ClaudeCodeConfigError: If an ``allowed_tools`` value is not a safe
        single argv token.
    :return: The argument vector for :func:`asyncio.create_subprocess_exec`,
        with the task string absent by construction.
    """
    argv: list[str] = [
        settings.binary_path,
        "-p",
        "--output-format",
        _OUTPUT_FORMAT,
        "--verbose",
    ]
    # ``--allowedTools`` is emitted UNCONDITIONALLY (C6.3): a validated
    # ``ClaudeCodeSettings`` guarantees a non-empty ``allowed_tools``
    # (``_validate_allowed_tools`` rejects an empty allowlist), so this never omits
    # the flag. Omitting it would grant the CLI unrestricted tool access - fail
    # open - the inverse of the read-only guard, so the flag is never conditional.
    joined = ",".join(_validate_argv_token(value, field="allowed_tools") for value in settings.allowed_tools)
    argv += ["--allowedTools", joined]
    argv += ["--permission-mode", settings.permission_mode]
    argv += ["--max-turns", str(settings.max_turns)]
    return argv


def _validate_argv_token(value: str, *, field: str) -> str:
    """Validate a single ``--allowedTools`` entry at the argv boundary.

    Accepts only ``\\A[A-Za-z0-9._-]+\\Z`` and rejects a leading ``-`` (which
    would be reparsed as a flag). The ``\\A``/``\\Z`` anchors reject a trailing
    newline that ``$`` would admit. Never silently drops a bad value — raises so
    the spawn aborts before any process starts. Directly mirrors
    ``OpenClaudeProcess._validate_argv_token``.

    :param value: A single ``allowed_tools`` entry.
    :param field: Originating settings field, for the payload-free error message.
    :raises ClaudeCodeConfigError: If *value* is not a safe single token.
    :return: *value* unchanged when it is a safe single token.
    """
    if not isinstance(value, str) or not value:
        raise ClaudeCodeConfigError(field=field, reason="allowlist entry must be a non-empty string")
    if value.startswith("-"):
        raise ClaudeCodeConfigError(
            field=field,
            reason="allowlist entry must not begin with '-' (would be parsed as a flag)",
        )
    if _ARGV_TOKEN_RE.match(value) is None:
        raise ClaudeCodeConfigError(
            field=field,
            reason="allowlist entry may contain only [A-Za-z0-9._-] (no ',', '=', whitespace, or control chars)",
        )
    return value


@dataclass(frozen=True, slots=True)
class ClaudeCodeUsage:
    """Real token usage read from the terminal ``result`` message (C6.2, C9).

    :ivar input_tokens: ``usage.input_tokens`` from the ``result`` message.
    :ivar output_tokens: ``usage.output_tokens`` from the ``result`` message.
    """

    input_tokens: int
    output_tokens: int

    @property
    def total(self) -> int:
        """Sum charged to ``CodeResult.token_estimate`` (C9 — a real count).

        :return: ``input_tokens + output_tokens``.
        """
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ClaudeCodeToolCallRecord:
    """One tool-use block surfaced by the parser for observability (C10).

    Carries only the tool name and an argument count — never the tool's argument
    JSON, which may contain incident payload (C13).

    :ivar tool: The Claude Code tool name (e.g. ``"Grep"``), or ``""`` when
        absent.
    :ivar arg_count: Number of top-level arguments in the tool call; a count,
        not content.
    """

    tool: str
    arg_count: int


@dataclass(frozen=True, slots=True)
class ClaudeCodeToolResultRecord:
    """One tool-result block surfaced by the parser for observability (C10).

    Carries only the tool name, a success flag, and the output size — never the
    tool output text, which may contain incident payload (C13).

    :ivar tool: The tool name resolved from the matching ``tool_use_id``, or
        ``""`` when unresolved.
    :ivar ok: ``True`` when the tool reported success, ``False`` on tool error.
    :ivar result_size: Byte/character length of the tool output; a count, not
        content.
    """

    tool: str
    ok: bool
    result_size: int


@dataclass(frozen=True, slots=True)
class ClaudeCodeStreamResult:
    """Reduction of one ``stream-json`` run to a single typed value.

    Produced by :func:`parse_stream`; consumed by
    :meth:`~aegis_swr.claude_code.tool.ClaudeCodeTool.delegate`. Carries no raw
    incident payload beyond ``content`` (the assistant answer text, which the
    tool handles and never logs, C13).

    :ivar content: The concatenated assistant text-block content, in order.
    :ivar usage: The real token usage from the terminal ``result`` message, or
        ``None`` when no well-formed ``result`` message was seen (a failure
        signal for the tool layer).
    :ivar is_error: ``True`` when the ``result`` message reported an error
        (``is_error`` flag or a non-``success`` ``subtype``); ``False`` on a
        clean result.
    :ivar frame_count: Total well-formed NDJSON frames observed (observability).
    :ivar assistant_count: Number of ``assistant`` frames observed.
    :ivar tool_calls: Tool-use records surfaced for observability emission.
    :ivar tool_results: Tool-result records surfaced for observability emission.
    :ivar num_turns: Agent turn count reported by the ``result`` message, or
        ``None`` when the field is absent.
    """

    content: str
    usage: Optional[ClaudeCodeUsage]
    is_error: bool
    frame_count: int = 0
    assistant_count: int = 0
    tool_calls: tuple[ClaudeCodeToolCallRecord, ...] = ()
    tool_results: tuple[ClaudeCodeToolResultRecord, ...] = ()
    num_turns: Optional[int] = None


async def parse_stream(stdout: asyncio.StreamReader) -> ClaudeCodeStreamResult:
    """Consume the NDJSON stdout stream to a single :class:`ClaudeCodeStreamResult`.

    Reads *stdout* line-by-line to EOF, parsing each non-empty line as JSON and
    dispatching on its ``type``: ``assistant`` frames contribute their text
    blocks to the accumulated content and their tool-use blocks to the tool-call
    records; ``user`` frames contribute tool-result records; the terminal
    ``result`` frame supplies the real :class:`ClaudeCodeUsage`, the ``is_error``
    flag, and ``num_turns`` (C6.2, C9). A line that is not valid JSON, or whose
    shape is unexpected, is **skipped** defensively — the parser never raises on
    malformed output and never logs the offending line's content (C13). If no
    well-formed ``result`` message is seen (e.g. the child died mid-stream),
    ``usage is None`` and the tool layer treats it as an unavailable-backend
    failure.

    :param stdout: The child's stdout stream from
        :meth:`ClaudeCodeProcess.stdout_lines`.
    :return: The reduced :class:`ClaudeCodeStreamResult` (never raises).
    """
    content_chunks: list[str] = []
    tool_calls: list[ClaudeCodeToolCallRecord] = []
    tool_results: list[ClaudeCodeToolResultRecord] = []
    tool_names: dict[str, str] = {}
    usage: Optional[ClaudeCodeUsage] = None
    is_error = False
    num_turns: Optional[int] = None
    frame_count = 0
    assistant_count = 0
    skipped = 0

    while True:
        try:
            raw = await stdout.readline()
        except (ValueError, OSError, asyncio.LimitOverrunError):
            # A per-line read failure (over-long line / transient stream error)
            # is non-fatal: skip it and keep parsing, never crash the reduction.
            skipped += 1
            continue
        if not raw:
            break  # EOF — the child closed stdout.
        line = raw.decode(errors="replace").strip()
        if not line:
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if not isinstance(frame, dict):
            skipped += 1
            continue

        frame_count += 1
        frame_type = frame.get("type")
        if frame_type == _TYPE_ASSISTANT:
            assistant_count += 1
            text = _extract_assistant_text(frame)
            if text:
                content_chunks.append(text)
            for tool_use_id, record in _extract_tool_calls(frame):
                tool_names[tool_use_id] = record.tool
                tool_calls.append(record)
        elif frame_type == _TYPE_USER:
            tool_results.extend(_extract_tool_results(frame, tool_names))
        elif frame_type == _TYPE_RESULT:
            usage = _extract_usage(frame)
            is_error = _result_is_error(frame)
            num_turns = _extract_num_turns(frame)

    if skipped:
        logger.debug("Claude Code NDJSON parser skipped {} malformed frame(s)", skipped)

    return ClaudeCodeStreamResult(
        content="".join(content_chunks),
        usage=usage,
        is_error=is_error,
        frame_count=frame_count,
        assistant_count=assistant_count,
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results),
        num_turns=num_turns,
    )


def _extract_assistant_text(frame: dict[str, object]) -> str:
    """Concatenate the text blocks of one ``assistant`` frame.

    Reads ``frame["message"]["content"]`` — a list of content blocks — and joins
    the ``text`` of each ``{"type": "text", ...}`` block, skipping tool-use and
    other block types. Returns ``""`` for any unexpected shape (never raises).
    The returned text is response payload: it is accumulated, never logged (C13).

    :param frame: One parsed ``assistant`` NDJSON frame.
    :return: The joined text content, or ``""`` when none is present.
    """
    parts: list[str] = []
    for block in _content_blocks(frame):
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _extract_tool_calls(frame: dict[str, object]) -> list[tuple[str, ClaudeCodeToolCallRecord]]:
    """Surface the ``tool_use`` blocks of one ``assistant`` frame (C10).

    Each ``{"type": "tool_use", "id": ..., "name": ..., "input": {...}}`` block
    yields its ``tool_use_id`` and a :class:`ClaudeCodeToolCallRecord` carrying
    the tool name and an argument count — never the argument JSON (C13). Unknown
    shapes are skipped; never raises.

    :param frame: One parsed ``assistant`` NDJSON frame.
    :return: A list of ``(tool_use_id, record)`` pairs, possibly empty.
    """
    calls: list[tuple[str, ClaudeCodeToolCallRecord]] = []
    for block in _content_blocks(frame):
        if block.get("type") != "tool_use":
            continue
        name = block.get("name")
        tool = name if isinstance(name, str) else ""
        raw_id = block.get("id")
        tool_use_id = raw_id if isinstance(raw_id, str) else ""
        arg_input = block.get("input")
        arg_count = len(arg_input) if isinstance(arg_input, (dict, list)) else 0
        calls.append((tool_use_id, ClaudeCodeToolCallRecord(tool=tool, arg_count=arg_count)))
    return calls


def _extract_tool_results(
    frame: dict[str, object],
    tool_names: dict[str, str],
) -> list[ClaudeCodeToolResultRecord]:
    """Surface the ``tool_result`` blocks of one ``user`` frame (C10).

    Each ``{"type": "tool_result", "tool_use_id": ..., "content": ...,
    "is_error": ...}`` block yields a :class:`ClaudeCodeToolResultRecord` whose
    tool name is resolved from *tool_names* via the ``tool_use_id``. Only a
    success flag and the output size travel — never the output text (C13).
    Unknown shapes are skipped; never raises.

    :param frame: One parsed ``user`` NDJSON frame.
    :param tool_names: Mapping of ``tool_use_id`` to tool name built from prior
        ``tool_use`` blocks.
    :return: A list of tool-result records, possibly empty.
    """
    results: list[ClaudeCodeToolResultRecord] = []
    for block in _content_blocks(frame):
        if block.get("type") != "tool_result":
            continue
        raw_id = block.get("tool_use_id")
        tool = tool_names.get(raw_id, "") if isinstance(raw_id, str) else ""
        ok = not bool(block.get("is_error", False))
        result_content = block.get("content")
        result_size = len(result_content) if isinstance(result_content, str) else 0
        results.append(ClaudeCodeToolResultRecord(tool=tool, ok=ok, result_size=result_size))
    return results


def _content_blocks(frame: dict[str, object]) -> list[dict[str, object]]:
    """Return the ``message.content`` block list of a turn frame, defensively.

    Reads ``frame["message"]["content"]`` and returns only its ``dict`` members;
    any unexpected shape yields ``[]`` (never raises). Shared by the text and
    tool extractors so all three tolerate a CLI minor-version drift by degrading
    to "no blocks" rather than crashing.

    :param frame: One parsed ``assistant`` / ``user`` NDJSON frame.
    :return: The list of content-block mappings, or ``[]`` when absent/malformed.
    """
    message = frame.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _extract_usage(frame: dict[str, object]) -> Optional[ClaudeCodeUsage]:
    """Read the real token usage from a terminal ``result`` frame (C6.2, C9).

    Reads ``frame["usage"]["input_tokens"]`` and ``["output_tokens"]``, coercing
    each to ``int``. Returns ``None`` when the ``usage`` block is absent or
    malformed (so the tool layer can distinguish "real tokens available" from "no
    usable result"). Never raises and never logs the frame.

    :param frame: One parsed ``result`` NDJSON frame.
    :return: The :class:`ClaudeCodeUsage`, or ``None`` when unreadable.
    """
    usage = frame.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = _coerce_token(usage.get("input_tokens"))
    output_tokens = _coerce_token(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None
    return ClaudeCodeUsage(input_tokens=input_tokens, output_tokens=output_tokens)


def _coerce_token(value: object) -> Optional[int]:
    """Coerce a JSON ``usage`` token count to a non-negative ``int``.

    Accepts a JSON number (``int``/``float``, never ``bool``) and returns its
    integer value; any other shape (missing key, string, ``bool``, ``None``)
    yields ``None`` so :func:`_extract_usage` can report "no usable count" without
    raising or swallowing an exception.

    :param value: The raw token value read from the ``usage`` block.
    :return: The integer count, or ``None`` when the value is not a usable number.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _result_is_error(frame: dict[str, object]) -> bool:
    """Read the error signal of a terminal ``result`` frame.

    An error is signalled by a truthy ``is_error`` flag or by any ``subtype``
    other than ``"success"``. A missing ``subtype`` is treated as clean so a
    minor CLI change does not spuriously fail a good result.

    :param frame: One parsed ``result`` NDJSON frame.
    :return: ``True`` when the result reports an error, else ``False``.
    """
    if bool(frame.get("is_error", False)):
        return True
    subtype = frame.get("subtype")
    return isinstance(subtype, str) and subtype != _RESULT_SUCCESS_SUBTYPE


def _extract_num_turns(frame: dict[str, object]) -> Optional[int]:
    """Read the ``num_turns`` count from a terminal ``result`` frame.

    :param frame: One parsed ``result`` NDJSON frame.
    :return: The integer turn count, or ``None`` when absent/non-integer.
    """
    num_turns = frame.get("num_turns")
    if isinstance(num_turns, bool) or not isinstance(num_turns, int):
        return None
    return num_turns


class ClaudeCodeProcess:
    """Async context manager owning one one-shot ``claude`` subprocess (C6).

    A fresh process is spawned per
    :meth:`~aegis_swr.claude_code.tool.ClaudeCodeTool.delegate` call and reaped
    when it exits — there is no persistent sidecar, no health-check lifecycle
    (contrast ``OpenClaudeProcess``). This class owns the **only**
    ``asyncio.create_subprocess_exec`` call in the package (C3):
    ``subprocess.Popen`` is never used on this async path (C13). The task text is
    written to the child's stdin and stdin is then closed; the argv (from
    :func:`build_argv`) carries no task text (C6.1).

    Usage::

        async with ClaudeCodeProcess(settings, task) as proc:
            result = await parse_stream(proc.stdout_lines())
            code = await proc.wait_exit()

    On exit the child is always reaped (SIGTERM → grace → SIGKILL) and stderr is
    drained; no zombie or leaked pipe remains, and no unredacted stderr text
    reaches a log sink (C13).

    :ivar _settings: Validated :class:`ClaudeCodeSettings`.
    :ivar _task: The open-ended task string, written to stdin — never argv (C6.1)
        and never logged (C13).
    :ivar _process: The owned subprocess handle, or ``None`` before entry / after
        reap.
    :ivar _stderr_task: Background task draining the child's stderr, or ``None``
        before the spawn.
    """

    def __init__(
        self,
        settings: ClaudeCodeSettings,
        task: str,
        *,
        credential: Optional[ResolvedCredential] = None,
    ):
        """Store configuration and the task; perform no I/O and spawn nothing.

        :param settings: Validated :class:`ClaudeCodeSettings` (Task 02.0).
        :param task: The open-ended code-navigation task, fed to stdin at entry.
        :param credential: A **pre-resolved** :class:`ResolvedCredential` to spawn
            under, or ``None`` to resolve one from *settings* at entry. Injecting it
            lets a caller that already resolved the credential (the auth-probe, C7)
            share that **single** resolution for both its own failure-label branch
            and this process's env/argv, closing the label-vs-behaviour seam of two
            independent resolutions (re-review LOW).
        """
        self._settings = settings
        self._task = task
        self._credential = credential
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None

    async def __aenter__(self) -> ClaudeCodeProcess:
        """Spawn the child, feed the task over stdin, and return ``self``.

        Builds the argv via :func:`build_argv`, spawns via
        :func:`asyncio.create_subprocess_exec` with ``stdin``/``stdout``/
        ``stderr`` piped and ``cwd`` set to the **mandatory disposable**
        ``settings.scratch_cwd`` (C6.3 — the child never inherits an
        attacker-influenced cwd), writes ``self._task`` to stdin, then closes
        stdin so the child sees EOF and begins. Starts a background stderr drain
        immediately so startup diagnostics are captured and no stderr
        backpressure stalls the child. Any failure *after* the process is live
        reaps it before the exception propagates (always-terminate invariant).

        :raises ClaudeCodeConfigError: If argv construction rejects a value.
        :raises ClaudeCodeUnavailableError: If the child cannot be spawned
            (e.g. the ``claude`` binary is missing), or - in ``subscription``
            mode - if an outranking credential reappeared between settings
            construction and spawn (``reason="ambiguous_credential"``, C7 /
            threat model Finding 1).
        :return: ``self``, with stdout ready to iterate.
        """
        credential = self._credential if self._credential is not None else resolve_credential(self._settings)
        self._credential = credential
        argv = build_argv(self._settings) + list(credential.extra_argv)
        child_env = self._build_child_env(credential)
        try:
            self._process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._settings.scratch_cwd,
                env=child_env,
            )
        except OSError as exc:
            raise ClaudeCodeUnavailableError(
                "the claude one-shot subprocess could not be spawned",
                binary=self._settings.binary_path,
                reason="spawn_failed",
            ) from exc

        self._stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            await self._write_task_stdin()
        except BaseException:
            # Always-terminate: once the process is live, any failure while
            # feeding stdin (including cancellation) stops the drain and reaps
            # the child before the exception leaves __aenter__. BaseException so
            # CancelledError is covered; the exception is always re-raised.
            await self._stop_stderr_drain()
            await self._terminate()
            raise
        return self

    def _build_child_env(self, credential: ResolvedCredential) -> Optional[dict[str, str]]:
        """Build the explicit child environment for ``subscription`` mode (C7).

        For ``auto`` and ``api_key`` modes this returns ``None`` so
        :func:`asyncio.create_subprocess_exec` inherits the live ``os.environ``
        unchanged - Task 03.0 behaviour is preserved **bit-for-bit** (an explicit
        ``env=None`` is identical to omitting the argument).

        For ``subscription`` mode it collapses the construction-to-spawn TOCTOU
        window (threat model Finding 1, CWE-367): it first **re-checks** that no
        outranking credential (:data:`_STRIPPED_IN_SUBSCRIPTION`) reappeared in
        ``os.environ`` after settings construction - raising
        :class:`ClaudeCodeUnavailableError` with ``reason="ambiguous_credential"``
        if one did, rather than silently running under a stray API key - then
        builds an **inherited-then-filtered** environment: a copy of ``os.environ``
        with exactly those outranking credentials removed. Inherited-then-filtered
        (not a from-scratch allowlist) preserves the platform variables the
        Windows target needs to locate its credential store (``SYSTEMROOT``,
        ``PATH``, ``USERPROFILE`` …) while removing only the vars that defeat the
        subscription intent; ``CLAUDE_CODE_OAUTH_TOKEN``, when set, is retained as
        the intended winner. No credential value is logged or returned to any
        Aegis surface (C13).

        :param credential: The :class:`ResolvedCredential` for this spawn.
        :raises ClaudeCodeUnavailableError: In ``subscription`` mode when an
            outranking credential is present at spawn time.
        :return: ``None`` to inherit the ambient env (``auto`` / ``api_key``), or
            the explicit filtered environment mapping (``subscription``).
        """
        if credential.mode != "subscription":
            return None

        reappeared = next((name for name in _STRIPPED_IN_SUBSCRIPTION if os.environ.get(name, "").strip()), None)
        if reappeared is not None:
            raise ClaudeCodeUnavailableError(
                "an outranking credential is present in the environment under subscription mode",
                binary=self._settings.binary_path,
                reason="ambiguous_credential",
            )

        stripped = frozenset(_STRIPPED_IN_SUBSCRIPTION)
        return {key: value for key, value in os.environ.items() if key not in stripped}

    @property
    def credential(self) -> ResolvedCredential:
        """Return the single :class:`ResolvedCredential` this process spawned under.

        Exposes the one resolution the process used for its env/argv so a caller
        (the auth-probe, C7) consults **exactly one** resolution rather than
        resolving a second time for a failure label - eliminating a latent
        label-vs-behaviour divergence (re-review LOW). Available only after
        :meth:`__aenter__` has resolved it.

        :raises RuntimeError: If accessed before ``__aenter__`` resolved the
            credential.
        :return: The resolved credential surface for this spawn.
        """
        if self._credential is None:
            raise RuntimeError("ClaudeCodeProcess.credential is not available until __aenter__ has resolved it")
        return self._credential

    async def _write_task_stdin(self):
        """Write ``self._task`` to the child's stdin, then close it (C6.1).

        The task reaches the CLI **only** here, over stdin — never via argv — so
        it is invisible to ``ps``. The task bytes are never logged (C13). Closing
        stdin signals EOF so ``claude -p`` starts processing the piped prompt.
        """
        process = self._process
        if process is None or process.stdin is None:
            return
        process.stdin.write(self._task.encode())
        await process.stdin.drain()
        process.stdin.close()

    def stdout_lines(self) -> asyncio.StreamReader:
        """Return the child's stdout stream for the NDJSON parser.

        :raises RuntimeError: If accessed before ``__aenter__`` has spawned the
            child (no stream exists yet).
        :return: The live ``asyncio.StreamReader`` for stdout.
        """
        process = self._process
        if process is None or process.stdout is None:
            raise RuntimeError("ClaudeCodeProcess.stdout_lines is not available until __aenter__ has spawned the child")
        return process.stdout

    async def wait_exit(self) -> int:
        """Await the child's exit and return its exit code (RAII-safe).

        Called after the stdout stream is drained, so the reduced result and the
        exit code are both available before the ``async with`` unwinds.
        Idempotent with :meth:`_terminate`: awaiting a child already reaped by
        cancellation returns its recorded code. Never logs the child's output
        (C13).

        :raises RuntimeError: If called before the child has spawned.
        :return: The process exit code (``0`` on clean completion).
        """
        process = self._process
        if process is None:
            raise RuntimeError("ClaudeCodeProcess.wait_exit called before the child spawned")
        if process.returncode is not None:
            return process.returncode
        return await process.wait()

    async def _drain_stderr(self):
        """Read the child's stderr to EOF, logging each line at DEBUG only (C13).

        Each line is passed as a bound argument (a value, never the format
        template) so untrusted text cannot inject format directives, and the
        loguru ``SensitiveFilter`` on every sink redacts it. A per-line
        decode/read failure is caught narrowly (``ValueError``/``OSError``/
        ``asyncio.LimitOverrunError``) and the drain continues;
        ``CancelledError`` propagates. Mirrors ``OpenClaudeProcess._forward_stderr``.
        """
        process = self._process
        if process is None or process.stderr is None:
            return
        stream = process.stderr
        while True:
            try:
                line = await stream.readline()
                if not line:
                    return  # EOF — the child closed stderr.
                text = line.decode(errors="replace").rstrip()
                logger.debug("Claude Code one-shot stderr: {}", text)
            except (ValueError, OSError, asyncio.LimitOverrunError) as exc:
                # Narrow, non-fatal: a per-line decode/log failure or a transient
                # stream error must not kill the drain. Keep reading.
                logger.debug("Claude Code stderr drain: transient read error: {}", exc)
                continue

    async def _stop_stderr_drain(self):
        """Cancel the stderr-draining task and await its clean shutdown.

        Idempotent: a no-op when the drain was never started or already finished.
        Otherwise cancels the task and awaits it inside
        :func:`contextlib.suppress` so the resulting :class:`asyncio.CancelledError`
        never leaks and no "Task was destroyed but it is pending" warning appears.
        """
        task = self._stderr_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _terminate(self):
        """Reap the owned child: SIGTERM, grace wait, then SIGKILL (RAII).

        Operates only on the stored asyncio handle (never ``os.kill`` on a raw
        pid), guards each step on ``returncode is None``, and awaits ``wait()``
        so no zombie remains. Idempotent: a no-op when never spawned or already
        dead. Mirrors ``OpenClaudeProcess._terminate_managed``.
        """
        process = self._process
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_S)
        except asyncio.TimeoutError:
            if process.returncode is None:
                try:
                    process.kill()
                except OSError:
                    # A SIGCHLD arriving between the returncode check and kill()
                    # can surface as ProcessLookupError/OSError — the child
                    # already died, so treat it as success and still reap below.
                    logger.debug("Claude Code one-shot child already exited before SIGKILL")
            await process.wait()

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
        :return: ``None`` — the in-flight exception (if any) is never suppressed.
        """
        await self._stop_stderr_drain()
        await self._terminate()
        return None
