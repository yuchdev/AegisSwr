from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypedDict
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from aegis_swr.core.fault_codes import FaultClass

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IncidentMode(str, Enum):
    CRASH_DUMP = "crash_dump"
    LOG_FORENSICS = "log_forensics"
    LIVE_PROCESS = "live_process"
    TELEMETRY_ANOMALY = "telemetry_anomaly"


class DumpFormat(str, Enum):
    WINDOWS_MINIDUMP = "windows_minidump"
    LINUX_CORE = "linux_core"
    APPLE_CRASHREPORT = "apple_crashreport"
    BREAKPAD = "breakpad"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    @classmethod
    def from_score(cls, score: float) -> ConfidenceLevel:
        if score >= 0.80:
            return cls.HIGH
        if score >= 0.50:
            return cls.MEDIUM
        return cls.LOW


# ---------------------------------------------------------------------------
# Source / Input
# ---------------------------------------------------------------------------


class IncidentSource(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    mode: IncidentMode
    incident_timestamp: datetime | None = None
    dump_path: str | None = None
    dump_format: DumpFormat | None = None
    dump_hash: str | None = None
    log_paths: list[str] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list)
    symbol_path: str | None = None
    user_assumption: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Debug extraction
# ---------------------------------------------------------------------------


class StackFrame(BaseModel):
    frame_number: int
    module: str | None = None
    function: str | None = None
    source_file: str | None = None
    source_line: int | None = None
    instruction_address: str


class DebugExtractionResult(BaseModel):
    fault_class: FaultClass
    exception_code_raw: str
    exception_address: str
    faulting_module: str | None = None
    faulting_function: str | None = None
    stack_frames: list[StackFrame] = Field(default_factory=list)
    debug_timestamp: datetime | None = None
    symbol_resolution_score: float = 0.0
    raw_text_excerpt: str = ""


# ---------------------------------------------------------------------------
# Agent turn types
# ---------------------------------------------------------------------------


class Hypothesis(BaseModel):
    root_cause: str
    faulting_module: str | None = None
    faulting_function: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float


class AgentTurn(BaseModel):
    agent: str
    turn_number: int
    message: str
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    confidence_score: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    corrections: list[str] = Field(default_factory=list)


class SkepticVerdict(BaseModel):
    confirmed: bool
    confidence: ConfidenceLevel
    challenges: list[str] = Field(default_factory=list)
    corrections: list[str] = Field(default_factory=list)


class HITLRequest(BaseModel):
    question: str
    context_summary: str
    requested_data: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Structured agent output schemas (used as output_schema in generate() calls)
# ---------------------------------------------------------------------------


class ExceptionSummary(BaseModel):
    fault_class: FaultClass
    exception_code_raw: str
    exception_address: str
    faulting_module: str | None = None
    faulting_function: str | None = None
    interpretation: str


class OSKernelOutput(BaseModel):
    exception_summary: ExceptionSummary
    hypotheses: list[Hypothesis]
    confidence_score: float


class RCAHypothesis(BaseModel):
    root_cause: str
    faulting_module: str | None = None
    faulting_function: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float
    code_location: str | None = None


class CodeAnalystOutput(BaseModel):
    rca: RCAHypothesis
    alternative_hypotheses: list[Hypothesis] = Field(default_factory=list)
    confidence_score: float
    probabilistic_fix: str | None = None
    fix_language: str | None = None


class PatternMatch(BaseModel):
    matched_incident_id: str
    similarity_score: float
    summary: str


class LogHistorianOutput(BaseModel):
    pattern_match: PatternMatch | None = None
    confidence_adjustment: float
    updated_confidence: float
    history_note: str


# ---------------------------------------------------------------------------
# Validation result (sandbox)
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    passed: bool | None = None
    exit_code: int | None = None
    compiler_output: str = ""
    lint_findings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Code history
# ---------------------------------------------------------------------------


class CommitRecord(BaseModel):
    sha: str
    message: str
    author: str
    timestamp: datetime
    files_changed: list[str] = Field(default_factory=list)


class BlameRecord(BaseModel):
    line_number: int
    sha: str
    author: str
    timestamp: datetime
    content: str


# ---------------------------------------------------------------------------
# UI context (screenshot OCR output)
# ---------------------------------------------------------------------------


class UIContext(BaseModel):
    error_message: str | None = None
    visible_timestamp: str | None = None
    ui_elements: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------


class RCAReport(BaseModel):
    incident_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: IncidentMode
    dump_hash: str | None = None
    symbol_resolution_score: float | None = None

    root_cause: str
    faulting_module: str | None = None
    faulting_function: str | None = None
    confidence_score: float
    confidence_level: ConfidenceLevel

    primary_hypothesis: Hypothesis
    alternative_hypotheses: list[Hypothesis] = Field(default_factory=list)
    skeptic_challenges: list[str] = Field(default_factory=list)
    agent_dialogue: list[AgentTurn] = Field(default_factory=list)
    consensus_rounds: int

    mitigation_instructions: list[str] = Field(default_factory=list)
    probabilistic_fix: str | None = None
    fix_confidence: float | None = None
    fix_validation_result: str | None = None

    hitl_request: HITLRequest | None = None

    total_input_tokens: int = 0
    total_output_tokens: int = 0


# ---------------------------------------------------------------------------
# Incident brief (Data Adapter output)
# ---------------------------------------------------------------------------


class IncidentBrief(BaseModel):
    """Token-dense, PII-scrubbed input produced by the Data Adapter.

    This object is LLM-safe: the PII substitution map is never stored here.
    The Data Adapter exposes the map separately so the orchestrator can persist
    it (encrypted) without it ever entering an agent prompt.
    """

    mode: IncidentMode
    dump_hash: str | None = None
    fault_class: FaultClass | None = None
    exception_code_raw: str | None = None
    exception_address: str | None = None
    faulting_module: str | None = None
    faulting_function: str | None = None
    symbol_resolution_score: float | None = None
    stack_frames: list[dict[str, Any]] = Field(default_factory=list)
    raw_text_excerpt: str | None = None
    log_summary: str | None = None
    ui_context: UIContext | None = None
    code_history: list[CommitRecord] = Field(default_factory=list)
    user_assumption: str | None = None
    low_symbol_coverage_warning: str | None = None


# ---------------------------------------------------------------------------
# LangGraph state (TypedDict — passed through the state graph)
# ---------------------------------------------------------------------------


class InvestigationState(TypedDict, total=False):
    incident_id: str
    incident_brief: dict[str, Any]
    source: dict[str, Any]
    discussion_history: list[dict[str, Any]]
    current_agent: str
    round_number: int
    consensus_score: float
    is_converged: bool
    primary_hypothesis: dict[str, Any] | None
    previous_hypothesis_key: str | None   # root_cause of last round's hypothesis
    current_round_scores: dict[str, float]  # per-agent scores for the current round
    hitl_pending: bool
    token_tracker: dict[str, int]
    result: dict[str, Any] | None          # serialised RCAReport on completion
    error: str | None
