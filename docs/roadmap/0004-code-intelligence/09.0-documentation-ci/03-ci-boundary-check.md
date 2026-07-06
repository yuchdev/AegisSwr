# 03 - CI grep boundary check extension

**Parent task:** 09.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 02.0 (`grpc/client.py` is the only gRPC importer), 06.0 (`code_intel/` scaffolding + `app.py` wiring exist to be checked); extends the Milestone 0003 isolation check.
**Blocks:** none

## Objective

Extend the existing `grep`-based CI isolation check — the Milestone 0003
provider-isolation lint that asserts `litellm` appears only in
`aegis/router/client.py`
(see
[docs/roadmap/0003-litellm-routing/03.0-litellm-client/04-isolation-boundary.md](/docs/roadmap/0003-litellm-routing/03.0-litellm-client/04-isolation-boundary.md)
and its CI job in
[docs/roadmap/0003-litellm-routing/07.0-documentation/04-ci-configuration.md](/docs/roadmap/0003-litellm-routing/07.0-documentation/04-ci-configuration.md))
— to also enforce the OpenClaude module isolation boundary (C3). The check must
be a **real, enforced failure condition** in CI, not advisory documentation.

## CI config (`.github/workflows/ci.yml` — new named job)

Two independent boundary rules, each a hard failure. Pattern mirrors the 0003
job (`grep -rl` over `aegis/`, invert-match the allowed file(s), fail if any
remain). The grep pattern targets import statements (`import grpc`, `from grpc`,
`import aegis.openclaude`, `from aegis.openclaude`, `_pb2`) — not bare mentions
in docstrings, matching the 0003 constraint.

```yaml
  openclaude-isolation:
    name: "Lint: OpenClaude module isolation (C3)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: "Reject aegis.openclaude imports in core/ui/code_intel"
        run: |
          # aegis.openclaude must never be imported by core/, ui/, or code_intel/
          hits=$(grep -rEl "(^|[^.])(import[[:space:]]+aegis\.openclaude|from[[:space:]]+aegis\.openclaude)" \
                   aegis/core/ aegis/ui/ aegis/code_intel/ 2>/dev/null || true)
          if [ -n "$hits" ]; then
            echo "ERROR: aegis.openclaude imported in an isolated module (C3):"
            echo "$hits"
            exit 1
          fi
      - name: "Reject grpc/_pb2 imports outside grpc/client.py"
        run: |
          # grpc and generated *_pb2 stubs may only be imported by grpc/client.py
          hits=$(grep -rEl "(import[[:space:]]+grpc|from[[:space:]]+grpc|_pb2)" aegis/ \
                   | grep -v "aegis/openclaude/grpc/client.py" \
                   | grep -v "aegis/openclaude/grpc/proto/" || true)
          if [ -n "$hits" ]; then
            echo "ERROR: grpc/_pb2 imported outside aegis/openclaude/grpc/client.py (C3):"
            echo "$hits"
            exit 1
          fi
```

Notes on the second rule: the generated `_pb2.py` / `_pb2_grpc.py` files under
`aegis/openclaude/grpc/proto/` legitimately contain `grpc`/`_pb2` and are excluded
(C9 commits them and excludes them from `mypy --strict`); only `client.py` may
*import* them into hand-written code.

## Acceptance test for the check itself

The check is only trustworthy if a real violation turns the build red. Verify
one of:

- **Preferred — dedicated negative fixture, self-testing script.** Keep a
  known-bad snippet fixture (e.g. `tests/ci/fixtures/bad_grpc_import.py.txt`
  containing `import grpc`) and a small self-test that copies it into
  `aegis/core/` under a temp path, runs the grep rule, asserts a non-zero exit,
  and removes it — so the failure path is exercised in CI without leaving a real
  violation committed. This makes "the guard actually fails" a tested property.
- **Alternative — transient manual proof.** On a throwaway branch, add
  `import grpc` to a file under `aegis/core/` and `import aegis.openclaude` to a
  file under `aegis/code_intel/`, push, confirm the `openclaude-isolation` job
  fails on both rules, then revert. Record the failing run URL in the PR.

Either way the deliverable is evidence that a deliberately introduced violation
fails the build.

## Implementation notes
- Add this as a **named** job/step so it surfaces in PR checks as
  `"Lint: OpenClaude module isolation (C3)"` (visible drift gate, per 0003).
- Optionally pair with a pytest mirror (as 0003 did with
  `test_litellm_is_only_imported_in_client`) so the Stop hook catches drift in
  development before CI — defer the test authoring itself to `testing-expert`.
- The real package on disk is `aegis_swr` under `src/`; if the CI paths need to
  be `src/aegis_swr/...` rather than `aegis/...`, adjust the globs accordingly
  when implementing (see the inconsistency flagged to the parent).

## Constraints
- Must be an enforced failure condition in CI config, not advisory prose.
- `aegis/openclaude/grpc/proto/` (generated stubs) is excluded from the grpc rule;
  `aegis/openclaude/grpc/client.py` is the only allowed grpc importer.
- Scan `*.py` under the source tree only, never `tests/` (fixtures legitimately
  import `grpc`).
- Do not weaken the 0003 `litellm` rule; this job is additive.

## Success criteria
- [ ] Named CI job `"Lint: OpenClaude module isolation (C3)"` added to `.github/workflows/ci.yml`.
- [ ] Rule 1 fails the build on `import aegis.openclaude` in `core/`, `ui/`, or `code_intel/`.
- [ ] Rule 2 fails the build on `import grpc` / `_pb2` anywhere except `grpc/client.py`.
- [ ] Generated proto stubs are excluded from rule 2.
- [ ] A deliberately introduced violation is demonstrated to fail the build
      (negative fixture self-test or recorded failing run), then reverted.
