"""Resource Exhaustion Agent - handle/fd/thread/memory-leak and OOM specialist."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from loguru import logger

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    Hypothesis,
    InvestigationState,
    ResourceExhaustionOutput,
)

_SYSTEM_PROMPT = """\
You are an expert in OS resource accounting, kernel object management, and \
production memory-leak forensics. You reason from handle tables, POSIX file \
descriptor limits, thread-pool watermarks, connection-pool metrics, heap and \
virtual-memory page counts, and GDI/USER/kernel object counts (semaphores, \
mutexes, events).

The user message includes a log_summary field: temporal growth patterns in that \
summary are your primary diagnostic channel for slow leaks. A deterministic scan \
has already pre-populated precheck_leak_indicators - you may append further \
indicators from your reasoning but must not remove the pre-populated entries.

Always respond with a structured JSON object matching the \
ResourceExhaustionOutput schema: hypotheses (list), confidence_score (float \
0.0-1.0), exhausted_resource (string or null - the most specific resource name \
resolvable, e.g. Win32 handle table, file descriptors, thread-pool workers), \
leak_indicators (list of strings), and growth_trend (string or null - populate \
only when temporal evidence exists).\
"""

# Resource-pressure signal patterns. Each entry is (canonical label, compiled
# regex). Matched case-insensitively; compiled once at import time.
_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("out of memory", re.compile(r"out ?of ?memory|outofmemoryerror|\boom\b", re.IGNORECASE)),
    ("too many open files", re.compile(r"too many open files", re.IGNORECASE)),
    ("system resource exhaustion", re.compile(r"ERROR_NO_SYSTEM_RESOURCES", re.IGNORECASE)),
    ("handle exhaustion", re.compile(r"handles?[^\n]{0,40}?\d{2,}", re.IGNORECASE)),
    (
        "thread exhaustion",
        re.compile(r"thread[^\n]{0,40}?(?:exhaust\w*|starv\w*|limit|max)", re.IGNORECASE),
    ),
    (
        "connection pool exhaustion",
        re.compile(r"connection ?pool[^\n]{0,40}?(?:exhaust\w*|full|timeout)", re.IGNORECASE),
    ),
    ("object handle exhaustion", re.compile(r"(?:GDI|USER) object[^\n]{0,40}?\d+", re.IGNORECASE)),
)

_MAX_INDICATOR_LEN = 200


class ResourceExhaustionAgent(BaseAgent):
    """Handle/fd/thread/memory-leak and OOM debate specialist.

    Joins the panel for resource-exhaustion-domain fault classes and runs a
    deterministic leak-indicator pre-check (regex only, never a shell/SQL/eval
    sink) over the incident brief's log summary and raw excerpt before and
    independent of the LLM call. Log-temporal patterns are the primary evidence
    channel, so ``log_summary`` is always included in the agent context.
    """

    agent_key: ClassVar[str] = "resource_exhaustion"
    display_name: ClassVar[str] = "Resource Exhaustion Agent"
    category: ClassVar[AgentCategory] = "forensic"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    default_weight: ClassVar[float] = 0.30
    authoritative_fault_classes: ClassVar[frozenset[FaultClass]] = frozenset(
        {
            FaultClass.RESOURCE_EXHAUSTION,
            FaultClass.STACK_OVERFLOW,
            FaultClass.DEADLOCK,
        }
    )

    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    @staticmethod
    def _extract_leak_indicators(brief: dict[str, object]) -> list[str]:
        """Return resource-pressure indicators found in the brief's text.

        Scans ``log_summary`` and ``raw_text_excerpt`` with regex only - it
        performs no I/O and never launches a child process, runs dynamic code,
        or issues a database query. Each indicator is a canonical label plus a
        trimmed match snippet (at most 200 chars). Never raises; on any internal
        error it logs a sanitized warning (no raw text) and returns an empty
        list.

        :param brief: The serialized incident brief.
        :type brief: dict[str, object]
        :return: Deduplicated indicators in first-occurrence order.
        :rtype: list[str]
        """
        try:
            parts = [str(brief.get(key)) for key in ("log_summary", "raw_text_excerpt") if brief.get(key)]
            text = "\n".join(parts)
            if not text:
                return []

            indicators: list[str] = []
            seen: set[str] = set()
            for label, pattern in _LEAK_PATTERNS:
                for match in pattern.finditer(text):
                    snippet = match.group(0).strip()
                    indicator = f"{label}: {snippet}"[:_MAX_INDICATOR_LEN]
                    if indicator not in seen:
                        seen.add(indicator)
                        indicators.append(indicator)
            return indicators
        except (TypeError, ValueError, re.error) as exc:
            logger.warning("leak-indicator pre-check failed: {}", type(exc).__name__)
            return []

    async def run(self, state: InvestigationState) -> AgentTurn:
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})

        corrections: list[str] = state.get("latest_arbiter_feedback") or []

        precheck_leak_indicators = self._extract_leak_indicators(brief)

        context: dict[str, object] = {
            "incident_brief": brief,
            "log_summary": brief.get("log_summary"),
            "precheck_leak_indicators": precheck_leak_indicators,
            "round": round_num,
        }
        if corrections:
            context["skeptic_corrections_from_previous_round"] = corrections

        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, ResourceExhaustionOutput)
        assert isinstance(output, ResourceExhaustionOutput)

        # Merge: prepend pre-check indicators not already present, preserving the
        # LLM-returned order; the deterministic entries are never dropped.
        output.leak_indicators = list(dict.fromkeys([*precheck_leak_indicators, *output.leak_indicators]))

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

        if output.exhausted_resource:
            message = f"Exhausted: {output.exhausted_resource}"
            if output.growth_trend:
                message = f"{message} ({output.growth_trend})"
        elif hypotheses:
            message = hypotheses[0].root_cause
        else:
            message = "No resource-exhaustion signal identified."

        turn = self.make_turn(
            turn_number=round_num,
            message=message,
            hypotheses=hypotheses,
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return turn
