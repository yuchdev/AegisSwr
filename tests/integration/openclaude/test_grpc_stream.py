"""Live gRPC stream-contract integration tests (C2, Task 08.0).

Proves the stream contract end to end against the live sidecar: a real
``query()`` drives the server-streaming ``Query`` RPC and yields at least one
``TEXT_CHUNK`` frame followed by a terminal, non-empty ``DONE`` frame, and
``health_check()`` returns ``True``. This validates the client's real frame
parsing (against a genuine server) rather than the scripted mock channel used in
the unit suite.

Skipped as a whole when ``OPENCLAUDE_INTEGRATION`` is unset or the ``openclaude``
binary is absent.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from aegis_swr.openclaude.grpc.client import FrameKind, OpenClaudeGrpcClient
from tests.integration.openclaude.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent


async def test_query_yields_text_chunk_then_done(
    live_grpc_client: OpenClaudeGrpcClient,
    stub_project: Path,
) -> None:
    """[Integration] grpc stream: A real query returns a non-empty terminal ``DONE`` preceded by >=1 ``TEXT_CHUNK``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a real query returns a non-empty terminal ``DONE`` preceded by >=1 ``TEXT_CHUNK``.
    """
    run_id = str(uuid.uuid4())
    app_py = stub_project / "app.py"
    prompt = f"Read the file at {app_py} and report the name and return type of the function named compute_checksum."
    frames = [frame async for frame in live_grpc_client.query(prompt, run_id)]

    text_chunks = [f for f in frames if f.frame_type is FrameKind.TEXT_CHUNK]
    assert text_chunks, "expected at least one TEXT_CHUNK frame"

    terminal = frames[-1]
    assert terminal.frame_type is FrameKind.DONE
    assert terminal.content.strip(), "DONE frame content must be non-empty"

    # Chunk(s) must precede the terminal DONE frame (C2 ordering).
    done_index = frames.index(terminal)
    first_chunk_index = frames.index(text_chunks[0])
    assert first_chunk_index < done_index


async def test_health_check_true_against_live_process(live_grpc_client: OpenClaudeGrpcClient) -> None:
    """[Integration] grpc stream: ``health_check()`` returns ``True`` against the running sidecar.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``health_check()`` returns ``True`` against the running sidecar.
    """
    assert await live_grpc_client.health_check() is True
