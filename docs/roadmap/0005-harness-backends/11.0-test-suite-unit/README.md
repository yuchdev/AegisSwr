# Task 11.0 — Test Suite — Unit

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

Author the unit suites for the three new packages this milestone stands up —
`tests/unit/harness/`, `tests/unit/claude_code/`, and `tests/unit/openhands/` —
written **incrementally alongside** tasks 01.0–10.0 (the same convention
Milestone 0004 used for its task 07.0), not sequenced strictly after them. Each
new backend and the neutral harness layer ships its unit coverage in the same PR
that lands its `src/` module.

The whole suite runs with **`AEGIS_CODE_INTEL_BACKEND` unset, every presence
signal (`OPENCLAUDE_GRPC_URL`, `CLAUDE_CODE_ENABLED`, `OPENHANDS_SERVER_URL`)
unset, and no `claude` binary / Docker daemon / OpenHands server available** — no
live process, socket, subprocess, or container is ever started in a unit test.
This mirrors 0004's `mock_grpc_client` seam pattern
([0004 07.0/01](/docs/roadmap/0004-code-intelligence/07.0-test-suite-unit/01-conftest-fixtures.md)):
a shared `conftest.py` provides the injection seams so every collaborator is
constructor-injected, never monkey-patched at a module's global.

The shared fixture module (subtask 01) provides, generalizing the 0004 seams to
three backends:

- a **mock subprocess factory** (`mock_claude_subprocess`) that builds a fake
  one-shot `claude` process from a scripted NDJSON line list **and records the
  exact `argv` it was constructed with**, so the argv-safety assertions (C6) and
  the auth-mode env assertions (C7) inspect a real recorded call — no real
  process is spawned;
- a **mock OpenHands HTTP/WS client** (`mock_openhands_client`) that turns a list
  of plain Action/Observation event dicts into an `AsyncMock` `OpenHandsClient`
  whose event stream yields them in order (the direct analogue of 0004's
  `mock_grpc_client`), plus optional `connect_raises` / `health_result` scripting;
- a recording **`mock_event_bus`** (a real `EventBus` collecting emitted events
  on `bus.captured`, carried over verbatim from 0004);
- **settings fixtures for every C2 ambiguity scenario** (zero signals, each
  single signal, multiple signals, selector-set-signal-absent) plus an ample
  `CallBudget`, a `dry_run_ctx`, and a `live_ctx`.

Mock NDJSON lines and Action/Observation frames are **plain dicts / strings** so
the suite carries no `grpc`, no OpenHands client library, and no real subprocess
dependency, exactly as 0004's plain-frame-dict discipline kept protobuf out of
the unit suite.

Test files mirror the implementation and the plan's File map:

- **`tests/unit/harness/`** — `test_config.py` (the full C2 selection truth
  table, including the `OPENCLAUDE_GRPC_URL`-only auto-select guarantee from
  0004), `test_composition.py` (the sole C4 branch across all three families;
  `dry_run` orthogonality; the moved-verbatim OpenClaude path), `test_isolation.py`
  (the import-aware isolation check that `harness/composition.py` is the only
  module importing more than one family).
- **`tests/unit/claude_code/`** — `test_config.py` (C5/C6 settings surface,
  `--dangerously-skip-permissions` rejection), `test_process.py` (argv-safety:
  task text never in argv), `test_tool.py` (**100% branch coverage on
  `delegate()`**, mirroring 0004's `tool.py` gate; real token accounting per C9),
  `test_auth_modes.py` (the full C7 matrix), `test_events.py` (the `claude_code.*`
  taxonomy incl. `auth_failed`), `test_isolation.py` (no sibling-backend import).
- **`tests/unit/openhands/`** — `test_config.py` (C5/C8; Docker-sandboxed
  default), `test_client.py` (scripted Action/Observation stream; sole importer of
  the client library), `test_process.py` (sidecar lifecycle mirroring 0004's
  `OpenClaudeProcess`), `test_tool.py` (**100% branch on `delegate()`**),
  `test_events.py` (the `openhands.*` taxonomy), `test_isolation.py`.

## Subtasks

| #  | Name                                                       | Status         | Blocks     |
|----|------------------------------------------------------------|----------------|------------|
| 01 | [Shared fixtures / `conftest.py`](01-conftest-fixtures.md) | ⬜ Not started | 02, 03, 04 |
| 02 | [`tests/unit/harness/` suite](02-harness-suite.md)         | ⬜ Not started | -          |
| 03 | [`tests/unit/claude_code/` suite](03-claude-code-suite.md) | ⬜ Not started | -          |
| 04 | [`tests/unit/openhands/` suite](04-openhands-suite.md)     | ⬜ Not started | -          |

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- All unit tests pass with `AEGIS_CODE_INTEL_BACKEND` unset, all three presence signals unset, and no `claude` binary / Docker / OpenHands server available — **no live process, socket, subprocess, or container ever starts** (global acceptance criterion; C13).
- **100% branch coverage on `delegate()`** for `claude_code/tool.py` **and** `openhands/tool.py` (each scoped `--cov-branch --cov-fail-under=100`, mirroring 0004's `tool.py` gate); ≥ 90% per-backend overall unit coverage (gate in task 13.0).
- `test_config.py` in `tests/unit/harness/` covers the **full C2 truth table**, including that an `OPENCLAUDE_GRPC_URL`-only environment still auto-selects with zero further changes (preserving 0004's closing guarantee).
- `test_process.py` in `tests/unit/claude_code/` asserts the task text substring **never** appears in the constructed argv (C6).
- `test_auth_modes.py` covers the **full C7 matrix** and asserts no OAuth token, credential-file content, or API-key value ever reaches a captured log record or exception message across every auth path (C7, C13).
- `test_isolation.py` per package extends 0004's `openclaude-isolation` grep-style check into an **import-statement-aware pytest test** (docstring mentions do not trip it) verifying no backend package imports a sibling and that `harness/composition.py` is the only module importing more than one family.
- No `monkeypatch` of module-level globals; every subprocess / client / process / bus dependency is constructor-injected via the shared fixtures (subtask 01). The only legitimate `monkeypatch` use is setting/clearing real env vars that Pydantic Settings read.

## Files

```
tests/unit/
├── harness/
│   ├── conftest.py              ← subtask 01 (shared seams; also serves claude_code + openhands via tests/unit/conftest.py)
│   ├── test_config.py          ← subtask 02 (full C2 selection matrix)
│   ├── test_composition.py     ← subtask 02 (sole C4 branch; dry-run orthogonality)
│   └── test_isolation.py       ← subtask 02 (import-aware isolation)
├── claude_code/
│   ├── test_config.py          ← subtask 03 (C5/C6 settings; --dangerously-skip-permissions rejection)
│   ├── test_process.py         ← subtask 03 (argv-safety)
│   ├── test_tool.py            ← subtask 03 (100% branch on delegate; real tokens C9)
│   ├── test_auth_modes.py      ← subtask 03 (C7 matrix; no-secret-in-logs)
│   ├── test_events.py          ← subtask 03 (claude_code.* taxonomy incl. auth_failed)
│   └── test_isolation.py       ← subtask 03
└── openhands/
    ├── test_config.py          ← subtask 04 (C5/C8; Docker-sandboxed default)
    ├── test_client.py          ← subtask 04 (scripted Action/Observation stream)
    ├── test_process.py         ← subtask 04 (sidecar lifecycle)
    ├── test_tool.py            ← subtask 04 (100% branch on delegate)
    ├── test_events.py          ← subtask 04 (openhands.* taxonomy)
    └── test_isolation.py       ← subtask 04
```

The shared seams (subtask 01) live in `tests/unit/conftest.py` (or a shared
helper module imported by each package's `conftest.py`) so all three packages
consume the same mock subprocess factory, mock OpenHands client, mock event bus,
and C2 settings fixtures — the exact reuse pattern 0004 established, extended from
one backend to three.
