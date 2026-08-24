# 02 - --dry-run path with grpc_url set

**Parent task:** 06.0 App Wiring & agents.yaml
**State:** ⬜ Not started
**Depends on:** 01 (composition root + `code_intel/` scaffolding)
**Blocks:** none (downstream Task 07.0 asserts the dry-run acceptance criteria)

## Objective

Nail down and implement the precise `--dry-run` behaviour when
`OPENCLAUDE_GRPC_URL` is set, resolving the tension between two `plan.md`
statements: the global acceptance criterion "`python -m aegis.app --dry-run`
with `OPENCLAUDE_GRPC_URL` set **does not attempt a gRPC connection**" and the
C6 process-lifecycle contract, under which external mode's `__aenter__`
performs a **health check** — which *is* a gRPC connection attempt. The
resolution: under `--dry-run` the full object graph is constructed and the
backend is registered (so composition is exercised), but
`OpenClaudeProcess.__aenter__()` is **not** called (no health check, no managed
subprocess start) and `ctx.dry_run` short-circuits `OpenClaudeTool.delegate`
to a zero-token `[dry-run]` result before any RPC is issued.

## Design decision (resolves the plan.md tension)

**"The process is still started" is FALSE under `--dry-run`.** Precisely:

| Step                                             | Normal run (grpc_url set) | `--dry-run` (grpc_url set) |
|--------------------------------------------------|---------------------------|----------------------------|
| Construct `OpenClaudeSettings`                   | yes                       | yes                        |
| Construct `OpenClaudeProcess` object             | yes                       | yes                        |
| `OpenClaudeProcess.__aenter__()` (health/start)  | **yes**                   | **no** (skipped)           |
| `OpenClaudeConnected` / `OpenClaudeDisconnected` | emitted (C6)              | **not emitted** (no entry) |
| Construct `OpenClaudeGrpcClient`                 | yes (from `process.grpc_url`) | yes (from `settings.grpc_url`) |
| Construct `OpenClaudeTool` + register in `CodeAgent` | yes                   | yes                        |
| First `client.query(...)` RPC                    | on first delegated task   | **never** (delegate short-circuits) |

Rationale: the acceptance criterion "does not attempt a gRPC connection" is the
tie-breaker and takes precedence over C6's health check. The health check *is* a
connection attempt, so it must be skipped in dry-run. This is also the only
sane behaviour — dry-run's purpose is to exercise wiring with **no external
side effects**; running a health check against a possibly-absent endpoint would
make dry-run fail (raising `OpenClaudeUnavailableError`), defeating the very
criterion that dry-run must satisfy with no OpenClaude binary present.

Because `OpenClaudeProcess.grpc_url` is only readable after `__aenter__`
(Task 03.0: reading it before entry raises `RuntimeError`), the dry-run path
constructs `OpenClaudeGrpcClient` from `settings.grpc_url` directly. gRPC aio
channels are lazy (no socket until the first RPC), and the first RPC never
happens under dry-run, so the object graph stays connection-free.

## File: `aegis/app.py` (composition-root section — dry-run branch)

```python
async def build_code_agent(
    settings: OpenClaudeSettings,
    bus: EventBus,
    stack: AsyncExitStack,
    *,
    dry_run: bool,
) -> CodeAgent:
    """Construct the CodeAgent; dry-run skips process entry but not registration.

    :param dry_run: When ``True``, the OpenClaude object graph is fully
        constructed and the backend registered, but ``OpenClaudeProcess`` is
        **not** entered (no health check / no subprocess start) and no gRPC
        connection is attempted. ``ctx.dry_run`` (threaded into
        :class:`CodeTaskContext`) short-circuits every ``delegate`` call.
    """
    if settings.grpc_url is None:
        return CodeAgent(backend=None)

    process = OpenClaudeProcess(settings, bus)
    if dry_run:
        # Construct + register, but never enter the process (no connection, C6
        # health check skipped) — the delegate() short-circuit does the rest.
        client = OpenClaudeGrpcClient(settings.grpc_url, settings)
    else:
        await stack.enter_async_context(process)      # health-check / start (C6)
        client = OpenClaudeGrpcClient(process.grpc_url, settings)

    backend = OpenClaudeTool(client, settings, bus)
    return CodeAgent(backend=backend)
```

`ctx.dry_run` originates from the CLI `--dry-run` flag, is carried on
`CodeTaskContext` (subtask 01), and is honoured inside `OpenClaudeTool.delegate`
per Task 04.0 subtask 04 (return `[dry-run]`/`0` before `client.query`).

## Implementation notes

- The `dry_run` flag is threaded from the CLI/`app.py` entry into
  `build_code_agent` and onward onto `CodeTaskContext.dry_run`; it is a separate
  axis from the `grpc_url is not None` branch (C4) and must not be folded into
  it.
- Dry-run must also complete with `grpc_url` **unset**: `build_code_agent`
  returns `CodeAgent(backend=None)` and the whole OpenClaude branch is skipped
  (this is the existing global acceptance criterion for the no-config case).
- Do not add a second dry-run short-circuit inside the client or the process;
  the single authoritative short-circuit is `OpenClaudeTool.delegate`
  (Task 04.0). `app.py` only decides whether to *enter* the process.
- No `OpenClaudeConnected`/`OpenClaudeDisconnected` events fire in dry-run,
  because `__aenter__`/`__aexit__` are never invoked — consistent with C6's
  "exactly once per entry/exit" wording (zero entries ⇒ zero events).

## Constraints

- `python -m aegis.app --dry-run` with `OPENCLAUDE_GRPC_URL` set attempts **no**
  gRPC connection: no health check, no managed subprocess start, no `query`
  RPC (global acceptance criteria).
- `python -m aegis.app --dry-run` with no API keys, no `OPENCLAUDE_GRPC_URL`,
  and no OpenClaude binary on `PATH` completes cleanly.
- The dry-run branch keeps the backend **registered** so the composition path
  (settings → client → tool → `CodeAgent`) is exercised end to end.
- `Optional[T]` from `typing`; `from __future__ import annotations`;
  `ruff` / `ruff check src/ tests/` - clean (C9).
- No raw payload / unredacted response text logged; the `[dry-run]` result
  carries no incident text (C9).

## Success criteria

- [ ] `python -m aegis.app --dry-run` with `OPENCLAUDE_GRPC_URL=localhost:50051`
      set completes without raising and **without any gRPC socket connection**
      (assertable with a mock client whose `query`/channel is never invoked).
- [ ] `OpenClaudeProcess.__aenter__` is **not** called under `--dry-run`
      (assertable via a spy/mock on the process).
- [ ] No `OpenClaudeConnected` or `OpenClaudeDisconnected` event is emitted on
      the bus during a dry-run.
- [ ] The `CodeAgent` returned under dry-run has a registered backend
      (`agent.available is True`) when `grpc_url` is set.
- [ ] A delegated task under dry-run returns
      `CodeResult(content startswith "[dry-run]", token_estimate == 0)`.
- [ ] `python -m aegis.app --dry-run` with no env vars set returns a
      backend-less `CodeAgent` (`agent.available is False`) and exits cleanly.
- [ ] `ruff check src/ tests/` - clean.
