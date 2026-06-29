# 6.2 Log Backend – Fluentd Stack

**Parent task:** Task 6.2 – Log Backend ([plan.md](/docs/roadmap/0001-generic-implementation/plan.md#task-62-log-backend))
**Status:** 🔶 Partial — `FileLogAdapter` done, `FluentAdapter` is a stub

## Scope

This sub-plan delivers a production-quality `FluentAdapter` that replaces the
current `NotImplementedError` stub, together with the supporting infrastructure
needed to query logs from a Fluent stack (Fluentd or Fluent Bit) by service tag
and time window — across multiple subsystems simultaneously.

## Subtask overview

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Configuration model extension](01-configuration-model.md) | ⬜ Not started | 02, 06, 07 |
| 02 | [LogBackend ABC – multi-service contract](02-logbackend-multiservice.md) | ⬜ Not started | 06, 07 |
| 03 | [Fluentd record normalization model](03-record-normalization.md) | ⬜ Not started | 06, 07 |
| 04 | [Error taxonomy and fail-open behaviour](04-error-taxonomy.md) | ⬜ Not started | 06, 07 |
| 05 | [Design clarifications ← **STOP**](05-design-clarifications.md) | ⬜ Pending answers | 06, 07, 08, 09, 10 |
| 06 | [Fluent HTTP query client](06-http-query-client.md) | ⬜ Blocked on 05 | 08 |
| 07 | [Fluent msgpack forward client](07-forward-protocol-client.md) | ⬜ Blocked on 05 | 08 |
| 08 | [FluentAdapter full implementation](08-fluent-adapter-impl.md) | ⬜ Blocked on 06/07 | 09, 10 |
| 09 | [Factory update and CLI wiring](09-factory-cli.md) | ⬜ Blocked on 08 | 10 |
| 10 | [Unit, mock and integration tests](10-tests.md) | ⬜ Blocked on 08 | — |

> **Stop point:** subtasks 01–04 can be designed and implemented without further
> input. Subtask 05 collects the design questions whose answers gate everything
> from 06 onward. **Do not start 06–10 until the questions in 05 are answered.**

## Key constraints (inherited from the project)

- Full `mypy --strict` compliance; `Optional[T]` not `T | None`.
- No bare `except:`; every network call has a timeout and a defined failure path.
- `SensitiveFilter` must cover any credential that appears in Fluent connection
  settings (auth tokens, TLS key paths).
- The Data Adapter already wraps `LogBackend` calls with `try/except` and falls
  open to file-only — this must stay true after the real adapter is wired in.
- `asyncio.to_thread` wraps every synchronous library call (msgpack/HTTP) to
  avoid blocking the event loop.
