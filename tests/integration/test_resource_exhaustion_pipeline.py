"""Integration smoke test: the Resource Exhaustion specialist in a one-round debate.

Uses a mocked AI backend and drives ``ResourceExhaustionAgent.run`` directly (not
the full orchestrator), per Task 06.0 subtask 05.
"""

from __future__ import annotations

import json
from typing import Any

from aegis_swr.agents.forensic.resource_analyst import ResourceExhaustionAgent
from aegis_swr.config.settings import Settings
from aegis_swr.core.schemas import Hypothesis, InvestigationState, ResourceExhaustionOutput
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


def _state() -> InvestigationState:
    return {
        "incident_id": "test-id",
        "incident_brief": {
            "fault_class": "resource_exhaustion",
            "log_summary": "accept: too many open files (errno 24)",
            "mode": "crash_dump",
        },
        "discussion_history": [],
        "round_number": 1,
        "token_tracker": {"input_tokens": 0, "output_tokens": 0},
    }


def _output() -> ResourceExhaustionOutput:
    return ResourceExhaustionOutput(
        hypotheses=[Hypothesis(root_cause="fd leak in accept loop", confidence=0.8)],
        confidence_score=0.8,
        exhausted_resource="file descriptors (ulimit 1024)",
    )


async def test_resource_exhaustion_incident_includes_debate_turn(settings: Settings):
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)

    turn = await agent.run(_state())

    assert turn.agent == "Resource Exhaustion Agent"
    assert 0.0 <= turn.confidence_score <= 1.0
    assert len(ai.calls) == 1

    context: dict[str, Any] = json.loads(ai.calls[-1]["messages"][0]["content"])
    assert "incident_brief" in context
    assert "log_summary" in context
