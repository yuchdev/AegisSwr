# 03 - `OpenClaudeGrpcClient` implementation

**Parent task:** 02.0 gRPC Proto & Client
**State:** ⬜ Not started
**Depends on:** 01, 02, 05.0 (imports `OpenClaudeUnavailableError` from `aegis.openclaude.exceptions`)
**Blocks:** 04 (`health_check()` + timeout handling extend this class), 03.0 (Process Lifecycle health-checks via this client), 04.0 (OpenClaudeTool delegates through this client)

## Objective

Implement `aegis/openclaude/grpc/client.py` - `OpenClaudeGrpcClient`, the sole
file in the entire codebase permitted to `import grpc` or the generated
`_pb2` / `_pb2_grpc` stubs (contract C3). The client owns the gRPC channel,
lazily created on first use (insecure by default, TLS when settings indicate an
`https` endpoint), sends the `Query` RPC, and exposes `query(prompt, run_id)` as
an async generator that yields parsed frames. It is constructed either from
`OpenClaudeSettings` (production) or from an injected channel via
`from_channel(...)` (tests), so unit tests drive a scripted frame sequence
through a mock channel with no live OpenClaude process. `health_check()` and the
gRPC-status-to-exception translation are specified in subtask 04.

## File: `aegis/openclaude/grpc/client.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Optional

import grpc  # noqa: the ONLY module permitted to import grpc (C3)

from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.exceptions import OpenClaudeUnavailableError
from aegis.openclaude.grpc.proto import openclaude_pb2, openclaude_pb2_grpc


@dataclass(frozen=True)
class AgentFrame:
    """A single parsed frame from the ``Query`` response stream (C2).

    A typed, `grpc`-free projection of ``openclaude_pb2.AgentMessage`` so callers
    outside this file never touch a generated protobuf object.

    :ivar frame_type: The frame's :class:`FrameKind` (text, tool call, tool
        result, permission request, done, or error).
    :ivar content: Interpretation depends on ``frame_type`` (C2): text chunk,
        tool-call args JSON, tool output, awaiting-approval command, full
        response on ``DONE``, or error message on ``ERROR``.
    :ivar tool: Tool name for tool/permission frames; ``None`` otherwise.
    """

    frame_type: "FrameKind"
    content: str
    tool: Optional[str]


class OpenClaudeGrpcClient:
    """Typed, mock-friendly async client for the OpenClaude gRPC sidecar.

    The only object in the codebase that speaks gRPC. It hides the generated
    stubs behind typed methods that yield :class:`AgentFrame` values, translates
    gRPC status errors into domain exceptions, and never logs raw prompt or
    response text (C9).

    :ivar _settings: Connection and timeout configuration (C1).
    :ivar _channel: The gRPC channel; ``None`` until first use (lazy open).
    :ivar _stub: The generated ``AgentService`` stub; ``None`` until first use.
    """

    def __init__(self, settings: OpenClaudeSettings):
        """Construct a client from settings without opening a channel.

        :param settings: OpenClaude configuration; ``settings.grpc_url`` must be
            non-``None`` (a ``None`` URL means the backend is not registered and
            no client should be built - guarded upstream at ``app.py``).
        """
        ...

    @classmethod
    def from_channel(
        cls,
        channel: grpc.aio.Channel,
        settings: OpenClaudeSettings,
    ) -> "OpenClaudeGrpcClient":
        """Build a client around a pre-existing channel (test seam).

        Injects a mock or in-process channel so unit tests can script a frame
        sequence without a live OpenClaude process. The channel is treated as
        already-open; lazy creation is bypassed.

        :param channel: An open (possibly mock) async gRPC channel.
        :param settings: OpenClaude configuration (timeouts, allowlists).
        :return: A client bound to ``channel``.
        """
        ...

    def _ensure_channel(self) -> grpc.aio.Channel:
        """Lazily create the channel and stub on first use.

        Chooses a secure channel when ``settings.grpc_url`` denotes a TLS
        endpoint and an insecure channel otherwise. Idempotent: repeated calls
        return the same channel.

        :return: The live async gRPC channel.
        """
        ...

    async def query(
        self,
        prompt: str,
        run_id: str,
    ) -> AsyncIterator[AgentFrame]:
        """Delegate one task and yield parsed response frames (C2).

        Opens the channel on first call, issues the server-streaming ``Query``
        RPC under ``settings.request_timeout_s``, and yields one
        :class:`AgentFrame` per streamed ``AgentMessage`` until a terminal
        ``DONE`` or ``ERROR`` frame. gRPC status translation is defined in
        subtask 04.

        :param prompt: The open-ended task string handed to OpenClaude's loop.
        :param run_id: Run correlation id echoed on emitted EventBus events.
        :return: An async iterator of parsed frames.
        :raises OpenClaudeUnavailableError: on ``UNAVAILABLE`` /
            ``DEADLINE_EXCEEDED`` (see subtask 04).
        """
        ...

    async def health_check(self) -> bool:
        """Probe reachability; return ``False`` (never raise) on failure.

        Full behaviour - probe prompt, terminal-``DONE`` expectation within
        ``connect_timeout_s``, and swallowing of transport errors - is specified
        in subtask 04.

        :return: ``True`` if a terminal ``DONE`` was received within the connect
            timeout, ``False`` otherwise.
        """
        ...

    async def close(self):
        """Shut the channel down, releasing all gRPC resources.

        Idempotent; safe to call when the channel was never opened. Emits no
        raw payload text to any log sink.
        """
        ...
```

## Implementation notes

- **`FrameKind` enum.** Introduce a small `enum.Enum` (`FrameKind`) mirroring the
  proto `FrameType` values (`TEXT_CHUNK`, `TOOL_CALL`, `TOOL_RESULT`,
  `PERMISSION_REQ`, `DONE`, `ERROR`). `_to_frame()` maps the generated
  `openclaude_pb2.FrameType` int onto it. A received `FRAME_TYPE_UNSPECIFIED`
  (proto zero-value) is a protocol violation: treat it as a terminal stream
  error, not a silently dropped frame. Keeping a domain enum means no caller
  imports the generated stub to compare frame types (preserves C3).
- **Lazy channel.** `__init__` stores settings only; the channel and stub are
  created in `_ensure_channel()` on the first `query()` / `health_check()` call.
  `from_channel()` sets the channel/stub directly and marks them ready so
  `_ensure_channel()` is a no-op.
- **Secure vs insecure.** The `grpc_url` field carries a bare `host[:port]` with
  no scheme (enforced in Task 01.0). TLS selection is therefore driven by a
  settings signal, not by parsing a scheme off `grpc_url`: use a secure channel
  (`grpc.aio.secure_channel` with default channel credentials) when a TLS
  indicator is set, otherwise `grpc.aio.insecure_channel`. Insecure is the
  default for a locally co-located sidecar.

  > Note: the milestone contract C1 defines no TLS/`use_tls` settings field;
  > this subtask assumes TLS selection comes from settings. See the
  > inconsistency flag in the task report - the exact settings signal must be
  > reconciled with Task 01.0 before implementation.
- **Frame parsing is a pure projection.** `_to_frame(msg)` copies
  `type`/`content`/`tool` into an immutable `AgentFrame`; empty `tool` string
  becomes `None` (proto3 strings have no presence). No mutation of generated
  objects; `AgentFrame` is `frozen=True`.
- **Terminal-frame invariant.** `query()` stops iterating after the first
  `DONE` or `ERROR`; a stream that ends without a terminal frame is treated as a
  transport failure and surfaced via the subtask-04 translation.
- **RAII.** The client is expected to be used inside the process lifecycle
  context (Task 03.0) or wrapped by the caller; `close()` is always called on
  teardown. Consider exposing async-context-manager support if the caller owns
  the client directly - decide with `python-expert`, but do not leak channels.
- **Logging.** Log only connection lifecycle and gRPC status codes at `DEBUG`;
  never log `prompt`, `content`, `run_id`-correlated payloads, or response text
  (C9, security). `SensitiveFilter` is on the sink but is not a substitute for
  not logging payloads at all.

## First-use setup: launching OpenClaude in gRPC mode

`OpenClaudeGrpcClient` is inert without a live sidecar to dial. Before writing
or debugging this file against a real process (as opposed to the
`from_channel` mock seam used by unit tests), start OpenClaude yourself in
external mode:

```bash
openclaude --version || npm install -g @gitlawb/openclaude@latest

openclaude --grpc --port 50051 \
  --allowed-tools Read,Grep,Glob,Bash \
  --bash-allowlist gtags,global,semgrep,rg,find,cat
```

The flags mirror the C1 defaults (`OPENCLAUDE_ALLOWED_TOOLS` /
`OPENCLAUDE_BASH_ALLOWLIST`) - in external mode the operator supplies them by
hand; Aegis SWR only injects them itself in managed mode (Task 03.0 subtask
02). Leave this process running in a separate terminal for the rest of this
subtask's manual testing, and point the client at it:

```bash
export OPENCLAUDE_GRPC_URL=localhost:50051
```

With the sidecar up, sanity-check the raw gRPC channel before trusting this
client's own code - this isolates "is OpenClaude reachable" from "is my
client code correct":

```bash
python3 - <<'PY'
import grpc

channel = grpc.insecure_channel("localhost:50051")
grpc.channel_ready_future(channel).result(timeout=5)
print("openclaude gRPC endpoint is reachable")
channel.close()
PY
```

This needs only `grpcio` (already a dependency of this subtask), never the
generated `_pb2` stubs, so it works even before `query()` is implemented.
Once `query()` is implemented, drive it end-to-end with a real prompt:

```bash
python3 - <<'PY'
import asyncio

from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient


async def main():
    client = OpenClaudeGrpcClient(OpenClaudeSettings(grpc_url="localhost:50051"))
    async for frame in client.query("ping", run_id="smoke-test"):
        print(frame.frame_type, len(frame.content))
    await client.close()


asyncio.run(main())
PY
```

A connection refusal here almost always means the `--port` OpenClaude was
launched with doesn't match `grpc_url`; a permission/allowlist error means the
launch flags above don't match `settings.allowed_tools` /
`settings.bash_allowlist`.

## Constraints

- **This file is the only place `import grpc` or `openclaude_pb2*` may appear**
  (C3); enforced by the isolation `grep` CI check.
- `from __future__ import annotations` at the top; `Optional[T]` from `typing`,
  never `T | None`, including in subscripts (C9).
- `ruff` clean; zero new `# type: ignore` (the generated
  stubs are excluded via the per-module override from subtask 02, so the client
  needs none).
- All public methods carry RST docstrings (`:param:`, `:return:`, `:raises:`).
- Async throughout (`grpc.aio`); no blocking `grpc` channel APIs on the event
  loop, no `time.sleep` (`asyncio.sleep` for any backoff - see subtask 04).
- No raw prompt/response text in any log sink or exception message.

## Success criteria

- [ ] `aegis/openclaude/grpc/client.py` defines `OpenClaudeGrpcClient` and the
      typed `AgentFrame` projection; no caller imports the generated stubs.
- [ ] `import grpc` and `openclaude_pb2*` appear in this file only (C3 check
      passes).
- [ ] The channel is not created in `__init__`; it is created on the first
      `query()` / `health_check()` call.
- [ ] `from_channel(channel, settings)` yields a working client whose `query()`
      streams frames from a mock channel with no live process.
- [ ] `query(prompt, run_id)` is an async generator yielding one `AgentFrame`
      per `AgentMessage`, stopping after the first `DONE` / `ERROR`.
- [ ] `close()` is idempotent and safe when the channel was never opened.
- [ ] `ruff check src/ tests/` - clean.
