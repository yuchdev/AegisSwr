# 04 - CI isolation and coverage gate extensions

**Parent task:** 13.0 Documentation & CI
**State:** ✅ Complete
**Depends on:** 10.0 (`harness/composition.py` exists; `openclaude/composition.py` deleted; `Settings.harness` nesting), 11.0 (per-backend unit suites incl. 100% branch on each `tool.py`), 12.0 (integration suites and per-backend skip guards); wires their enforcement into CI. Extends the Milestone 0004 `openclaude-isolation` job and coverage gate (see [0004 subtask 03](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/03-ci-boundary-check.md) and [0004 subtask 04](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/04-ci-coverage-gate.md)).
**Blocks:** none

## Objective

Generalize the Milestone 0004 `openclaude-isolation` `grep` boundary job to cover
the **two new backend packages** (`claude_code`, `openhands`) and the **neutral
harness layer** (C3), and extend the coverage gate to require **≥ 90% unit
coverage per backend package** and **100% branch coverage on each new tool's
`delegate()`** — mirroring 0004's `tool.py` gate. Both must be **real, enforced
failure conditions** in CI, not advisory prose.

## Part 1 — Isolation `grep` boundary job (extends 0004 subtask 03, C3)

Extend the existing `openclaude-isolation` job (rename to reflect coverage of all
families, e.g. `code-intel-isolation`) with these hard-failure rules, each in the
0004 `grep -rEl` invert-match style, import-statement-aware (so docstring mentions
do not trip it), scanning `src/aegis_swr/*.py` only, never `tests/`:

### Rule 1 — scaffolding imports no backend (generalizes 0004 rule 1)
`aegis_swr/core/`, `aegis_swr/views/`, and `aegis_swr/code_intel/` must import
**none** of `aegis_swr.openclaude`, `aegis_swr.claude_code`, `aegis_swr.openhands`,
`grpc`, or the OpenHands client library. Fail on any hit. (This is the existing
0004 rule widened from `aegis.openclaude`/`grpc` to all three families.)

### Rule 2 — no backend imports a sibling (new; the core C3 multi-backend rule)
No backend package imports another backend family:
- `aegis_swr/openclaude/` must not import `aegis_swr.claude_code` or `aegis_swr.openhands`.
- `aegis_swr/claude_code/` must not import `aegis_swr.openclaude` or `aegis_swr.openhands`.
- `aegis_swr/openhands/` must not import `aegis_swr.openclaude` or `aegis_swr.claude_code`.
Fail on any hit.

### Rule 3 — only `harness/composition.py` imports more than one family (new)
Within `aegis_swr/harness/`, cross-family backend imports are permitted **only** in
`composition.py`. Any import of a backend family in `harness/config.py`,
`harness/exceptions.py`, or `harness/__init__.py` fails. (Assert `composition.py`
is the sole harness file that may import more than one backend family.)

### Rule 4 — per-family client isolation (retains 0004 + adds OpenHands)
- `grpc`/`_pb2` only in `aegis_swr/openclaude/grpc/client.py` (excluding generated
  `.../grpc/proto/` stubs) — the existing 0004 rule, unchanged.
- The **OpenHands HTTP/WS client library** only in `aegis_swr/openhands/client.py`
  (C3/C8). Fail on any import elsewhere.

Present these as named steps in one CI job so each failure message names the rule
that broke. Reuse the 0004 pattern: `hits=$(grep -rEl "<import pattern>" <paths> |
grep -v "<allowed file>" || true); if [ -n "$hits" ]; then echo ERROR…; exit 1; fi`.

### Acceptance test for the checks themselves
Mirror 0004 subtask 03: either a **negative-fixture self-test** (copy a known-bad
snippet — e.g. `import aegis_swr.openhands` — into `aegis_swr/claude_code/` under a
temp path, run the rule, assert non-zero exit, remove it) or a **transient manual
proof** on a throwaway branch (introduce a cross-family import + a `core/` backend
import, confirm the job fails on the relevant rules, revert, record the failing
run URL). Deliverable: evidence a deliberate violation turns the build red.

## Part 2 — Coverage gate (extends 0004 subtask 04)

Extend the coverage gate so each backend package has its own enforced threshold,
mirroring 0004's `--cov-fail-under=90` overall + `100% branch on tool.py`:

- **Per-backend unit coverage ≥ 90%** for each of `aegis_swr.openclaude` (existing,
  unchanged), `aegis_swr.claude_code`, `aegis_swr.openhands`, and
  `aegis_swr.harness`.
- **100% branch coverage on each new tool's `delegate()`**: a separate stricter
  step per tool, `--cov-branch --cov-fail-under=100` scoped to
  `aegis_swr.claude_code.tool` and `aegis_swr.openhands.tool` (mirroring the 0004
  `openclaude/tool.py` gate). Keep each as a separate step so the failure message
  names which gate broke.

CI config sketch (mirrors 0004 subtask 04's `openclaude-unit-coverage` job shape):

```yaml
  code-intel-unit-coverage:
    name: "Code-intel: per-backend unit + coverage gates (>=90%; 100% branch on delegate)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install uv && uv sync --all-extras --dev
      - name: "Harness unit + coverage gate"
        run: uv run pytest tests/unit/harness/ --cov=aegis_swr.harness --cov-fail-under=90
        env: { AEGIS_CODE_INTEL_BACKEND: "", OPENCLAUDE_GRPC_URL: "", CLAUDE_CODE_ENABLED: "", OPENHANDS_SERVER_URL: "" }
      - name: "Claude Code unit + coverage gate"
        run: uv run pytest tests/unit/claude_code/ --cov=aegis_swr.claude_code --cov-fail-under=90
        env: { CLAUDE_CODE_ENABLED: "", ANTHROPIC_API_KEY: "", CLAUDE_CODE_OAUTH_TOKEN: "" }
      - name: "OpenHands unit + coverage gate"
        run: uv run pytest tests/unit/openhands/ --cov=aegis_swr.openhands --cov-fail-under=90
        env: { OPENHANDS_SERVER_URL: "" }
      - name: "100% branch on claude_code.tool.delegate"
        run: uv run pytest tests/unit/claude_code/test_tool.py --cov=aegis_swr.claude_code.tool --cov-branch --cov-report=term-missing --cov-fail-under=100
      - name: "100% branch on openhands.tool.delegate"
        run: uv run pytest tests/unit/openhands/test_tool.py --cov=aegis_swr.openhands.tool --cov-branch --cov-report=term-missing --cov-fail-under=100
```

Each unit step runs with **all presence signals and credentials unset** to prove
the suites are hermetic (Global acceptance criterion — all unit tests pass with
`AEGIS_CODE_INTEL_BACKEND` unset, all signals unset, no `claude`/Docker/OpenHands).

### Integration gating (mirrors 0004 subtask 04, per backend)
Gate `tests/integration/claude_code/` and `tests/integration/openhands/` behind
per-backend signals so they are **skipped, not failed**, when a binary/Docker/URL
is absent (matching 0004): the Claude Code integration job on
`CLAUDE_CODE_ENABLED` + binary; a **subscription-mode variant additionally
skipped** without a live login or `CLAUDE_CODE_OAUTH_TOKEN`; the OpenHands job on
`OPENHANDS_SERVER_URL` + Docker availability. Skipped on PRs by default; eligible
on main/nightly. Register any necessary pytest markers in `pyproject.toml`
(`branch = true` already set by 0004; add per-backend integration markers if the
suites need them).

## Implementation notes
- Package on disk is `aegis_swr` under `src/`; use `--cov=aegis_swr.<pkg>` and glob
  `src/aegis_swr/...` in the grep paths (0004's subtasks flagged the
  `aegis` vs. `aegis_swr` path inconsistency — resolve it to `src/aegis_swr` here).
- Do **not** weaken the existing 0004 `openclaude-isolation` rules or the global
  project coverage gate; these jobs are additive.
- Optionally pair the grep rules with pytest isolation mirrors (Task 11.0 already
  authors per-package isolation tests) so the Stop hook catches drift before CI —
  defer the test authoring to `testing-expert`.
- Note that the deletion of `openclaude/composition.py` (Task 10.0) means the old
  job must not reference it; the generalized job checks `harness/composition.py`
  instead.

## Constraints
- Every rule and gate is an **enforced** CI failure condition, not advisory prose.
- Generated proto stubs under `openclaude/grpc/proto/` stay excluded from the grpc rule; scan source only, never `tests/` (fixtures legitimately import backends).
- Unit suites must pass with all presence signals and credentials unset.
- Integration suites skip (not fail) when a signal/binary/Docker is absent; the subscription-mode variant additionally skips without a live login / OAuth token.
- Do not lower the existing global project coverage gate.

## Success criteria
- [ ] The isolation grep job covers all three families + `harness/` (rules 1–4), named so it surfaces in PR checks.
- [ ] Rule 2 fails the build on a backend package importing a sibling family.
- [ ] Rule 3 fails the build on a cross-family import outside `harness/composition.py`.
- [ ] Rule 4 fails on the OpenHands client library imported outside `openhands/client.py` (and retains the grpc/`client.py` rule).
- [ ] A deliberately introduced violation is demonstrated to fail the build (negative fixture self-test or recorded failing run), then reverted.
- [ ] Per-backend unit coverage gate `--cov-fail-under=90` enforced for `claude_code`, `openhands`, and `harness` (and the existing `openclaude`).
- [ ] 100% branch coverage on `claude_code.tool` and `openhands.tool` `delegate()` enforced as separate failing steps.
- [ ] Unit jobs run with all presence signals/credentials unset (hermetic).
- [ ] Integration suites gated per backend, skipped on PRs; subscription-mode variant additionally skipped without a live login / OAuth token.
- [ ] A deliberate coverage regression turns the pipeline red.
