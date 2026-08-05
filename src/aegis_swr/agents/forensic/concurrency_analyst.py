"""Concurrency Analyst Agent - deadlock and race-condition specialist."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    ConcurrencyAnalystOutput,
    Hypothesis,
    InvestigationState,
)

_SYSTEM_PROMPT = """\
You are an expert in concurrent-programming hazards: deadlocks, lock-ordering \
inversions, race conditions, TOCTOU windows, thread wait-chains, and priority \
starvation. Reason about lock-acquisition order, thread state \
(blocked/runnable/waiting), mutex ownership, and synchronization-primitive \
signals such as WaitForMultipleObjects, EnterCriticalSection, pthread_mutex, \
std::mutex, CRITICAL_SECTION, futex, and os_unfair_lock.

Weight heavily toward a deadlock explanation when the incident's fault_class is \
deadlock, and toward race-condition hypotheses when the fault_class is \
use_after_free or assertion_failure.

Always respond with a structured JSON object matching the \
ConcurrencyAnalystOutput schema: hypotheses (list), confidence_score (float \
0.0-1.0), wait_chain (list of strings), lock_order_inversions (list of \
strings), and suspected_race (string or null). Populate wait_chain with the \
ordered thread/lock cycle when a deadlock is present, and lock_order_inversions \
with any observed acquisition-order reversals.\
"""

# Blocking / synchronization primitives whose presence signals a thread may be
# parked in a wait state. Matched case-insensitively.
_BLOCKING_PRIMITIVES: tuple[str, ...] = (
    "WaitForMultipleObjects",
    "WaitForSingleObject",
    "EnterCriticalSection",
    "pthread_mutex_lock",
    "pthread_mutex_trylock",
    "std::mutex",
    "CRITICAL_SECTION",
    "os_unfair_lock",
    "futex",
    "SleepConditionVariableCS",
    "MonitorEnter",
)

# Generic thread-identifier tokens (e.g. ``Thread-12``, ``Thread 7``, ``TID:0x1a``).
# Compiled once at import time - never inside the hot path.
_THREAD_RE = re.compile(r"(?:Thread[-\s]?|TID[:\s]?)[0-9A-Fa-fxX]+")


def _extract_wait_chain_candidates(text: str) -> list[str]:
    """Return human-readable blocking-primitive candidates found in *text*.

    A pure, side-effect-free helper: it inspects *text* with regex and keyword
    matching only. It performs no I/O and never launches a child process, runs
    dynamic code, or issues a database query. Returns an empty list when no
    blocking primitives are present.

    :param text: Raw text (e.g. the incident brief's ``raw_text_excerpt``).
    :type text: str
    :return: One candidate string per detected blocking primitive, annotated
        with any thread identifiers found in the text.
    :rtype: list[str]
    """
    if not text:
        return []
    lowered = text.lower()
    threads = list(dict.fromkeys(t.strip() for t in _THREAD_RE.findall(text)))
    thread_note = f" involving {', '.join(threads)}" if threads else ""

    candidates: list[str] = []
    for primitive in _BLOCKING_PRIMITIVES:
        if primitive.lower() in lowered:
            candidates.append(f"{primitive}{thread_note}")
    return candidates


class ConcurrencyAnalystAgent(BaseAgent):
    """Deadlock and race-condition debate specialist.

    Joins the panel for concurrency-domain fault classes and runs a
    deterministic wait-chain pre-check (regex/keyword only, never a
    shell/SQL/eval sink) over the incident brief before and independent of the
    LLM call, pre-populating wait-chain candidates when blocking primitives are
    present.
    """

    agent_key: ClassVar[str] = "concurrency_analyst"
    display_name: ClassVar[str] = "Concurrency Analyst Agent"
    category: ClassVar[AgentCategory] = "forensic"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    default_weight: ClassVar[float] = 0.30
    authoritative_fault_classes: ClassVar[frozenset[FaultClass]] = frozenset(
        {
            FaultClass.DEADLOCK,
            FaultClass.USE_AFTER_FREE,
            FaultClass.ASSERTION_FAILURE,
        }
    )

    @property
    def system_prompt(self) -> str:
        """Return the concurrency-analyst investigator system prompt for this agent."""
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        """Analyse concurrency/deadlock signals and return the agent's turn.

        :param state: the current investigation state (brief, arbiter feedback).
        :return: the concurrency-analyst agent's :class:`AgentTurn`.
        """
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})

        corrections: list[str] = state.get("latest_arbiter_feedback") or []

        # Deterministic wait-chain pre-check - fires before the LLM call.
        raw_excerpt = brief.get("raw_text_excerpt") or ""
        wait_chain_candidates = _extract_wait_chain_candidates(raw_excerpt)

        context: dict[str, object] = {"incident_brief": brief, "round": round_num}
        if brief.get("low_symbol_coverage_warning"):
            context["warning"] = brief["low_symbol_coverage_warning"]
        if corrections:
            context["skeptic_corrections_from_previous_round"] = corrections
        if wait_chain_candidates:
            context["wait_chain_candidates"] = wait_chain_candidates

        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, ConcurrencyAnalystOutput)
        assert isinstance(output, ConcurrencyAnalystOutput)

        # Merge: retain the deterministic candidates when the model returns an
        # empty wait_chain; never overwrite an already-populated one.
        if wait_chain_candidates and not output.wait_chain:
            output.wait_chain = list(wait_chain_candidates)

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
        elif output.suspected_race:
            base_message = f"Suspected race: {output.suspected_race}"
        else:
            base_message = "No concurrency fault detected."

        # Surface the wait chain into the debate transcript so the panel (and
        # tests) can observe the merged pre-check + LLM result.
        message = base_message
        if output.wait_chain:
            message = f"{base_message} Wait chain: {' -> '.join(output.wait_chain)}."

        turn = self.make_turn(
            turn_number=round_num,
            message=message,
            hypotheses=hypotheses,
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return turn
