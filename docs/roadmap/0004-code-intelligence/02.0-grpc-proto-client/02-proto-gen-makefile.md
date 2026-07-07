# 02 - `make proto-gen` target

**Parent task:** 02.0 gRPC Proto & Client
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 03 (client imports the generated stubs), 04.0 (downstream tasks build/test against committed stubs), 09.0 (downstream: CI drift check formalised there)

## Objective

Add a `Makefile` target `proto-gen` that regenerates the Python gRPC stubs
(`openclaude_pb2.py`, `openclaude_pb2_grpc.py`) from `openclaude.proto` into the
same proto directory. The generated files are **committed to the repo** so that
contributors and CI runners without `grpc_tools` installed can still build,
type-check, and run the test suite. Because the stubs are committed, they can
drift from the schema; CI must guarantee they do not (the drift check itself is
formally added in Task 09.0 - this subtask only produces the generator target
and records the CI expectation).

## Makefile target

```makefile
# ── OpenClaude gRPC stubs ─────────────────────────────────────────────────────
# Regenerate committed gRPC stubs from the authoritative proto schema.
# The generated *_pb2.py / *_pb2_grpc.py files are committed (see C9); run this
# whenever openclaude.proto changes and commit the result.

OPENCLAUDE_PROTO_DIR := aegis/openclaude/grpc/proto
OPENCLAUDE_PROTO     := $(OPENCLAUDE_PROTO_DIR)/openclaude.proto

.PHONY: proto-gen
proto-gen:  ## Regenerate committed OpenClaude gRPC stubs from openclaude.proto
	python -m grpc_tools.protoc \
		--proto_path=$(OPENCLAUDE_PROTO_DIR) \
		--python_out=$(OPENCLAUDE_PROTO_DIR) \
		--grpc_python_out=$(OPENCLAUDE_PROTO_DIR) \
		$(OPENCLAUDE_PROTO)
	@echo "Regenerated stubs in $(OPENCLAUDE_PROTO_DIR); commit the result."
```

## Implementation notes

- **Invocation.** `python -m grpc_tools.protoc` (not a bare `protoc`) so the
  toolchain is the pinned `grpcio-tools` Python package rather than a
  system-installed compiler; `grpcio-tools` is a dev-only dependency, not a
  runtime dependency (contributors without it still get the committed stubs).
- **Output layout.** `--proto_path`, `--python_out`, and `--grpc_python_out` all
  point at `aegis/openclaude/grpc/proto/`, so the generated modules import each
  other by their flat module names (`import openclaude_pb2`) exactly as the
  compiler emits them; do not attempt to rewrite imports to package-relative
  form by hand - that is a known drift source. If the flat import proves
  awkward under the package layout, prefer passing the repo root as
  `--proto_path` and a package-qualified proto path rather than post-editing
  generated files.
- **Determinism / drift check.** The generated output is a pure function of the
  `.proto` plus the `grpcio-tools` version. CI re-runs `make proto-gen`, then
  `git diff --exit-code -- aegis/openclaude/grpc/proto/` and fails on any
  difference. Pin `grpcio-tools` to an exact version in the dev dependency group
  so regeneration is reproducible across machines; a version bump that changes
  codegen output must be committed together with the regenerated stubs. This CI
  wiring is authored in Task 09.0 - this subtask only guarantees the target
  exists and is byte-stable when re-run on an unchanged schema.
- **Generated-module handling.** The two generated modules are committed as-is, with
  no inline `# type: ignore` comments hand-added to generated files. Task 01.0 / 06.0
  owns any supporting configuration; note the requirement here.
- **No `.pyi` requirement.** Do not require stub-only generation; the only typed
  surface is `client.py`, which wraps the stubs behind explicit method signatures.

## Constraints

- The target is `.PHONY` and idempotent: running it twice on an unchanged
  `.proto` leaves the working tree clean (no diff).
- Generated files are committed; `.gitignore` must **not** exclude
  `openclaude_pb2.py` / `openclaude_pb2_grpc.py`.
- `grpcio-tools` is a dev/test dependency only; runtime install of `aegis-swr`
  must not require it.
- No manual edits to generated files - all changes flow through the `.proto`
  and regeneration.

## Success criteria

- [ ] `make proto-gen` exists, is `.PHONY`, and regenerates both
      `openclaude_pb2.py` and `openclaude_pb2_grpc.py` into
      `aegis/openclaude/grpc/proto/`.
- [ ] Running `make proto-gen` on an unchanged `.proto` produces no `git diff`.
- [ ] Generated stubs are committed and not git-ignored.
- [ ] `grpcio-tools` is pinned in the dev dependency group and absent from
      runtime dependencies.
- [ ] Generated modules avoid inline `# type: ignore` comments (C9).
- [ ] The CI drift check (re-generate + `git diff --exit-code`) is recorded as a
      Task 09.0 expectation.
