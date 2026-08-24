# Task 03.0 — Claude Code Subprocess Tool

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Category:** infrastructure
**Status:** ⬜ Not started

## Scope

Create `aegis_swr/claude_code/process.py` and `aegis_swr/claude_code/tool.py` —
the **one-shot subprocess** `CodeIntelBackend` for the installed `claude` CLI
(plan.md "Backend B — Claude Code", Topology D). Each `delegate()` call spawns a
fresh `claude -p … --output-format stream-json` process, feeds the task **over
stdin** (never argv), consumes the NDJSON stream on stdout, and reaps the process
on completion — no persistent sidecar, no health check lifecycle. This is the
structural sibling of Milestone 0004's `OpenClaudeTool` (04.0), adapted from a
persistent gRPC stream to a spawn-and-reap subprocess: it keeps the same
budget-pre-check / dry-run / typed-`CodeResult` discipline but replaces the
long-lived channel with RAII over a short-lived `asyncio` subprocess.

`ClaudeCodeTool` implements the **unchanged** `CodeIntelBackend` ABC
(`code_intel/backend.py`), holds `ClaudeCodeSettings` (Task 02.0), an `EventBus`,
and a per-call `CallBudget`, and returns exactly one `CodeResult` per call. Three
things distinguish it from OpenClaude and are the focus of this task (C6, C9):

1. **Argv-safety.** The task text must **never** appear in argv (it is visible via
   `ps`/process listing on a shared host). It is passed via stdin (or a
   disposable temp file), and the constructed argv is asserted free of any task
   substring in unit tests (C6.1).
2. **Real token accounting.** The terminal `result` NDJSON message carries actual
   `usage.input_tokens` / `usage.output_tokens`; their sum becomes
   `CodeResult.token_estimate` — a real count, not a length estimate — while the
   field name and `int` type stay unchanged so `CodeAgent`/`CallBudget` remain
   backend-agnostic (C6.2, C9).
3. **No sandbox.** Runs with host OS permissions. `settings.allowed_tools`
   (→ `--allowedTools`), `settings.permission_mode`, and a **mandatory disposable
   scratch cwd** are the only guards; `--dangerously-skip-permissions` was already
   rejected at settings-validation time in Task 02.0 (C6.3).

**Authentication scope (C6.6 / C7).** This task fixes the invocation *mechanism*
(spawn, stdin, NDJSON parse, real tokens) under `auth_mode="auto"` only: it adds
**no** validation beyond the `claude` binary's own credential precedence, passing
the inherited environment through unexamined. The `auth_mode` field, its
construction-time validation, the `--bare` rule, `CLAUDE_CODE_OAUTH_TOKEN`
handling, and the startup auth-probe are **Task 04.0**, which extends this same
invocation path with a second, mutually exclusive-by-design auth surface. This
task is deliberately sequenced before 04.0 (plan.md Sequencing) so that auth is
designed against a concrete spawn path rather than in isolation.

**Events/exceptions scope (C10).** The canonical `claude_code.*` `DomainEvent`
taxonomy and the typed error hierarchy are **Task 05.0**. This task
**forward-declares** a minimal `ClaudeCodeUnavailableError` for its non-zero-exit
/ timeout / missing-`result` failure paths, exactly as Milestone 0004's Task 01.0
forward-declared `OpenClaudeConfigError` ahead of its canonical home in that
milestone's Task 05.0 (see `openclaude/exceptions.py`, which records the "Task
01.0 forward-declared … this task moves the definition here" convention). Task
05.0 moves the canonical definition into `claude_code/exceptions.py` and updates
this module to import/re-export it, so downstream imports keep resolving. The
`EventBus` is injected here for structural parity and forward wiring; concrete
`claude_code.*` emission lands in Task 05.0. This keeps the plan's MVP path
(`01.0 → (02.0 → 03.0) → 10.0 → 11.0`) self-contained without Task 05.0.

## Subtasks

| #  | Name                                                                                                                              | Blocks     | Status         |
|----|-----------------------------------------------------------------------------------------------------------------------------------|------------|----------------|
| 01 | [Argv-safe subprocess spawn](/docs/roadmap/0005-harness-backends/03.0-claude-code-tool/01-argv-safe-spawn.md)                     | 02, 03, 04 | ⬜ Not started |
| 02 | [NDJSON stream parsing + token accounting](/docs/roadmap/0005-harness-backends/03.0-claude-code-tool/02-ndjson-parsing.md)        | 03, 04     | ⬜ Not started |
| 03 | [ClaudeCodeTool.delegate() + budget + real tokens](/docs/roadmap/0005-harness-backends/03.0-claude-code-tool/03-tool-delegate.md) | 04         | ⬜ Not started |
| 04 | [Dry-run + timeout + failure-path handling](/docs/roadmap/0005-harness-backends/03.0-claude-code-tool/04-dryrun-failure-paths.md) | 04.0, 05.0 | ⬜ Not started |

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- Implements the **unchanged** `CodeIntelBackend` ABC from `code_intel/backend.py` (Milestone 0004, byte-for-byte untouched); `code_intel/` never imports this package, and this package imports no sibling backend (C3).
- **Argv-safety is load-bearing:** the task string never appears in the argv; it is written to stdin (or a disposable temp file). Unit tests assert no task substring is present in the constructed argv (C6.1).
- **Token accounting is real:** `CodeResult.token_estimate == usage.input_tokens + usage.output_tokens` from the terminal `result` message — never a `len(content) // 4` estimate for this backend (C6.2, C9). The field name and `int` type are unchanged (C9 hard invariant).
- **No sandbox:** host OS permissions only; `--allowedTools`, `permission_mode`, and the mandatory disposable scratch cwd are the sole guards. `--dangerously-skip-permissions` (rejected in Task 02.0) is never producible here (C6.3).
- **RAII over the subprocess:** spawn via `asyncio.create_subprocess_exec` (never `subprocess.Popen` in an async path); every exit path reaps the child (SIGTERM → grace → SIGKILL), drains stderr, and closes stdin/stdout inside an `async with` block (C13).
- **Dry-run** short-circuits before **any** spawn to a `[dry-run]` `CodeResult` with `token_estimate == 0` (C6.5, C13).
- **Timeout & failure paths:** `settings.request_timeout_s` enforced via `asyncio.wait_for`; timeout / non-zero exit / missing `result` message → forward-declared `ClaudeCodeUnavailableError` → typed failure `CodeResult`. No exception escapes `delegate()`.
- **`auth_mode="auto"` only** in this task; no credential validation beyond the binary's own precedence (C6.6 / C7 — Task 04.0).
- **Secrecy (C13):** no raw task text, no accumulated response text, no argv, no credential/env value ever reaches a log sink or exception message; `loguru` with `SensitiveFilter` on every sink; no bare `except:`.
- 100% branch coverage on `tool.py`'s `delegate` (mirrors 0004's `tool.py` gate, Task 11.0); per-package unit coverage ≥ 90%.

## Files

```
src/aegis_swr/claude_code/
├── __init__.py            ← (created in Task 02.0; unchanged here)
├── config.py              ← ClaudeCodeSettings (Task 02.0; consumed, not edited)
├── process.py             ← NEW: build_argv + ClaudeCodeProcess (spawn/RAII, subtask 01); NDJSON parse + usage extraction (subtask 02)
└── tool.py                ← NEW: ClaudeCodeTool (CodeIntelBackend); delegate() with
                             budget pre-check + real tokens (subtask 03); dry-run,
                             timeout, failure paths + ClaudeCodeUnavailableError
                             forward-declaration (subtasks 03-04)

tests/unit/claude_code/     ← Task 11.0 (written incrementally)
├── test_process.py        ← argv-safety (no task substring in argv), NDJSON parse
└── test_tool.py           ← delegate: budget/dry-run/timeout/non-zero-exit/real-tokens
```
