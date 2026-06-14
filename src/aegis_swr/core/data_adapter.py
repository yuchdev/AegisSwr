"""Data Adapter - the non-LLM preprocessing pipeline.

Converts a raw :class:`IncidentSource` into a token-dense, PII-scrubbed
:class:`IncidentBrief`. Runs synchronously (no LLM calls) before any agent is
invoked. See ``docs/specs/generic_implementation_plan.md`` Phase 2 for the stage contract.

Pipeline stages:
    1. Source validation and content hashing (SHA-256, before any backend call)
    2. Dump extraction (delegated to a DebugBackend)
    3. Global noise pre-filter (DBGHELP / fill patterns / DLL list / truncate)
    4. Log processing (temporal window, Drain3 clustering, severity isolation)
    5. Screenshot OCR (optional)
    6. PII scrubbing (always runs; regex baseline + optional Presidio NER)
    7. User-assumption token cap
    8. Code-history query (optional)
    9. Incident-brief assembly
"""
from __future__ import annotations

import re
import hashlib
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from presidio_analyzer import AnalyzerEngine
from loguru import logger
import pytesseract
from PIL import Image

from aegis_swr.core.schemas import (
    CommitRecord,
    DumpFormat,
    IncidentBrief,
    IncidentSource,
    UIContext,
)
from aegis_swr.core.tokens import count_tokens, truncate_to_tokens
from aegis_swr.backends.base import CodeBackend, DebugBackend, LogBackend
from aegis_swr.config.settings import Settings


# ---------------------------------------------------------------------------
# Stage 3: noise filter (module-level so DebugBackends can reuse it)
# ---------------------------------------------------------------------------

_DBGHELP_RE = re.compile(r"^DBGHELP:.*?file not found\s*$\n?", re.MULTILINE)
_DLL_LIST_RE = re.compile(r"\*\*\* WARNING:.*?(?=EXCEPTION_ANALYSIS:)", re.DOTALL)
_FILL_RE = re.compile(
    r"0x(?:CCCCCCCC|DDDDDDDD|FEEEFEEE|ABABABAB|BAADF00D)",
    re.IGNORECASE,
)
_TRUNCATION_MARKER = "\n[... middle section truncated ...]\n"
_NOISE_TRUNCATE_CHARS = 8000
_NOISE_HEAD_TAIL = 4000


def apply_noise_filter(text: str) -> str:
    """Strip debugger noise and truncate to an 8 000-char head+tail window.

    Order matters: remove DBGHELP lines and the DLL load list first, collapse
    fill patterns, then apply head+tail truncation last so the truncation budget
    is spent on signal rather than noise.
    """
    if not text:
        return text
    text = _DBGHELP_RE.sub("", text)
    text = _DLL_LIST_RE.sub("", text)
    text = _FILL_RE.sub("<fill>", text)
    if len(text) > _NOISE_TRUNCATE_CHARS:
        head = text[:_NOISE_HEAD_TAIL]
        tail = text[-_NOISE_HEAD_TAIL:]
        text = head + _TRUNCATION_MARKER + tail
    return text


# ---------------------------------------------------------------------------
# Stage 4 helpers: timestamp parsing & severity
# ---------------------------------------------------------------------------

_ISO_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")
_TIME_ONLY_RE = re.compile(r"\[(\d{2}):(\d{2}):(\d{2})]")
_SEVERITY_RE = re.compile(
    r"\b(TRACE|DEBUG|INFO|WARNING|WARN|ERROR|FATAL|CRITICAL)\b", re.IGNORECASE
)
_SEVERITY_RANK = {
    "TRACE": 0,
    "DEBUG": 1,
    "INFO": 2,
    "WARN": 3,
    "WARNING": 3,
    "ERROR": 4,
    "FATAL": 5,
    "CRITICAL": 5,
}
_WARNING_RANK = 3
_DEFAULT_RANK = 2  # treat lines with no explicit level as INFO
_INNER_WINDOW_SECONDS = 5
_LOG_TOKEN_BUDGET = 2000
_NO_TIMESTAMP_TAIL = 500


def _parse_timestamp(line: str, reference: datetime) -> Optional[datetime]:
    """Extract a timestamp from a log line, anchored to the incident date"""
    iso = _ISO_TS_RE.search(line)
    if iso:
        try:
            parsed = datetime.fromisoformat(f"{iso.group(1)}T{iso.group(2)}")
        except ValueError:
            return None
        return parsed.replace(tzinfo=reference.tzinfo)
    clock = _TIME_ONLY_RE.search(line)
    if clock:
        hour, minute, second = (int(g) for g in clock.groups())
        try:
            return reference.replace(
                hour=hour, minute=minute, second=second, microsecond=0
            )
        except ValueError:
            return None
    return None


def _severity_rank(line: str) -> int:
    """Return the numeric severity rank for a log line (0-5).

    Higher rank indicates more severe. Returns 2 (INFO) if no severity token is found.
    """
    match = _SEVERITY_RE.search(line)
    if not match:
        return _DEFAULT_RANK
    return _SEVERITY_RANK[match.group(1).upper()]


def _severity_token(line: str) -> Optional[str]:
    """Return the uppercased severity token in *line*, or None if none is present.

    Reused by ``FileLogAdapter`` so the severity vocabulary stays in one place.
    """
    match = _SEVERITY_RE.search(line)
    return match.group(1).upper() if match else None


# ---------------------------------------------------------------------------
# Stage 6 helpers: deterministic PII regexes (always-on baseline)
# ---------------------------------------------------------------------------

_DB_CONN_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@[^\s/]+")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_CREDIT_CARD_RE = re.compile(r"\b\d(?:[ \-]?\d){12,18}\b")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# (label, regex) applied in order; DB connection strings first since they
# embed credentials we don't want partially matched by the email/IP rules.
_PII_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("DB_CONN", _DB_CONN_RE),
    ("EMAIL", _EMAIL_RE),
    ("AWS_KEY", _AWS_KEY_RE),
    ("CREDIT_CARD", _CREDIT_CARD_RE),
    ("IP", _IPV4_RE),
]


class _ScrubState:
    """Accumulates a stable substitution map across multiple scrubbed fields"""

    def __init__(self):
        """Initialize a new scrubbing state with empty mapping and counters."""
        self.mapping: dict[str, str] = {}  # token -> original value
        self._counters: dict[str, int] = defaultdict(int)
        self._reverse: dict[tuple[str, str], str] = {}  # (label, value) -> token

    def token_for(self, label: str, value: str) -> str:
        """Return a stable token (e.g. [REDACTED_EMAIL_1]) for a PII value.

        If the same (label, value) pair is requested again, we return the same token.
        Maintains an internal mapping for later retrieval.
        """
        key = (label, value)
        if key in self._reverse:
            return self._reverse[key]
        self._counters[label] += 1
        token = f"[REDACTED_{label}_{self._counters[label]}]"
        self.mapping[token] = value
        self._reverse[key] = token
        return token


class DataAdapter:
    """Stateful-per-call preprocessor producing an :class:`IncidentBrief`.

    After :meth:`process` returns, :attr:`last_pii_substitution_map` holds the
    PII map for the most recent call. The orchestrator must read it immediately
    and persist it out-of-band; it is intentionally never part of the brief.
    """

    def __init__(self, settings: Settings):
        """Initialize the adapter with application settings.

        Args:
            settings: Global configuration object.
        """
        self._settings = settings
        self.last_pii_substitution_map: dict[str, str] = {}

    # -- public entry point ------------------------------------------------

    async def process(
        self,
        source: IncidentSource,
        debug_backend: Optional[DebugBackend] = None,
        code_backend: Optional[CodeBackend] = None,
        log_backend: Optional[LogBackend] = None,
    ) -> IncidentBrief:
        """Run the 9-stage preprocessing pipeline on a crash incident source.

        Orchestrates extraction, noise filtering, log processing, OCR, PII scrubbing,
        token enforcement, and code history queries. The PII map is stored in
        :attr:`last_pii_substitution_map` for out-of-band persistence.

        Args:
            source: The crash incident data (dump, logs, screenshots, etc.).
            debug_backend: Optional backend to extract crash data. If None, skips extraction.
            code_backend: Optional backend to retrieve code commit history.
            log_backend: Optional backend to query structured logs.

        Returns:
            An :class:`IncidentBrief` ready for downstream agent processing.
        """
        scrub = _ScrubState()

        # Stage 1: hash + format detection
        dump_hash = source.dump_hash
        dump_format = source.dump_format
        if source.dump_path:
            path = Path(source.dump_path)
            if path.exists():
                if dump_hash is None:
                    dump_hash = self._compute_hash(path)
                if dump_format is None:
                    dump_format = self._detect_format(path)

        # Stage 2: dump extraction
        fault_class = None
        exception_code_raw = None
        exception_address = None
        faulting_module = None
        faulting_function = None
        symbol_score: Optional[float] = None
        exception_code: Optional[str] = None
        raw_excerpt: Optional[str] = None
        stack_frames: list[dict[str, Any]] = []

        if debug_backend is not None and source.dump_path:
            extraction = debug_backend.extract(source, source.symbol_path)
            fault_class = extraction.fault_class
            exception_code_raw = extraction.exception_code_raw
            exception_address = extraction.exception_address
            faulting_module = extraction.faulting_module
            faulting_function = extraction.faulting_function
            symbol_score = extraction.symbol_resolution_score
            limit = self._settings.core.stack_frames_limit
            stack_frames = [f.model_dump(mode="json") for f in extraction.stack_frames[:limit]]
            # Stage 3: noise filter, then Stage 6 scrub
            raw_excerpt = self._scrub_text(apply_noise_filter(extraction.raw_text_excerpt), scrub)

        # Stage 4: log processing (merge file lines + LogBackend lines), then scrub
        backend_lines = await self._query_log_backend(source, log_backend)
        log_summary = self._process_logs(
            source.log_paths, source.incident_timestamp, extra_lines=backend_lines
        )
        if log_summary:
            log_summary = self._scrub_text(log_summary, scrub)

        # Stage 5: screenshot OCR, then Stage 6 scrub
        ui_context = self._process_screenshots(source.screenshot_paths)
        if ui_context and ui_context.error_message:
            ui_context.error_message = self._scrub_text(ui_context.error_message, scrub)

        # Stage 6 (cont.) + Stage 7: scrub assumption, then enforce token cap
        user_assumption = source.user_assumption
        if user_assumption:
            user_assumption = self._scrub_text(user_assumption, scrub)
            user_assumption = self._enforce_assumption_limit(user_assumption)

        # Stage 8: code history
        code_history = self._query_code_history(source, code_backend)

        # Persist the PII map out-of-band (never in the brief).
        self.last_pii_substitution_map = scrub.mapping

        # Stage 9: assemble
        low_symbol_warning = None
        if symbol_score is not None and symbol_score < 0.50:
            low_symbol_warning = f"[LOW SYMBOL COVERAGE: {symbol_score:.0%}]"

        return IncidentBrief(
            mode=source.mode,
            dump_hash=dump_hash,
            fault_class=fault_class,
            exception_code_raw=exception_code_raw,
            exception_address=exception_address,
            faulting_module=faulting_module,
            faulting_function=faulting_function,
            symbol_resolution_score=symbol_score,
            stack_frames=stack_frames,
            raw_text_excerpt=raw_excerpt,
            log_summary=log_summary,
            ui_context=ui_context,
            code_history=code_history,
            user_assumption=user_assumption,
            low_symbol_coverage_warning=low_symbol_warning,
        )

    # -- Stage 1 -----------------------------------------------------------

    @staticmethod
    def _compute_hash(path: Path) -> str:
        """Compute the SHA-256 hash of a file in 8 KB chunks.

        Args:
            path: Path to the file to hash.

        Returns:
            Hash string prefixed with 'sha256:', e.g., 'sha256:a1b2c3...'.
        """
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _detect_format(path: Path) -> DumpFormat:
        """Detect the crash dump format from file magic bytes and extension.

        Checks for MDMP (Windows minidump), ELF (Linux core), or JSON-like
        (Apple crash report) signatures. Falls back to Windows minidump if uncertain.

        Args:
            path: Path to the crash dump file.

        Returns:
            A :class:`DumpFormat` enum value.
        """
        with path.open("rb") as handle:
            magic = handle.read(8)
        if magic[:4] == b"MDMP":
            return DumpFormat.WINDOWS_MINIDUMP
        if magic[:4] == b"\x7fELF":
            return DumpFormat.LINUX_CORE
        if magic[:1] in (b"{", b"["):
            return DumpFormat.APPLE_CRASHREPORT
        suffix = path.suffix.lower()
        if suffix == ".core":
            return DumpFormat.LINUX_CORE
        if suffix in (".ips", ".crash"):
            return DumpFormat.APPLE_CRASHREPORT
        return DumpFormat.WINDOWS_MINIDUMP

    # -- Stage 4 -----------------------------------------------------------

    def _process_logs(
        self,
        log_paths: list[str],
        incident_ts: Optional[datetime],
        extra_lines: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Load, filter, cluster, and truncate log lines around the incident time.

        Reads log files, applies temporal windowing, deduplicates via Drain3
        clustering, and enforces a token budget. Gracefully handles missing files
        and missing timestamps.

        Args:
            log_paths: Relative or absolute paths to log files.
            incident_ts: Timestamp of the incident; used to window the logs.
            extra_lines: Optional additional log lines (e.g., from a LogBackend).

        Returns:
            A multi-line string of filtered log lines, or None if no logs remain
            after processing.
        """
        raw: list[str] = []
        for raw_path in log_paths:
            path = Path(raw_path)
            if not path.exists():
                logger.warning(f"Log path does not exist, skipping: {raw_path}")
                continue
            raw.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        if extra_lines:
            raw.extend(extra_lines)
        if not raw:
            return None

        if incident_ts is not None:
            windowed = self._apply_temporal_window(raw, incident_ts)
        else:
            logger.warning("No incident timestamp; falling back to last 500 log lines")
            windowed = raw[-_NO_TIMESTAMP_TAIL:]

        if not windowed:
            return None

        clustered = self._cluster_and_dedup(windowed)
        summary = "\n".join(clustered)
        summary, truncated = self._enforce_log_budget(summary)
        if truncated:
            logger.warning("Log summary exceeded token budget; oldest lines dropped")
        return summary or None

    def _apply_temporal_window(
        self,
        lines: list[str],
        incident_ts: datetime,
    ) -> list[str]:
        """Filter log lines to a window around the incident time.

        Lines with high severity (WARNING+) are kept within the outer window.
        All severity levels (including INFO/DEBUG) are kept within an inner window
        around the exact incident time. Lines without parseable timestamps are
        always retained to avoid discarding relevant anomalies.

        Args:
            lines: Raw log lines to filter.
            incident_ts: The incident timestamp to window around.

        Returns:
            Filtered list of log lines within the temporal window.
        """
        window = timedelta(seconds=self._settings.core.log_window_seconds)
        inner = timedelta(seconds=_INNER_WINDOW_SECONDS)
        kept: list[str] = []
        for line in lines:
            ts = _parse_timestamp(line, incident_ts)
            rank = _severity_rank(line)
            if ts is None:
                # Cannot place this line in time; retain it rather than risk
                # dropping a relevant anomaly.
                kept.append(line)
                continue
            delta = abs(ts - incident_ts)
            if delta > window:
                continue
            if rank >= _WARNING_RANK or delta <= inner:
                kept.append(line)
            # INFO/DEBUG outside the inner window are dropped.
        return kept

    @staticmethod
    def _cluster_and_dedup(lines: list[str]) -> list[str]:
        """Deduplicate and compress log lines using Drain3 template mining.

        Groups repeated log messages into templates, emits each template once
        with a count (e.g., "(×42)"), and keeps unique lines as-is. Falls back
        to returning input lines unmodified if drain3 is unavailable.

        Args:
            lines: Log lines to deduplicate.

        Returns:
            Deduplicated and compressed log lines.
        """
        try:
            from drain3 import TemplateMiner
            from drain3.template_miner_config import TemplateMinerConfig
        except ImportError:  # pragma: no cover - drain3 is a core dependency
            logger.warning("drain3 unavailable; skipping log clustering")
            return lines

        config = TemplateMinerConfig()
        config.profiling_enabled = False
        miner = TemplateMiner(config=config)

        assigned: list[tuple[str, int]] = []
        counts: dict[int, int] = defaultdict(int)
        for line in lines:
            if not line.strip():
                continue
            result = miner.add_log_message(line)
            cluster_id = int(result["cluster_id"])
            assigned.append((line, cluster_id))
            counts[cluster_id] += 1

        output: list[str] = []
        emitted: set[int] = set()
        for line, cluster_id in assigned:
            if counts[cluster_id] > 3:
                if cluster_id in emitted:
                    continue
                emitted.add(cluster_id)
                output.append(f"{line} (×{counts[cluster_id]})")
            else:
                output.append(line)
        return output

    @staticmethod
    def _enforce_log_budget(text: str) -> tuple[str, bool]:
        """Truncate log text to stay within the token budget.

        Removes oldest lines first (from the top) until the text fits within
        the budget. Logs often precede an incident, so keeping recent lines
        and dropping old context is intentional.

        Args:
            text: Multi-line log text.

        Returns:
            Tuple of (truncated_text, was_truncated).
        """
        if count_tokens(text) <= _LOG_TOKEN_BUDGET:
            return text, False
        lines = text.split("\n")
        while lines and count_tokens("\n".join(lines)) > _LOG_TOKEN_BUDGET:
            lines.pop(0)  # drop oldest first
        return "\n".join(lines), True

    # -- Stage 5 -----------------------------------------------------------

    @staticmethod
    def _process_screenshots(screenshot_paths: list[str]) -> Optional[UIContext]:
        """Extract and OCR text from screenshots with Tesseract and Pillow.

        Processes images, filters text by confidence (>60%), and assembles a UI
        context. Gracefully falls back to None if libraries are unavailable or
        OCR fails on individual images.

        Args:
            screenshot_paths: Paths to screenshot files.

        Returns:
            A :class:`UIContext` with extracted text, or None if no text was found.
        """
        words: list[str] = []
        for raw_path in screenshot_paths:
            path = Path(raw_path)
            if not path.exists():
                continue
            try:
                data = pytesseract.image_to_data(
                    Image.open(path), output_type=pytesseract.Output.DICT
                )
            except Exception as exc:  # pragma: no cover - depends on tesseract binary
                logger.warning(f"OCR failed for {raw_path}: {exc}")
                continue
            for text, conf in zip(data.get("text", []), data.get("conf", [])):
                try:
                    confidence = float(conf)
                except (TypeError, ValueError):
                    continue
                if confidence > 60 and text.strip():
                    words.append(text.strip())

        if not words:
            return None
        return UIContext(error_message=" ".join(words), ui_elements=words)

    # -- Stage 6 -----------------------------------------------------------

    def _scrub_text(self, text: str, state: _ScrubState) -> str:
        """Apply PII scrubbing: regex baseline then optional Presidio NER.

        Replaces sensitive patterns (emails, database URLs, IP addresses, etc.)
        with stable tokens (e.g., [REDACTED_EMAIL_1]). Optionally enhances
        detection with Presidio if available.

        Args:
            text: Text to scrub.
            state: Scrubbing state to maintain a stable token assignment.

        Returns:
            Scrubbed text with PII replaced by tokens.
        """
        if not text:
            return text

        def _make_replacer(label_: str) -> Callable[[re.Match[str]], str]:
            """
            Creates a function to replace matched patterns in a string with a tokenized value derived
            from the given label and the matched content.

            :param label_: The label that used to generate the tokenized value for the matched content.
            :return: A callable function that takes a regex match object and returns a string
                with the tokenized value based on the provided label and matched text.
            """

            def _replace(match: re.Match[str]) -> str:
                """
                Replaces a matched pattern with a token generated from a specific label.

                This function takes a matched string and replaces it with a token
                generated through the provided label and current state.

                :param match: A match object containing the details of the matched pattern in the input string.
                :type match: re.Match[str]
                :return: A string which is the token corresponding to the matched text.
                :rtype: str
                """
                return state.token_for(label_, match.group(0))
            return _replace

        for label, pattern in _PII_RULES:
            text = pattern.sub(_make_replacer(label), text)
        return self._presidio_enhance(text, state)

    @staticmethod
    def _presidio_enhance(text: str, state: _ScrubState) -> str:
        """Optional NER pass to catch entities the regex baseline misses"""
        try:
            analyzer = AnalyzerEngine()
            entities = ["PERSON", "PHONE_NUMBER", "US_SSN", "CRYPTO", "LOCATION"]
            results = analyzer.analyze(text=text, entities=entities, language="en")
            # Replace it from the end so earlier spans keep their offsets.
            for res in sorted(results, key=lambda r: r.start, reverse=True):
                value = text[res.start : res.end]
                token = state.token_for(res.entity_type, value)
                text = text[: res.start] + token + text[res.end :]
        except Exception as exc:  # pragma: no cover - depends on spaCy models
            logger.warning(f"Presidio enhancement failed; using regex baseline only: {exc}")
        return text

    # -- Stage 7 -----------------------------------------------------------

    def _enforce_assumption_limit(self, text: str) -> str:
        """Truncate a user assumption to the configured token limit.

        The user-provided context is often verbose; this method ensures it
        doesn't crowd out the incident data in downstream LLM processing.

        Args:
            text: User assumption text.

        Returns:
            Text truncated to the token limit (see :attr:`Settings.core.user_assumption_token_limit`).
        """
        limit = self._settings.core.user_assumption_token_limit
        truncated_text, was_truncated = truncate_to_tokens(text, limit)
        if was_truncated:
            logger.warning(
                f"User assumption exceeded {limit}-token cap; truncated."
            )
        return truncated_text

    # -- Stage 4 (LogBackend) ----------------------------------------------

    async def _query_log_backend(
        self,
        source: IncidentSource,
        log_backend: Optional[LogBackend],
    ) -> list[str]:
        """Pull windowed log lines from a LogBackend (fail to open on any error)"""
        if log_backend is None or source.incident_timestamp is None:
            return []
        service = source.metadata.get("service")
        if not service:
            return []
        window = timedelta(seconds=self._settings.core.log_window_seconds)
        try:
            return await log_backend.query_window(
                service=service,
                start_time=source.incident_timestamp - window,
                end_time=source.incident_timestamp + window,
            )
        except NotImplementedError:
            logger.warning(
                "LogBackend is a stub (e.g. fluent); falling back to file-based logs only."
            )
            return []
        except Exception as exc:  # pragma: no cover - backend-specific
            logger.warning(f"LogBackend query failed; using file logs only: {exc}")
            return []

    # -- Stage 8 -----------------------------------------------------------

    @staticmethod
    def _query_code_history(
        source: IncidentSource,
        code_backend: Optional[CodeBackend],
    ) -> list[CommitRecord]:
        """Retrieve recent commits from the source repository (before the incident).

        Queries a CodeBackend for commits in a 2-hour window before the incident.
        Gracefully returns an empty list if the backend is unavailable, repo_path
        is missing, or the query fails.

        Args:
            source: The incident source (contains repo_path in metadata and timestamp).
            code_backend: Optional backend to retrieve commit history. If None, returns [].

        Returns:
            List of :class:`CommitRecord` (up to 5), or empty list on failure.
        """
        if code_backend is None or source.incident_timestamp is None:
            return []
        repo_path = source.metadata.get("repo_path")
        if not repo_path:
            return []
        try:
            return code_backend.get_commits_before(
                repo_path=repo_path,
                before=source.incident_timestamp,
                window_hours=2,
                limit=5,
            )
        except Exception as exc:  # pragma: no cover - backend-specific
            logger.warning(f"Code history query failed: {exc}")
            return []

    # -- Stage 5.3 helper (used by Log Historian in Phase 5) ---------------

    @staticmethod
    def should_inject_history(
        brief: IncidentBrief,
        recent: list[IncidentBrief],
    ) -> bool:
        """Conditional history-injection rule (design spec §5.3)"""
        if not recent:
            return False
        module = brief.faulting_module
        fault = brief.fault_class
        module_hits = sum(1 for r in recent if module and r.faulting_module == module)
        fault_hits = sum(1 for r in recent if fault and r.fault_class == fault)
        return module_hits >= 2 or fault_hits >= 3
