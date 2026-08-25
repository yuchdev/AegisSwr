# 02 - NDJSON stream parsing and token accounting

**Parent task:** 03.0 Claude Code Subprocess Tool
**State:** ✅ Complete
**Depends on:** 01
**Blocks:** 03, 04

## Objective

Add the `stream-json` (NDJSON) parser to `aegis_swr/claude_code/process.py`:
consume the child's stdout line-by-line, parse each line as a JSON frame, dispatch
on its `type`, accumulate assistant text content, and extract the terminal
`result` message's `usage` block. The parser reduces the whole stream to one
frozen `ClaudeCodeStreamResult` carrying the accumulated text, the **real** token
counts (`usage.input_tokens` + `usage.output_tokens`, C6.2/C9), an `is_error`
flag, and observability counts. It never raises on a malformed line (skips it,
defensively) and never logs raw line/text content (C13). This is the data-shaping
layer the subtask-03 tool converts into a `CodeResult`.

## File: `aegis_swr/claude_code/process.py`

```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Final, Optional

#: NDJSON ``type`` discriminators emitted by ``claude --output-format
#: stream-json``. ``system`` (init/meta), ``assistant``/``user`` (turn messages),
#: and the single terminal ``result`` message that carries real ``usage``.
_TYPE_ASSISTANT: Final[str] = "assistant"
_TYPE_RESULT: Final[str] = "result"


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
        """Sum charged to ``CodeResult.token_estimate`` (C9 - a real count).

        :return: ``input_tokens + output_tokens``.
        """
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class ClaudeCodeStreamResult:
    """Reduction of one ``stream-json`` run to a single typed value.

    Produced by :func:`parse_stream`; consumed by :meth:`ClaudeCodeTool.delegate`
    (subtask 03). Carries no raw incident payload beyond ``content`` (the
    assistant answer text, which the tool truncates/handles and never logs, C13).

    :ivar content: The concatenated assistant text-block content, in order.
    :ivar usage: The real token usage from the terminal ``result`` message, or
        ``None`` when no well-formed ``result`` message was seen (a failure
        signal for subtask 03).
    :ivar is_error: ``True`` when the ``result`` message reported an error
        (``is_error`` / an error ``subtype``); ``False`` on a clean result.
    :ivar frame_count: Total NDJSON frames observed (observability metadata).
    :ivar assistant_count: Number of ``assistant`` frames observed.
    """

    content: str
    usage: Optional[ClaudeCodeUsage]
    is_error: bool
    frame_count: int = 0
    assistant_count: int = 0


async def parse_stream(stdout: asyncio.StreamReader) -> ClaudeCodeStreamResult:
    """Consume the NDJSON stdout stream to a single :class:`ClaudeCodeStreamResult`.

    Reads *stdout* line-by-line to EOF, parsing each non-empty line as JSON and
    dispatching on its ``type``: ``assistant`` frames contribute their text
    blocks to the accumulated content; the terminal ``result`` frame supplies the
    real :class:`ClaudeCodeUsage` and the ``is_error`` flag (C6.2, C9). A line
    that is not valid JSON, or whose shape is unexpected, is **skipped**
    defensively - the parser never raises on malformed output and never logs the
    offending line's content (C13). If no well-formed ``result`` message is seen
    (e.g. the child died mid-stream), ``usage is None`` and subtask 03 treats it
    as an unavailable-backend failure.

    :param stdout: The child's stdout stream from
        :meth:`ClaudeCodeProcess.stdout_lines`.
    :return: The reduced :class:`ClaudeCodeStreamResult` (never raises).
    """
    ...


def _extract_assistant_text(frame: dict[str, object]) -> str:
    """Concatenate the text blocks of one ``assistant`` frame.

    Reads ``frame["message"]["content"]`` - a list of content blocks - and joins
    the ``text`` of each ``{"type": "text", ...}`` block, skipping tool-use and
    other block types. Returns ``""`` for any unexpected shape (never raises).
    The returned text is response payload: it is accumulated, never logged (C13).

    :param frame: One parsed ``assistant`` NDJSON frame.
    :return: The joined text content, or ``""`` when none is present.
    """
    ...


def _extract_usage(frame: dict[str, object]) -> Optional[ClaudeCodeUsage]:
    """Read the real token usage from a terminal ``result`` frame (C6.2, C9).

    Reads ``frame["usage"]["input_tokens"]`` and ``["output_tokens"]``, coercing
    each to ``int``. Returns ``None`` when the ``usage`` block is absent or
    malformed (so subtask 03 can distinguish "real tokens available" from "no
    usable result"). Never raises and never logs the frame.

    :param frame: One parsed ``result`` NDJSON frame.
    :return: The :class:`ClaudeCodeUsage`, or ``None`` when unreadable.
    """
    ...
```

## Implementation notes

- **Frame shape (`claude --output-format stream-json`).** Each stdout line is one
  JSON object with a `type` discriminator. The relevant types: `system` (init /
  metadata - ignored here), `assistant` / `user` (turn messages whose
  `message.content` is a list of content blocks), and exactly one terminal
  `result` message that carries `usage.input_tokens` / `usage.output_tokens`, an
  `is_error` boolean, a `subtype`, and the final `result` text. Confirm the exact
  keys against the installed CLI at implementation and note any drift; keep the
  extractors tolerant (skip unknown shapes) so a CLI minor-version change degrades
  to "no usage" rather than a crash.
- **Real token accounting (C6.2, C9).** `token_estimate` for this backend is
  `usage.input_tokens + usage.output_tokens` - `ClaudeCodeUsage.total`. This is
  the genuine gain over OpenClaude's `max(1, len(content) // 4)` boundary
  estimate; the shared `CodeResult.token_estimate` field name and `int` type are
  unchanged (C9 hard invariant), so `CodeAgent`/`CallBudget` never learn which
  backend produced it.
- **Line reading.** Iterate `stdout.readline()` until EOF (empty `bytes`),
  decode with `errors="replace"`, strip the trailing newline, skip blank lines.
  Guard against an over-long line (`ValueError` / `asyncio.LimitOverrunError`)
  the same narrow way `OpenClaudeProcess._forward_stderr` does - skip and
  continue, never crash the parse.
- **Malformed-line resilience.** A `json.JSONDecodeError` (a `ValueError`) or an
  unexpected shape is skipped, not raised - one bad line must not fail the whole
  investigation. The skipped line's content is never logged (C13); a payload-free
  DEBUG counter ("skipped N malformed frames") is acceptable.
- **`usage is None` is the failure signal.** If the stream ends with no
  well-formed `result` message (child killed by the subtask-04 timeout, non-zero
  exit before completion), `parse_stream` returns `usage=None`; subtask 03 maps
  that to a `ClaudeCodeUnavailableError` failure `CodeResult` with zero tokens.
- **No logging of `content`.** Assistant text is untrusted response payload -
  accumulated into `content` and handed to subtask 03, never logged or placed on
  an event (C13). Only counts (`frame_count`, `assistant_count`) leave the parser
  as observability.
- The `import asyncio` and `ClaudeCodeProcess` are already present from subtask 01
  (same file); this subtask adds the dataclasses and the parse functions.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `parse_stream` and both extractors **never raise** on malformed/partial output; a bad line is skipped (C13).
- `token_estimate` is derived from real `usage` only - `parse_stream` never falls back to a length estimate for this backend (C6.2, C9); "no usage" is surfaced as `usage=None`, not as a fabricated count.
- No `content`/line/frame text is logged or emitted; only payload-free counts (C13). No bare `except:`; narrow `ValueError`/`OSError`/`LimitOverrunError`.
- Dataclasses are `frozen=True, slots=True`; no `Any` in any signature.
- `ruff check src/ tests/` - clean; RST docstrings on every public class/function (C13).

## Success criteria

- [ ] A stream of `system` + N `assistant` frames + a terminal `result` frame returns `content` = the ordered concatenation of assistant text blocks.
- [ ] `usage.total == usage.input_tokens + usage.output_tokens`, read from the terminal `result` message (C6.2, C9).
- [ ] `is_error` reflects the `result` message's error flag/subtype.
- [ ] A stream with **no** well-formed `result` message returns `usage is None`.
- [ ] A malformed / non-JSON line is skipped without raising, and its content is not logged; the surrounding well-formed frames still parse.
- [ ] `frame_count` and `assistant_count` reflect the frames observed.
- [ ] Tool-use / non-text content blocks are ignored by `_extract_assistant_text`.
- [ ] No `content`/line text reaches any log sink (C13).
- [ ] `ruff check src/ tests/` - clean; no `Any` in any signature.
