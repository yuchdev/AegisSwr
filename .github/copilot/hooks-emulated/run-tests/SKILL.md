---
name: run-tests
description: Emulates the Claude run_tests.py Stop hook. Runs the unit suite and blocks session completion if tests are red. In Claude this ran automatically before the session could end. In Copilot, invoke /run-tests manually before finishing a session.
allowed-tools: Bash, Read
invocation: /run-tests
# Ported from Claude (.claude/hooks/run_tests.py) on 2026-07-03
# Original hook type: Stop - EXIT 2 blocking (prevented session from ending on red suite)
# Copilot equivalent: Manual skill — invoke before ending a session; honor its result
---

# Run Tests (Session Gate)

Gate the end of a work session on a green unit test suite.

> **Ported from Claude `run_tests.py` (Stop hook) on 2026-07-03.**
> In Claude Code this ran automatically when the session was about to end, and
> exited with code 2 (blocking the session from closing) if tests were red.
> In Copilot CLI, call `/run-tests` manually before finishing a session.
> Honor its result: do not commit or push if tests are red.

## Steps

1. **Check skip flag**:
   ```powershell
   if ($env:AEGIS_SKIP_TESTS -eq "1") { Write-Host "Tests skipped (AEGIS_SKIP_TESTS=1)" ; return }
   ```

2. **Run the unit suite** (fast, no external services):
   ```bash
   uv run pytest tests/unit/ -q --override-ini=addopts= -p no:cov
   ```
   Fallback if uv is unavailable:
   ```bash
   pytest tests/unit/ -q --override-ini=addopts= -p no:cov
   ```

3. **Evaluate result**:
   - **Pass** → log `PASS` to `.claude/logs/tests.log` and confirm the session can end.
   - **Fail** → log `FAIL`, print the last 25 lines of output, and **stop** — fix
     the failures before committing or pushing. Export `AEGIS_SKIP_TESTS=1` only
     for intentional WIP branches.

## Rules

- Never weaken or `xfail` a test to make the bar green — fix the cause.
- The full suite (`tests/unit/`) must stay green at all times on `master`.
- `/run-tests` is the last quality gate before a session ends; `/pr-review` is
  the merge gate — both must pass.

## Skip policy

`AEGIS_SKIP_TESTS=1` is for known-WIP sessions only. Document *why* tests are
skipped in the PR description if you open a PR with this flag set.
