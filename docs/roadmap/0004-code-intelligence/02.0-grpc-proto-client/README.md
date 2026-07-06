# Task 02.0 — gRPC Proto & Client

**Parent milestone:** [Milestone 0004 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

Author the gRPC contract and the only Python file permitted to import `grpc`.
Create `aegis/openclaude/grpc/proto/openclaude.proto` defining the message-frame
enum, the agent-message frame, a `PromptRequest` (prompt + run id), and an
`AgentService` with a single server-streaming `Query` RPC (contract C2). Add a
`Makefile` `proto-gen` target that regenerates `openclaude_pb2.py` and
`openclaude_pb2_grpc.py` into the proto directory; the generated files are
committed so contributors without `grpc_tools` can still build and test.

Create `aegis/openclaude/grpc/client.py` — `OpenClaudeGrpcClient`. The channel
is created lazily (insecure, or secure when the URL is `https`) and not opened
until the first `query()` call. `query(prompt, run_id)` calls the `Query` RPC
and yields parsed frames; `health_check()` sends a ping request and expects a
terminal `DONE` frame within `connect_timeout_s`, returning `False` (not
raising) when the channel is unreachable. gRPC `UNAVAILABLE` /
`DEADLINE_EXCEEDED` are surfaced as `OpenClaudeUnavailableError`. The channel
and stub are injectable via a `from_channel(channel, settings)` classmethod so
tests need no live process. `close()` shuts the channel down.

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [`openclaude.proto` schema](01-proto-schema.md) | ⬜ Not started | 02, 03, 04.0 |
| 02 | [`make proto-gen` target](02-proto-gen-makefile.md) | ⬜ Not started | 03, 04.0, 09.0 |
| 03 | [`OpenClaudeGrpcClient` implementation](03-grpc-client.md) | ⬜ Not started | 04, 03.0, 04.0 |
| 04 | [`health_check()` + timeout handling](04-health-check-timeouts.md) | ⬜ Not started | 03.0, 04.0 |

## Key constraints

- `import grpc` (and the generated `_pb2` stubs) appear in **this file only**;
  enforced by the C3 boundary check.
- Generated proto files are committed and excluded from `mypy --strict` via a
  `per-module` ignore; `make proto-gen` must reproduce identical output.
- Channel/stub injectable via `from_channel`; unit tests drive a scripted frame
  sequence through a mock channel with no real OpenClaude process.
- `health_check()` returns `False` on unreachable within `connect_timeout_s`;
  it does not raise. `query()` raises `OpenClaudeUnavailableError` on
  `UNAVAILABLE` / `DEADLINE_EXCEEDED`.
- Client code is `mypy --strict` and `ruff` clean; `Optional[T]`, no `T | None`.
