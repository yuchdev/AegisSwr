# ── OpenClaude gRPC stubs ─────────────────────────────────────────────────────
# Regenerate committed gRPC stubs from the authoritative proto schema.
# The generated *_pb2.py / *_pb2_grpc.py files are committed (see C9); run this
# whenever openclaude.proto changes and commit the result.
#
# The proto is compiled with the package source root (src) as --proto_path and a
# package-qualified proto path, so the generated grpc stub emits a
# package-qualified cross-import
#   `from aegis_swr.openclaude.grpc.proto import openclaude_pb2`
# rather than a flat `import openclaude_pb2` (which breaks when the stubs are
# loaded as package submodules). This avoids any hand-editing of generated code.

OPENCLAUDE_PROTO_ROOT := src
OPENCLAUDE_PROTO_PKG  := aegis_swr/openclaude/grpc/proto
OPENCLAUDE_PROTO      := $(OPENCLAUDE_PROTO_ROOT)/$(OPENCLAUDE_PROTO_PKG)/openclaude.proto

.PHONY: proto-gen
proto-gen:  ## Regenerate committed OpenClaude gRPC stubs from openclaude.proto
	@command -v uv >/dev/null || { echo "uv required; see README"; exit 1; }
	uv run python -m grpc_tools.protoc \
		--proto_path=$(OPENCLAUDE_PROTO_ROOT) \
		--python_out=$(OPENCLAUDE_PROTO_ROOT) \
		--grpc_python_out=$(OPENCLAUDE_PROTO_ROOT) \
		$(OPENCLAUDE_PROTO)
	@echo "Regenerated stubs in $(OPENCLAUDE_PROTO_ROOT)/$(OPENCLAUDE_PROTO_PKG); commit the result."
