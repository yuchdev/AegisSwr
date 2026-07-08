"""gRPC transport layer for the OpenClaude sidecar.

This subpackage is the sole location in the codebase permitted to import the
``grpc`` library and the generated ``_pb2`` / ``_pb2_grpc`` stubs (contract C3).
Callers outside it interact only through the typed ``AgentFrame`` projection
exposed by :mod:`aegis_swr.openclaude.grpc.client`.
"""
