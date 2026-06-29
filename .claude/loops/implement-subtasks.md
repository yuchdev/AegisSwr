---
name: task-name
description: Implements one pending phase per iteration from docs/roadmap/subtasks/{task-name}/NN-*.md, where NN is number in the task queue; runs quality gates, and updates docs/roadmap/progress/0001-generic_implementation_status.md. Self-terminates when all phases reach ✅ Complete.
invoke: /loop task-name
terminates-when: All rows in 0001-generic_implementation_status.md show ✅ Complete
---

# task-name - per-phase implementation loop

Each iteration of this loop implements **exactly one** pending phase, verifies it, invokes the relevant quality-gate skills, and updates the status table.
The loop re-schedules itself until every phase is complete.

---

## Iteration algorithm

### Step 1 - identify the next phase

Read `docs/roadmap/progress/implementation_status.md`. Scan the status of the high-level strategic tasks.

- If every row shows `✅ Complete`: print "All phases complete - loop done." and **stop** (do NOT call ScheduleWakeup).
- Otherwise, take the first row whose Status cell begins with `⬜` (not started) or `🔶` (partial). Record its Phase number, Name, and current Status.

Partial phases are prioritized over not-started ones because unfinished work carries higher regression risk than new work.

Find the required `task-name` in `docs/roadmap/subtasks/{task-name}/{NN}-{slug}.md`, where `NN` is the subtask number to be implemented one by one.

Start implementation from `0001-{slug}.md` subtask.

### Step 2 - load the implementation brief

TODO: load the implementation brief

### Step 3 - implement via the dev-fleet agents

Delegate each Agentic Execution Brief to the appropriate fleet agent in parallel
where the spec allows it (independent briefs within one step can run concurrently;
briefs with stated ordering dependencies run sequentially):

| Spec role keyword  | Fleet agent                             | Agentic action               |
|--------------------|-----------------------------------------|------------------------------|
| `Architect`        | `app-architect`                         | evaluate design              |
| `Python Expert`    | `python-expert`                         | subtask implementation       |
| `Testing Expert`   | `testing-expert` then `python-expert`   | QA then fix regressions      |
| `Security Auditor` | `security-auditor` then `python-expert` | advisory then implementation |
| `Docs Writer`      | `docs-writer` or `docs-updater`         | write or update docs         |

Brief each coder/qa agent with:
- The exact Inputs and Instructions from the spec brief
- The cross-cutting rules from the **"Cross-Cutting Agent Guidelines"** section
  at the bottom of `agentic_implementation_plan.md`
- The relevant parts of `docs/specs/implementation_spec.md` that the brief
  references (e.g. "§9 endpoint specifications")

**Security-sensitive phases** (Phase 8 auth middleware, Phase 9 sandbox): spawn
the `security-auditor` agent BEFORE coding begins. The auditor reads the spec
section and issues a threat model to `docs/security/phase-N-threat-model.md`.
Coder picks up the threat model as an additional input.

### Step 4 - run the verification gate

After all briefs for the step are done, run the Verification command(s) stated
in each brief (e.g. `pytest tests/unit/test_api.py -v`, `mypy src/ --strict`).
If any verification fails:
- Diagnose the failure, delegate a fix to `python-expert`.
- Re-run verification. Continue until green or until the failure is clearly a
  spec ambiguity requiring human input (in that case, stop the loop and surface
  the blocker to the user).

### Step 5 - spec-compliance gate

After the verification gate is green, run `/verify-subtask {subtask-path}` where
`{subtask-path}` is the path identified in Step 1 (relative to `docs/roadmap/subtasks/`,
without the `.md` extension).

- **PASS** → continue to Step 6.
- **PARTIAL** → log the deviations; continue to Step 6 but include the deviation list in
  the `/pr-review` context so the reviewer is aware.
- **FAIL** → delegate the blocking gaps back to `python-expert` (max 1 retry). After the
  fix, re-run Step 4 (verification), then this step again. If still FAIL after one retry,
  surface the gaps to the user and stop the loop.

### Step 6 - run quality-gate skills

After the spec-compliance gate passes (or PARTIAL is noted), invoke the following skills as applicable:

| Condition                                                    | Skill                                                                                                                    |
|--------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Always                                                       | `/test-gap src/aegis_swr/<phase-module>/` - report coverage delta; if < 85 % delegate missing tests to `testing-expert`. |
| `pyproject.toml` or any `requirements*.txt` changed          | `/dep-audit`                                                                                                             |
| Any file under `api/`, `sandbox/`, or any middleware changed | `/secret-scan src/aegis_swr/<changed-module>/`                                                                           |
| Phase is complete (before updating status)                   | `/pr-review` - must get LGTM or REQUEST_CHANGES resolved before advancing.                                               |

### Step 7 - update the status table

After all subtasks are implemented, edit `docs/roadmap/progress/implementation_status.md`:

- Change the phase row's Status cell to `✅ Complete`.
- Update the Tests cell with the new test file names introduced this phase.
- Append a one-paragraph summary under the relevant `## Phase N` heading (or
  create it if this phase had no summary yet) describing what was delivered,
  key implementation decisions, and test coverage numbers.

### Step 8 - reschedule

Call ScheduleWakeup with:
- `prompt`: the literal text `/loop task-name`
- `delaySeconds`: `270`  ← keeps the cache window warm (< 300 s TTL)
- `reason`: "advancing to next pending phase after completing Phase N: <Name>"

---

## Phase-specific notes

### Phase 8 - REST API Layer

Run `security-auditor` first on the auth middleware spec (§9 auth section).
The `python-expert` reads the threat model before implementing `api/middleware/auth.py`.
After the `APIEngineer` brief, verify `aegis server --help` exits 0 (the stub
from Phase 7 must be wired to the real `uvicorn.run` call).

Integration tests (`test_api.py`) require `httpx` - add it to the `[test]`
extras group in `pyproject.toml` if not already present; trigger `/dep-audit`.

### Phase 9 - Secure Code Sandbox

Run `security-auditor` first on the full `PRODUCTION_DESIGN_SPEC.md §10`.
Key invariant from the spec: **path traversal must be blocked at the temp-dir
boundary** before the Docker command is constructed - the security-auditor must
confirm this in its threat model before the coder starts.

The Sandbox Dockerfiles (`sandbox/Dockerfile.cpp`, `sandbox/Dockerfile.python`)
are implementation artifacts, not product code - the `python-expert` writes them, but they
do not need mypy/ruff passes.

### Phase 10 - Testing & Hardening

`GroundTruthEngineer` needs real fixture dumps from `prototype/tests/`. Delegate
to `python-expert` with the explicit instruction to **not** invoke real AI backends --
expected outputs are pre-computed ground truth, not live inference.

`HardeningEngineer`'s `shell=True` audit (step 5 in its Instructions) is a
code-review task: delegate to `feature-reviewer`, not `python-expert`. The reviewer must
grep for `shell=True` across all `backends/` and `sandbox/` and report any
violations as blocking findings.

After `DocumentationEngineer` updates `docs/README.md`, run `/link-check docs/`
to verify all inbound doc references still resolve.

---

## Termination conditions

| Condition                                           | Action                             |
|-----------------------------------------------------|------------------------------------|
| All phases `✅ Complete`                             | Print summary, do NOT reschedule   |
| Verification fails after 2 fix attempts             | Surface blocker to user, stop loop |
| `security-auditor` issues CRITICAL finding          | Stop loop, require human sign-off  |
| `/pr-review` returns REQUEST_CHANGES after 2 rounds | Stop loop, surface diff            |

---
