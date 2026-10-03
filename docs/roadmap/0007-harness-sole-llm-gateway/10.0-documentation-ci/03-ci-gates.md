# 03 — CI grep/coverage gate extensions

**Parent task:** 10.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** Tasks 02.0, 03.0, 05.0, 06.0, 07.0
**Contracts:** C1, C9, C11, C13

## Objective

Wire the CI gates ADR 0006's Validation/Rollout and Coverage sections name:
the sole-gateway import-ban grep job and the scoped coverage gates — mirroring the
Milestone 0004/0005 `*-isolation` / `*-coverage` job pattern.

## Scope (`.github/workflows/`)

- **`harness-gateway-isolation`** grep job (import-statement-aware, mirroring the
  0004 `openclaude-isolation` self-testing guard):
  - no `import anthropic`, `import openai`, `import boto3` anywhere in
    `src/aegis_swr/`;
  - no module imports `claude_cli_provider`;
  - `core/`, `views/`, `code_intel/` import no `aegis_swr.mcp` server module;
  - `router/` imports no `litellm` (0003 invariant preserved);
  - a self-test step that drops a probe `import openai`, asserts the guard flags it,
    and removes it — proving the guard turns red on a real violation.
- **`harness-gateway-coverage`** job (clearing the ini `addopts` with `-o
  addopts=""` so the scoped gate is not diluted, as 0004/0005 did):
  - `--cov-fail-under=90` on `aegis_swr.backends.ai.harness_adapter` and
    `aegis_swr.mcp`;
  - `--cov-fail-under=100` branch on the trust-tier selection
    (`aegis_swr.harness.config` per-tier resolution) and `aegis_swr.core.autonomy`.
  - runs with all provider keys + tier selectors unset (the no-key unit posture).
- **`harness-gateway-integration`** job gated to non-PR/schedule events, self-skips
  without `AEGIS_GATEWAY_INTEGRATION` + Docker/OpenHands (mirrors 0004's
  integration job).
- Use the repo toolchain (`uv sync` / `uv run pytest`) and importable module names
  for `--cov` targets.

## Acceptance criteria

- [ ] `harness-gateway-isolation` enforces all four import bans + the self-test
      (C1, C13).
- [ ] `harness-gateway-coverage` enforces ≥90% on the adapter + MCP surface and 100%
      branch on the tier selection + autonomy gate (C9, C11, ADR Coverage).
- [ ] The coverage job runs with keys/selectors unset (no-key posture).
- [ ] `harness-gateway-integration` self-skips without the signal/Docker.
- [ ] The existing global coverage gate is left intact; the new gates are additive
      and scoped.
