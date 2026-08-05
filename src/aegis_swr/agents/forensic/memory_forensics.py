"""Memory Forensics Agent - heap-corruption and memory-safety specialist."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    Hypothesis,
    InvestigationState,
    MemoryForensicsOutput,
)

_SYSTEM_PROMPT = """\
You are an expert memory-safety and heap-corruption forensics specialist. Your \
primary specialism is heap corruption, use-after-free, double-free, buffer \
over/underflow, allocator and heap-metadata tells, guard-page hits, and \
fill-pattern sentinel analysis (0xCCCCCCCC, 0xFEEEFEEE, 0xBAADF00D, 0xDDDDDDDD, \
0xABABABAB, 0xCDCDCDCD).

Reason about allocator metadata consistency, chunk size fields, free-list \
linkage, guard pages, fill patterns, and allocation-site provenance to explain \
how memory was corrupted or misused.

Always respond with a structured JSON object matching the MemoryForensicsOutput \
schema. Set confidence_score to a value between 0.0 and 1.0 reflecting your \
certainty. Populate corruption_signatures with every hex sentinel or allocator \
anomaly you find, suspected_allocation_site when the allocation origin is \
traceable, and heap_state with a concise assessment of the heap's integrity. \
Do not repeat raw stack text verbatim and never include PII or credential \
values.\
"""

# Known heap-metadata / uninitialized-memory fill-pattern sentinels. Longer
# constants precede their prefixes (``CCCCCCCC`` before ``CCCC``) so the full
# value is captured. Compiled once at import time - never inside the hot path.
_FILL_PATTERN_RE = re.compile(
    r"0x(?:CCCCCCCC|CCCC|FEEEFEEE|BAADF00D|DDDDDDDD|ABABABAB|CDCDCDCD)",
    re.IGNORECASE,
)


class MemoryForensicsAgent(BaseAgent):
    """Heap-corruption and memory-safety debate specialist.

    Joins the panel for memory-domain fault classes and runs a deterministic
    fill-pattern pre-check (regex only, never a shell/SQL/eval sink) over the
    incident brief before and independent of the LLM call, surfacing any known
    sentinel values immediately.
    """

    agent_key: ClassVar[str] = "memory_forensics"
    display_name: ClassVar[str] = "Memory Forensics Agent"
    category: ClassVar[AgentCategory] = "forensic"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    default_weight: ClassVar[float] = 0.25
    authoritative_fault_classes: ClassVar[frozenset[FaultClass]] = frozenset(
        {
            FaultClass.MEMORY_ACCESS_VIOLATION,
            FaultClass.NULL_POINTER_DEREFERENCE,
            FaultClass.USE_AFTER_FREE,
        }
    )

    @property
    def system_prompt(self) -> str:
        """Return the memory-forensics investigator system prompt for this agent."""
        return _SYSTEM_PROMPT

    @staticmethod
    def _detect_fill_patterns(brief: dict[str, object]) -> list[str]:
        """Scan the brief's text for known fill-pattern sentinels (regex only).

        Operates purely on strings: the structured stack frames are serialized
        to JSON text and concatenated with the raw excerpt, then matched. The
        untrusted payload text is never passed to a shell, SQL, ``eval``, or any
        other sink - regex scanning is the only operation performed on it.

        :param brief: The serialized incident brief.
        :type brief: dict[str, object]
        :return: Unique sentinel values (normalized as ``0x`` + uppercase hex),
            in first-seen order.
        :rtype: list[str]
        """
        raw_excerpt = brief.get("raw_text_excerpt") or ""
        stack_frames = brief.get("stack_frames") or []
        haystack = f"{raw_excerpt}\n{json.dumps(stack_frames)}"

        seen: dict[str, None] = {}
        for match in _FILL_PATTERN_RE.findall(haystack):
            seen.setdefault(f"0x{match[2:].upper()}", None)
        return list(seen)

    async def run(self, state: InvestigationState) -> AgentTurn:
        """Analyse memory-corruption signatures and return the agent's turn.

        Runs a deterministic fill-pattern pre-check before the LLM call and merges
        its findings into the result.

        :param state: the current investigation state (brief, arbiter feedback).
        :return: the memory-forensics agent's :class:`AgentTurn`.
        """
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})

        # Incorporate any arbiter corrections carried over from the previous round.
        corrections: list[str] = state.get("latest_arbiter_feedback") or []

        # Deterministic fill-pattern pre-check - runs before the LLM call and its
        # results are never discarded by the merge below.
        pre_detected_signatures = self._detect_fill_patterns(brief)

        context: dict[str, object] = {"incident_brief": brief, "round": round_num}
        context["pre_detected_signatures"] = pre_detected_signatures
        if corrections:
            context["skeptic_corrections_from_previous_round"] = corrections

        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, MemoryForensicsOutput)
        assert isinstance(output, MemoryForensicsOutput)

        # Merge: the deterministic pre-check results are always retained even
        # when the model returns an empty corruption_signatures list.
        merged_signatures = list(dict.fromkeys([*pre_detected_signatures, *output.corruption_signatures]))

        hypotheses = [
            Hypothesis(
                root_cause=h.root_cause,
                faulting_module=h.faulting_module,
                faulting_function=h.faulting_function,
                evidence=h.evidence,
                confidence=h.confidence,
            )
            for h in output.hypotheses
        ]

        if hypotheses:
            base_message = hypotheses[0].root_cause
        elif output.heap_state:
            base_message = output.heap_state
        else:
            base_message = "No memory-corruption signal identified."

        # Surface merged signatures into the debate transcript so the panel (and
        # tests) can observe that pre-check + LLM findings are retained together.
        if merged_signatures:
            message = f"{base_message} Detected corruption signatures: {', '.join(merged_signatures)}."
        else:
            message = base_message

        turn = self.make_turn(
            turn_number=round_num,
            message=message,
            hypotheses=hypotheses,
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return turn
