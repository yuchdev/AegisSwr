from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import Settings
from aegis_swr.core.schemas import AgentTurn, InvestigationState


class BaseAgent(ABC):
    """Abstract base for all Synthetic War Room agents"""

    def __init__(self, ai_backend: AIAPIBackend, settings: Settings):
        self._ai = ai_backend
        self._settings = settings

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The stable system-level persona instruction for this agent"""
        pass

    @abstractmethod
    async def run(self, state: InvestigationState) -> AgentTurn:
        """Execute this agent's analysis pass and return a completed AgentTurn"""
        pass

    @staticmethod
    def _append_turn(
            state: InvestigationState,
            turn: AgentTurn,
    ):
        """Append a completed turn to the state's discussion history"""
        history: list[dict[str, Any]] = state.get("discussion_history", [])
        history.append(turn.model_dump(mode="json"))
        state["discussion_history"] = history

    def _accumulate_tokens(self, state: InvestigationState):
        """Add this backend call's token usage to state["token_tracker"]"""
        usage = getattr(self._ai, "last_usage", None)
        if usage is None:
            return
        tracker: dict[str, int] = dict(state.get("token_tracker") or {})
        tracker["input_tokens"] = tracker.get("input_tokens", 0) + usage.get("input_tokens", 0)
        tracker["output_tokens"] = tracker.get("output_tokens", 0) + usage.get("output_tokens", 0)
        state["token_tracker"] = tracker
