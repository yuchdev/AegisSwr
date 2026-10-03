# 02 — No-key boot test

**Parent task:** 08.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** Tasks 02.0, 03.0, 04.0
**Contracts:** C1

## Objective

Prove the ADR's "No-key boot" criterion: the full `aegis analyze` dry-run path
completes with **no** `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/AWS creds in the
environment — keys live only inside the chosen harness.

## Scope (`tests/unit/test_no_key_boot.py`)

- With every provider key env var explicitly unset (and `monkeypatch.delenv` for
  any that leak from the host/CI), construct `Settings()` and the full composition
  (harness session factory + orchestrator) and run `aegis analyze --dry-run` over a
  fixture incident.
- Assert: the run completes, produces a dry-run `RCAReport`, opens no network
  connection, spawns no provider call, and `Settings` exposes no key attribute
  (C1).
- Assert a direct provider is never constructed (reuses the subtask 01 guard).
- Parametrise over the trusted-source tier only (no Docker in unit), confirming the
  no-key path does not depend on a payload-tier backend being present.

## Acceptance criteria

- [ ] `aegis analyze --dry-run` completes with all provider keys unset (C1).
- [ ] No network connection / provider call is made; `Settings` exposes no key.
- [ ] No direct provider is constructed.
- [ ] The test explicitly deletes inherited key env vars so a leaky CI host cannot
      mask a regression.
