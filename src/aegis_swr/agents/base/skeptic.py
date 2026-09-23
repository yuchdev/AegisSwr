"""Skeptic Agent - adversarial moderator / consensus challenger"""

from __future__ import annotations

import json
from typing import ClassVar, Optional

from aegis_swr.agents.base.base import AgentCategory, BaseAgent
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    ConfidenceLevel,
    Hypothesis,
    InvestigationState,
    SkepticVerdict,
)

_SYSTEM_PROMPT = """\
You are the adversarial moderator of the Synthetic War Room. You receive the \
current primary hypothesis and the full discussion so far. Your job is to challenge \
it: verify that the stated faulting module actually appears in the stack trace, \
check that the exception code is consistent with the hypothesis, and identify any \
evidence the other agents may have overlooked. If the hypothesis survives scrutiny, \
confirm it with a HIGH or MEDIUM confidence rating. If not, provide specific \
corrections and flag it as LOW confidence.

Always respond with a structured JSON object matching the SkepticVerdict schema.\
"""


def _module_in_frames(module: str, frames: list[dict[str, object]]) -> bool:
    """Return True if *module* appears in the top 5 stack frames"""
    module_lower = module.lower()
    for frame in frames[:5]:
        frame_module = str(frame.get("module") or "").lower()
        if frame_module and module_lower in frame_module:
            return True
    return False


class SkepticAgent(BaseAgent):
    """Adversarial arbiter that challenges the primary hypothesis to a verdict."""

    agent_key: ClassVar[str] = "skeptic"
    display_name: ClassVar[str] = "Skeptic Agent"
    category: ClassVar[AgentCategory] = "base"
    role: ClassVar[AgentRole] = AgentRole.ARBITER
    default_weight: ClassVar[float] = 0.13

    @property
    def system_prompt(self) -> str:
        """Return the adversarial-moderator system prompt for this agent."""
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        """Challenge the primary hypothesis and return the skeptic's turn.

        Runs a programmatic pre-check that the faulting module appears in the top
        frames before falling back to an LLM verification of the exception code and
        overlooked evidence.

        :param state: the current investigation state (brief, history, hypothesis).
        :return: the skeptic's :class:`AgentTurn` carrying its verdict.
        """
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})
        history = state.get("discussion_history", [])
        primary_hyp = state.get("primary_hypothesis")

        # ----------------------------------------------------------------
        # Programmatic pre-check 1: faulting module must appear in frames.
        # ----------------------------------------------------------------
        if primary_hyp:
            faulting_module = str(primary_hyp.get("faulting_module") or "")
            frames: list[dict[str, object]] = list(brief.get("stack_frames") or [])
            if faulting_module and frames and not _module_in_frames(faulting_module, frames):
                verdict = SkepticVerdict(
                    confirmed=False,
                    confidence=ConfidenceLevel.LOW,
                    challenges=[f"Stated faulting module '{faulting_module}' not found in top 5 stack frames."],
                    corrections=[
                        f"Re-examine the stack - '{faulting_module}' may not be "
                        "the actual faulting module. Consider the top frames: "
                        + ", ".join(str(f.get("module") or "unknown") for f in frames[:5])
                    ],
                )
                return self._build_turn(verdict, primary_hyp, round_num)

        # ----------------------------------------------------------------
        # LLM-based verification for checks 2 and 3.
        # ----------------------------------------------------------------
        context: dict[str, object] = {
            "incident_brief": brief,
            "discussion_history": history,
            "primary_hypothesis": primary_hyp,
            "round": round_num,
            "task": (
                "Verify: (1) exception code is consistent with the hypothesis, "
                "(2) the stated exception address falls within the module's range if known, "
                "(3) no significant evidence is being overlooked."
            ),
        }
        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, SkepticVerdict)
        assert isinstance(output, SkepticVerdict)
        self._accumulate_tokens(state)
        return self._build_turn(output, primary_hyp, round_num)

    def _build_turn(
        self,
        verdict: SkepticVerdict,
        primary_hyp: Optional[dict[str, object]],
        round_num: int,
    ) -> AgentTurn:
        """Build the skeptic's turn from a *verdict* and the primary hypothesis."""
        primary_root = str((primary_hyp or {}).get("root_cause") or "")
        message = (
            f"Confirmed ({verdict.confidence.value}): {primary_root}"
            if verdict.confirmed
            else f"Challenged ({verdict.confidence.value}): " + "; ".join(verdict.challenges)
        )
        confidence_score = {
            ConfidenceLevel.HIGH: 0.90,
            ConfidenceLevel.MEDIUM: 0.65,
            ConfidenceLevel.LOW: 0.30,
        }[verdict.confidence]
        hyp = (
            [
                Hypothesis(
                    root_cause=primary_root,
                    confidence=confidence_score,
                    evidence=list(verdict.challenges),
                )
            ]
            if not verdict.confirmed
            else []
        )
        return self.make_turn(
            turn_number=round_num,
            message=message,
            hypotheses=hyp,
            confidence_score=confidence_score,
            corrections=verdict.corrections,
        )
