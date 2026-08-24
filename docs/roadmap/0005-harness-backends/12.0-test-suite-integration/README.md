# Task 12.0 — Test Suite — Integration

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

Author the **live**, per-backend integration suites for the two new backends
this milestone adds, plus a harness-level selection smoke test. Every suite is
**skipped by default** and gated purely on availability — a missing presence
signal, a missing binary, or an unreachable Docker daemon must produce a clean
**skip**, never a failure or an error. These suites are written **incrementally
alongside** their backend tasks (Claude Code 03.0/04.0, OpenHands 07.0/08.0),
the same convention Milestone 0004's Task 08.0 followed for OpenClaude.

Each suite exercises a real, end-to-end `CodeIntelBackend.delegate()` call
against a genuinely running backend and asserts on the returned `CodeResult`
shape:

- **`tests/integration/claude_code/`** drives the installed `claude` binary in
  one-shot `-p … --output-format stream-json` mode. The **base** module runs in
  `auto`/`api_key` credential mode (skipped without `CLAUDE_CODE_ENABLED` + the
  `claude` binary + an API credential); a **subscription-mode** variant carries a
  distinct **third-level** guard and is additionally skipped without a live
  `claude login` session or `CLAUDE_CODE_OAUTH_TOKEN` (C7). The Claude Code live
  test asserts the load-bearing capability gain of this backend — that
  `CodeResult.token_estimate` reflects the **real** reported `usage` from the
  terminal `result` message, not a `len(content)//4` boundary estimate (C6, C9).
- **`tests/integration/openhands/`** drives a live OpenHands sidecar over REST/WS
  (skipped without `OPENHANDS_SERVER_URL` + a reachable Docker daemon, C8). Its
  load-bearing assertion is **sandbox verification** — proof the task actually
  executed inside the Docker runtime, not on the host.
- **`tests/integration/harness/`** is an end-to-end selection smoke test:
  with exactly one presence signal configured and that backend live, the neutral
  `harness.composition.create_code_intel_backend(...)` (C4) resolves
  `HarnessSettings.active_backend` (C2), composes a `CodeAgent`, and a real
  `delegate()` flows through — exercising the composition root itself rather than
  constructing a tool directly as the per-backend suites do.

These suites are the runtime-quality gate for each new backend: a model or
sandbox that cannot sustain a real multi-step navigation task surfaces here
rather than degrading silently in production.

## Subtasks

| # | Name | Blocks | Status |
|---|------|--------|--------|
| 01 | [`tests/integration/claude_code/` live suite](/docs/roadmap/0005-harness-backends/12.0-test-suite-integration/01-claude-code-suite.md) | none | ⬜ Not started |
| 02 | [`tests/integration/openhands/` live suite](/docs/roadmap/0005-harness-backends/12.0-test-suite-integration/02-openhands-suite.md) | none | ⬜ Not started |
| 03 | [`tests/integration/harness/` selection smoke](/docs/roadmap/0005-harness-backends/12.0-test-suite-integration/03-harness-selection-smoke.md) | none | ⬜ Not started |

## Key constraints

- **Skip, never fail.** Every guard uses `pytest.skip(..., allow_module_level=True)`
  so an absent presence signal, missing binary, or unreachable Docker daemon
  yields exactly **one** clean "skipped" line per module — never a failure, an
  error, or a collection crash. This is a Global acceptance criterion of the
  milestone (integration tests are skipped, not failed, when a backend is absent).
- **Three guard levels for Claude Code.** The base guard checks the
  `CLAUDE_CODE_ENABLED` presence signal **and** the `claude` binary on `PATH`.
  The subscription-mode variant adds a **distinct** third-level guard requiring a
  live `claude login` session or `CLAUDE_CODE_OAUTH_TOKEN`, and additionally
  skips when an ambiguous `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` is present
  (which would make `auth_mode="subscription"` reject construction, C7) — so the
  variant only runs when it can run cleanly.
- **Docker reachability is a skip predicate, not an assumption.** The OpenHands
  guard probes the daemon (`docker info` with a timeout) inside a `try` that maps
  any failure to a skip; an unreachable daemon never crashes collection.
- **Real backend, zero mocks.** Tests that actually run talk to a real `claude`
  process / OpenHands sidecar; no integration test leaves a process or sidecar
  session alive after the module, and no test targets the Aegis SWR source tree.
- **Real token accounting is asserted for Claude Code.** The live test proves
  `token_estimate` equals the summed reported `usage`, distinct from the boundary
  estimate (C9), and that at least one `claude_code.tool_call` event is emitted
  (real navigation, not an answer from priors).
- **CI wiring lives in task 13.0.** These modules only *read* the availability
  signals; the opt-in CI job that sets them (so PRs skip and main is optional,
  mirroring 0004's Task 09.0) is added in task 13.0.
- **Cross-cutting (C13):** `from __future__ import annotations`; `Optional[T]`
  from `typing`, never `T | None`; `asyncio.sleep` never `time.sleep`; RST
  docstrings on public helpers/fixtures; `ruff` and `replace_optional.py --check`
  clean on the test tree; loguru sinks keep `SensitiveFilter`; no raw incident
  payload, argv, response, or credential text is ever logged.

## Files

```
tests/integration/
├── claude_code/
│   ├── __init__.py
│   ├── conftest.py                 ← base + subscription-mode skip guards; disposable stub project
│   ├── test_delegate_live.py       ← live delegate() in auto/api_key mode; real token accounting (C9)
│   └── test_subscription_live.py   ← subscription-mode live delegate() (third-level guard, C7)
├── openhands/
│   ├── __init__.py
│   ├── conftest.py                 ← OPENHANDS_SERVER_URL + Docker-daemon skip guards; live client fixture
│   └── test_delegate_live.py       ← live delegate() against running sidecar; sandbox verification (C8)
└── harness/
    ├── __init__.py
    ├── conftest.py                 ← reuses per-backend guards; single-active-backend selection guard
    └── test_selection_smoke.py     ← end-to-end selection → composition → delegate smoke (C2, C4)
```
