"""Metadata-based incident similarity and recurrence scoring.

The Log Historian needs to know whether the incident under investigation has
been seen before.  Aegis SWR has no semantic vector store wired up, but every
saved :class:`~aegis_swr.core.schemas.RCAReport` already carries the structured
forensic fingerprint of its crash - the faulting module and function, the
source location, the exception code, and the debugger failure bucket.  Two
crashes from the *same* defect share that fingerprint even when their dump
hashes differ (a new dump every debug session).

This module distils both the live incident brief and each historical report
into an :class:`IncidentSignature`, scores them against each other with a
weighted field match, and turns the closest matches into a recurrence
probability the historian can reason about.  It is fully deterministic - no
embeddings, no network - so it is cheap to run on every round and trivial to
test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from aegis_swr.core.schemas import RCAReport

# ---------------------------------------------------------------------------
# Signature extraction
# ---------------------------------------------------------------------------

"""Source-file extensions we recognise when pulling a ``file:line`` location out
of free-form analysis text.
"""
_SOURCE_EXT = "cpp|cxx|cc|c|hpp|hh|h|rs|go|py|js|ts|java|cs|kt|swift|m|mm"

"""Code location, e.g. ``CrashUi.exe!Crash_Window::on_access_violation_click:123``."""
_CODE_LOCATION_RE = re.compile(
    rf"([\w.\\/-]+\.(?:{_SOURCE_EXT})):(\d+)", re.IGNORECASE
)

"""WinDbg failure bucket, e.g.
``NULL_POINTER_WRITE_c0000005_CrashUi.exe!Crash_Window::on_access_violation_click``.
"""
_FAILURE_BUCKET_RE = re.compile(r"\b([A-Z][A-Z0-9]+(?:_[A-Za-z0-9]+){2,})\b")

"""An NT-status / exception code: exactly 8 hex digits, optionally ``0x``-prefixed.
Hex-aware lookarounds (rather than ``\b``) so a code embedded in a failure
bucket like ``..._c0000005_...`` is found - underscores are word characters,
so ``\b`` never fires there - while a sub-run of a 16-digit address is not.
"""
_EXCEPTION_CODE_RE = re.compile(
    r"(?<![0-9a-fA-F])(?:0x)?([0-9a-fA-F]{8})(?![0-9a-fA-F])"
)


def _norm_module(module: Optional[str]) -> Optional[str]:
    """Lowercase a module name and strip any path and image extension."""
    if not module:
        return None
    name = re.split(r"[\\/]", module.strip())[-1]
    name = re.sub(r"\.(exe|dll|sys|so|dylib)$", "", name, flags=re.IGNORECASE)
    return name.lower() or None


def _norm_function(function: Optional[str]) -> Optional[str]:
    """Normalize a symbol: drop the ``module!`` prefix and ``+0x…`` offset."""
    if not function:
        return None
    name = function.strip()
    if "!" in name:
        name = name.split("!", 1)[1]
    name = re.split(r"\+0x", name, maxsplit=1)[0]
    return name.strip().lower() or None


def _norm_code_location(source_file: Optional[str], source_line: Optional[Any]) -> Optional[str]:
    """Render ``basename:line`` from an explicit file and line."""
    if not source_file or source_line in (None, "", 0):
        return None
    base = re.split(r"[\\/]", str(source_file).strip())[-1]
    return f"{base.lower()}:{source_line}"


def _norm_exception_code(raw: Optional[str]) -> Optional[str]:
    """Reduce an exception code to bare lowercase hex (``0xC0000005`` → ``c0000005``)."""
    if not raw:
        return None
    match = _EXCEPTION_CODE_RE.search(str(raw))
    return match.group(1).lower() if match else None


def _norm_bucket(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return raw.strip().rstrip(".").lower() or None


def _find_code_location(text: str) -> Optional[str]:
    match = _CODE_LOCATION_RE.search(text)
    if not match:
        return None
    return _norm_code_location(match.group(1), match.group(2))


def _find_failure_bucket(text: str) -> Optional[str]:
    """Pull the most bucket-like token out of *text* (longest underscore run)."""
    candidates = [
        c for c in _FAILURE_BUCKET_RE.findall(text) if _EXCEPTION_CODE_RE.search(c)
    ]
    if not candidates:
        return None
    return _norm_bucket(max(candidates, key=len))


@dataclass(frozen=True)
class IncidentSignature:
    """The structural fingerprint of one crash, ready for field-wise comparison."""

    fault_class: Optional[str] = None
    exception_code: Optional[str] = None
    faulting_module: Optional[str] = None
    faulting_function: Optional[str] = None
    code_location: Optional[str] = None
    failure_bucket: Optional[str] = None

    def as_dict(self) -> dict[str, Optional[str]]:
        return {
            "fault_class": self.fault_class,
            "exception_code": self.exception_code,
            "faulting_module": self.faulting_module,
            "faulting_function": self.faulting_function,
            "code_location": self.code_location,
            "failure_bucket": self.failure_bucket,
        }


def signature_from_brief(brief: dict[str, Any]) -> IncidentSignature:
    """Build a signature from the live :class:`IncidentBrief` (as a dict)."""
    frames = brief.get("stack_frames") or []
    code_location: Optional[str] = None
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        code_location = _norm_code_location(frame.get("source_file"), frame.get("source_line"))
        if code_location:
            break

    excerpt = str(brief.get("raw_text_excerpt") or "")
    if code_location is None and excerpt:
        code_location = _find_code_location(excerpt)

    fault_class = brief.get("fault_class")
    return IncidentSignature(
        fault_class=str(fault_class).lower() if fault_class else None,
        exception_code=_norm_exception_code(brief.get("exception_code_raw")),
        faulting_module=_norm_module(brief.get("faulting_module")),
        faulting_function=_norm_function(brief.get("faulting_function")),
        code_location=code_location,
        failure_bucket=_find_failure_bucket(excerpt) if excerpt else None,
    )


def signature_from_report(report: RCAReport) -> IncidentSignature:
    """Build a signature from a stored report, mining its evidence text."""
    text_parts = [report.root_cause or ""]
    primary = report.primary_hypothesis
    if primary is not None:
        text_parts.append(primary.root_cause or "")
        text_parts.extend(e for e in primary.evidence if not e.startswith("__fix__:"))
    text = "\n".join(text_parts)

    module = report.faulting_module or (primary.faulting_module if primary else None)
    function = report.faulting_function or (primary.faulting_function if primary else None)
    return IncidentSignature(
        fault_class=None,  # not persisted on the report; inferred only on the live side
        exception_code=_norm_exception_code(text),
        faulting_module=_norm_module(module),
        faulting_function=_norm_function(function),
        code_location=_find_code_location(text),
        failure_bucket=_find_failure_bucket(text),
    )


# ---------------------------------------------------------------------------
# Similarity scoring
# ---------------------------------------------------------------------------

"""Per-field contribution to the similarity score.  The failure bucket and the
faulting symbol are the most discriminating; the module alone is weak.
"""
_FIELD_WEIGHTS: dict[str, float] = {
    "failure_bucket": 0.30,
    "faulting_function": 0.25,
    "code_location": 0.20,
    "exception_code": 0.12,
    "faulting_module": 0.10,
    "fault_class": 0.03,
}

"""Fields specific enough that, without at least one of them matching, a high
score (driven by module/exception alone) is not trustworthy.
"""
_STRONG_FIELDS = ("failure_bucket", "faulting_function", "code_location")

"""Score ceiling when no strong field is comparable on both sides."""
_WEAK_ONLY_CAP = 0.40



def similarity(a: IncidentSignature, b: IncidentSignature) -> float:
    """Weighted field-match score in ``[0, 1]``.

    Only fields populated on *both* signatures contribute, so a sparsely
    populated historical report is not penalized for what it never recorded.
    If nothing discriminating (bucket / symbol / source line) is comparable,
    the score is capped at :data:`_WEAK_ONLY_CAP`.
    """
    a_fields, b_fields = a.as_dict(), b.as_dict()
    matched = 0.0
    comparable = 0.0
    strong_compared = False
    for field_name, weight in _FIELD_WEIGHTS.items():
        av, bv = a_fields[field_name], b_fields[field_name]
        if av is None or bv is None:
            continue
        comparable += weight
        if field_name in _STRONG_FIELDS:
            strong_compared = True
        if av == bv:
            matched += weight
    if comparable == 0.0:
        return 0.0
    score = matched / comparable
    if not strong_compared:
        score = min(score, _WEAK_ONLY_CAP)
    return round(score, 4)


# ---------------------------------------------------------------------------
# History analysis
# ---------------------------------------------------------------------------

"""Minimum similarity for a historical report to count as the *same* incident."""
DEFAULT_MATCH_THRESHOLD = 0.55


@dataclass
class HistoryMatch:
    """One historical report judged to be the same incident as the live one."""

    incident_id: str
    similarity: float
    created_at: Optional[str]
    faulting_function: Optional[str]
    code_location: Optional[str]
    failure_bucket: Optional[str]
    root_cause: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "similarity": self.similarity,
            "created_at": self.created_at,
            "faulting_function": self.faulting_function,
            "code_location": self.code_location,
            "failure_bucket": self.failure_bucket,
            "root_cause": self.root_cause,
        }


@dataclass
class HistoryAnalysis:
    """The historian's precomputed view of how this incident relates to the past."""

    current_signature: IncidentSignature
    matches: list[HistoryMatch] = field(default_factory=list)
    history_size: int = 0
    recurrence_probability: float = 0.0
    suggested_confidence_adjustment: float = 0.0

    @property
    def recurrence_count(self) -> int:
        return len(self.matches)

    @property
    def is_recurrence(self) -> bool:
        return bool(self.matches)

    def summary(self) -> str:
        """A one-line human-readable verdict for prompts and logs."""
        if not self.history_size:
            return "No historical reports were available to compare against."
        if not self.matches:
            return (
                f"Checked {self.history_size} prior report(s); no matching signature - "
                "this appears to be a first-observed crash."
            )
        top = self.matches[0]
        return (
            f"Recurrence: matched {self.recurrence_count} of {self.history_size} prior "
            f"report(s) (best {top.similarity:.0%}, recurrence probability "
            f"{self.recurrence_probability:.0%}); closest is incident {top.incident_id}."
        )

    def as_context(self) -> dict[str, Any]:
        """The structured block fed to the Log Historian LLM."""
        return {
            "current_signature": self.current_signature.as_dict(),
            "history_size": self.history_size,
            "matched_incidents": [m.as_dict() for m in self.matches],
            "recurrence_count": self.recurrence_count,
            "is_recurrence": self.is_recurrence,
            "recurrence_probability": round(self.recurrence_probability, 4),
            "suggested_confidence_adjustment": round(
                self.suggested_confidence_adjustment, 4
            ),
            "summary": self.summary(),
        }


def _recurrence_probability(best: float, count: int) -> float:
    """Combine match strength with repeat count into a recurrence probability.

    A single strong match is already convincing; each further confirmed repeat
    pushes certainty toward 1 with diminishing returns.
    """
    if count <= 0:
        return round(best, 4)
    return round(best + (1.0 - best) * (1.0 - 0.5 ** count), 4)


def _suggested_adjustment(probability: float, matched: bool, history_size: int) -> float:
    """Confidence nudge for the historian, bounded to ``[-0.2, +0.2]``.

    A recurrence reinforces the diagnosis (positive); a genuinely novel
    signature against a non-empty history is a mild caution (negative).
    """
    if matched:
        return round(min(0.2, 0.2 * probability), 4)
    if history_size:
        return -0.05
    return 0.0


def analyze_history(
    brief: dict[str, Any],
    history: list[RCAReport],
    *,
    exclude_incident_id: Optional[str] = None,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> HistoryAnalysis:
    """Score the live incident against *history* and derive recurrence stats."""
    current = signature_from_brief(brief)
    considered: list[RCAReport] = [
        r
        for r in history
        if exclude_incident_id is None or str(r.incident_id) != str(exclude_incident_id)
    ]

    matches: list[HistoryMatch] = []
    for report in considered:
        sig = signature_from_report(report)
        score = similarity(current, sig)
        if score >= threshold:
            matches.append(
                HistoryMatch(
                    incident_id=str(report.incident_id),
                    similarity=score,
                    created_at=report.created_at.isoformat() if report.created_at else None,
                    faulting_function=sig.faulting_function,
                    code_location=sig.code_location,
                    failure_bucket=sig.failure_bucket,
                    root_cause=(report.root_cause or "").strip(),
                )
            )

    matches.sort(key=lambda m: m.similarity, reverse=True)
    best = matches[0].similarity if matches else 0.0
    probability = _recurrence_probability(best, len(matches))
    adjustment = _suggested_adjustment(probability, bool(matches), len(considered))

    return HistoryAnalysis(
        current_signature=current,
        matches=matches,
        history_size=len(considered),
        recurrence_probability=probability,
        suggested_confidence_adjustment=adjustment,
    )
