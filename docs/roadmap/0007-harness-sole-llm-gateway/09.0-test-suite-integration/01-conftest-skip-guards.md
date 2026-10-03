# 01 — `conftest.py` + skip guards

**Parent task:** 09.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03, 04 (this task)
**Contracts:** C9, C12

## Objective

Provide the module-level skip guards and live fixtures so the integration suite
runs only when a real harness is available and self-skips cleanly otherwise —
mirroring the 0004/0005 integration conftest pattern.

## Scope

- `require_gateway_integration` — skips the module unless `AEGIS_GATEWAY_INTEGRATION`
  is set.
- `require_payload_tier` — additionally skips unless Docker + OpenHands
  (`OPENHANDS_SERVER_URL`) are available (the sandboxed payload-tier backend, C9).
- `require_trusted_tier` — additionally skips unless a trusted-source backend
  presence signal is set (`OPENCLAUDE_GRPC_URL` or `CLAUDE_CODE_ENABLED`).
- Live fixtures: a configured `HarnessSessionFactory` over the real per-tier
  backends (registered on an `AsyncExitStack` so sidecars tear down in a
  `finally`), a disposable fixture incident (not the Aegis source tree), and the
  reused hostile fixture (Task 08.0 subtask 05) for leakage assertions.
- Emit exactly one clean `skipped` line per module when a signal/binary/Docker is
  absent; collection stays clean.

## Acceptance criteria

- [ ] `require_gateway_integration` / `require_payload_tier` / `require_trusted_tier`
      skip guards exist and self-skip cleanly (one line per module).
- [ ] Live fixtures build the real per-tier factory with RAII teardown.
- [ ] The hostile fixture is available for leakage assertions.
- [ ] With all signals unset, the suite reports skipped (never failed/errored);
      collection is clean.
