"""Verify that ABCs cannot be instantiated directly and that concrete
subclasses satisfying all abstract methods can be instantiated."""
from __future__ import annotations

import pytest

from aegis_swr.agents.base import BaseAgent
from aegis_swr.backends.base import (
    AIAPIBackend,
    CodeBackend,
    DebugBackend,
    LogBackend,
    ObjectStore,
    RelationalStore,
    VectorStore,
)

# ---------------------------------------------------------------------------
# ABCs raise TypeError when instantiated directly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        AIAPIBackend,
        DebugBackend,
        RelationalStore,
        ObjectStore,
        VectorStore,
        LogBackend,
        CodeBackend,
    ],
)
def test_backend_abc_cannot_be_instantiated(cls: type) -> None:
    with pytest.raises(TypeError):
        cls()  # type: ignore[call-arg]


def test_base_agent_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseAgent(ai_backend=None, settings=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Minimal concrete subclasses can be instantiated
# ---------------------------------------------------------------------------


def test_minimal_ai_backend_subclass() -> None:
    from collections.abc import AsyncGenerator
    from typing import Any

    from pydantic import BaseModel

    class _DummyAI(AIAPIBackend):
        model_name = "dummy"

        async def generate(
            self,
            system_prompt: str,
            messages: list[dict[str, Any]],
            output_schema: type[BaseModel] | None = None,
        ) -> BaseModel | str:
            return "ok"

        async def stream(
            self,
            system_prompt: str,
            messages: list[dict[str, Any]],
        ) -> AsyncGenerator[str, None]:
            async def _gen() -> AsyncGenerator[str, None]:
                yield "token"
            return _gen()

    backend = _DummyAI()
    assert backend.model_name == "dummy"


def test_minimal_base_agent_subclass() -> None:
    from aegis_swr.core.schemas import AgentTurn, InvestigationState

    class _DummyAgent(BaseAgent):
        @property
        def system_prompt(self) -> str:
            return "dummy"

        async def run(self, state: InvestigationState) -> AgentTurn:
            return AgentTurn(
                agent="Dummy",
                turn_number=1,
                message="ok",
                confidence_score=0.5,
            )

    agent = _DummyAgent(ai_backend=None, settings=None)  # type: ignore[arg-type]
    assert agent.system_prompt == "dummy"
