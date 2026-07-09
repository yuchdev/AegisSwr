# 01 - `openclaude.proto` schema

**Parent task:** 02.0 gRPC Proto & Client
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02 (`scripts/proto_gen.py` regenerates stubs from this file), 03 (client imports the generated stubs), 04.0 (downstream: Process Lifecycle), 04.0/05.0 event mapping

## Objective

Author `aegis/openclaude/grpc/proto/openclaude.proto` - the single, committed,
authoritative contract for the OpenClaude gRPC stream (milestone contract C2).
It defines the frame-type enum, the agent-message frame carried on the stream,
the `PromptRequest` that Aegis SWR sends, and the `AgentService` with its one
server-streaming `Query` RPC. Every other file in the module talks to
OpenClaude only through the stubs generated from this schema, so the schema is
the contract that unit tests mock against - no live Node.js process is ever
needed to exercise the Python side.

## Target schema

```protobuf
// aegis/openclaude/grpc/proto/openclaude.proto
//
// Authoritative gRPC contract for the OpenClaude headless sidecar (C2).
// Generated stubs (openclaude_pb2.py / openclaude_pb2_grpc.py) are committed
// alongside this file and regenerated via `uv run python scripts/proto_gen.py`.

syntax = "proto3";

package aegis.openclaude.v1;

// Type of a single frame in the Query response stream.
//
// FRAME_TYPE_UNSPECIFIED is the mandatory proto3 zero-value; it must never be
// emitted by a well-behaved server. The client treats a received
// UNSPECIFIED frame as a protocol violation (terminal, mapped to a stream
// error) rather than silently ignoring it.
enum FrameType {
  FRAME_TYPE_UNSPECIFIED = 0;
  TEXT_CHUNK             = 1;  // Incremental response text.
  TOOL_CALL             = 2;  // Tool invocation: `tool` set, args JSON in content.
  TOOL_RESULT           = 3;  // Tool output.
  PERMISSION_REQ        = 4;  // Requires confirmation before proceeding.
  DONE                  = 5;  // Terminal frame; content = full response text.
  ERROR                 = 6;  // Terminal error frame; content = error message.
}

// One frame of the server-streamed agent response.
message AgentMessage {
  FrameType type    = 1;  // Discriminates how `content` should be interpreted.
  string    content = 2;  // Text chunk, tool-call args JSON, tool output, or error text.
  string    tool    = 3;  // Optional: tool name for TOOL_CALL / TOOL_RESULT / PERMISSION_REQ.
}

// A single delegated code-navigation task.
message PromptRequest {
  string prompt = 1;  // The open-ended task string handed to OpenClaude's loop.
  string run_id = 2;  // Aegis SWR run correlation id; echoed on emitted events.
}

// The OpenClaude delegation surface.
service AgentService {
  // Delegate one task; receive a stream of agent-message frames terminated by
  // exactly one DONE or one ERROR frame.
  rpc Query(PromptRequest) returns (stream AgentMessage);
}
```

## Implementation notes

- **proto3 zero-value.** proto3 requires the first enum member to be `0`;
  `FRAME_TYPE_UNSPECIFIED = 0` satisfies that and gives the client an
  unambiguous "server sent no type" signal. The six semantic values from C2
  (`TEXT_CHUNK`, `TOOL_CALL`, `TOOL_RESULT`, `PERMISSION_REQ`, `DONE`, `ERROR`)
  take field numbers `1`-`6`. Do not renumber existing values once committed -
  wire compatibility depends on stable numbers.
- **`tool` is optional by omission.** proto3 scalar fields have no explicit
  presence for strings; an empty `tool` string means "not applicable"
  (`TEXT_CHUNK`, `DONE`, `ERROR`). The client must not treat empty string as a
  tool named `""`.
- **`content` semantics are type-dependent** and documented inline: text for
  `TEXT_CHUNK`; args JSON for `TOOL_CALL`; output for `TOOL_RESULT`; the command
  string (or JSON) awaiting approval for `PERMISSION_REQ`; the full concatenated
  response for `DONE`; the error message for `ERROR`.
- **Terminal-frame invariant.** Exactly one of `DONE` / `ERROR` terminates a
  stream. The client (subtask 03) enforces this; the schema only documents it.
- **Package/namespace.** `package aegis.openclaude.v1;` versions the wire
  contract so a future incompatible frame layout can ship as `.v2` without
  breaking committed stubs.
- **No health-specific message.** `health_check()` (subtask 04) reuses `Query`
  with a probe prompt and inspects for a terminal `DONE`; no separate
  `HealthCheck` RPC is added, keeping the surface to a single RPC per C2.

## Constraints

- proto3 syntax only; no proto2 required/optional keywords.
- The file lives at `aegis/openclaude/grpc/proto/openclaude.proto` and is the
  single source the generated stubs derive from (C9: generated files committed).
- Field numbers and enum values are append-only once merged; never reused or
  renumbered.
- No imports of other `.proto` files - the contract is self-contained so
  `scripts/proto_gen.py` needs no include path beyond the proto directory.
- This `.proto` is the only place the frame taxonomy is defined; C8 event
  classes and the client parser both derive their meaning from here.

## Success criteria

- [ ] `openclaude.proto` exists at `aegis/openclaude/grpc/proto/` in proto3 syntax.
- [ ] `FrameType` enum defines `FRAME_TYPE_UNSPECIFIED=0` plus the six C2 values
      `TEXT_CHUNK`, `TOOL_CALL`, `TOOL_RESULT`, `PERMISSION_REQ`, `DONE`, `ERROR`.
- [ ] `AgentMessage` carries `type` (FrameType), `content` (string), and
      optional `tool` (string).
- [ ] `PromptRequest` carries `prompt` (string) and `run_id` (string).
- [ ] `AgentService` exposes exactly one RPC: server-streaming
      `Query(PromptRequest) returns (stream AgentMessage)`.
- [ ] `uv run python scripts/proto_gen.py` (subtask 02) compiles the file without error and
      produces `openclaude_pb2.py` / `openclaude_pb2_grpc.py`.
