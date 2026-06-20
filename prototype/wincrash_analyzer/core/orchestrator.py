"""Orchestrator: pipeline business logic for WinCrash Analyzer"""
from __future__ import annotations

import logging
import re
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wincrash_analyzer.core.data_sources import SourceCollection

from wincrash_analyzer.core.exceptions import (
    AIBackendError,
    DebuggerError,
    StorageBackendError,
)

logger = logging.getLogger(__name__)

# Regex that matches common uninformative fill patterns (e.g. 0xCCCCCCCC).
_FILL_PATTERN = re.compile(r"\b0x[cC]{8}\b")


class Orchestrator:
    """
    Coordinates the debug, AI, and storage pipeline.
    """

    def __init__(self, debug_backend, ai_backend, storage_backend):
        """
        Initialize the Orchestrator.

        @param debug_backend: The debug engine backend to use.
        @param ai_backend: The AI analysis backend to use.
        @param storage_backend: The storage backend to use for results.
        """
        self.debug_backend = debug_backend
        self.ai_backend = ai_backend
        self.storage_backend = storage_backend

    def run(self, sources: SourceCollection, analyze_history: bool = False, assumption: str = None) -> str:
        """
        Execute the full analysis pipeline and return the diagnosis.

        @param sources: A collection of data sources (dump, symbols, logs).
        @param analyze_history: Whether to include historical crash data in the analysis.
        @param assumption: Additional context provided by the user.
        @return: The AI-generated diagnosis string.
        """
        import os
        dump_path = sources.dump.path if sources.dump else None
        symbol_path = sources.symbols.path if sources.symbols else ""
        
        if not dump_path:
             logger.error("No dump file provided for analysis.")
             return "Error: No dump file provided."

        dump_filename = os.path.basename(dump_path)
        existing = self.storage_backend.find_report(dump_filename, self.ai_backend.model_name)
        if existing:
            logger.info("A report for %s using %s already exists. Skipping AI analysis.", dump_filename, self.ai_backend.model_name)
            return existing.get("ai_analysis", "No AI analysis in existing report.")

        raw_report = self.debug_backend.extract(dump_path, symbol_path)
        stack_trace = raw_report["raw"]

        # Unified context: add logs if available (assumptions passed separately)
        unified_context = f"STACK TRACE:\n{stack_trace}\n\n"
        
        if sources.logs and sources.logs.exists():
            log_content = sources.logs.read_logs(raw_report.get("timestamp"))
            unified_context += f"APPLICATION LOGS:\n{log_content}\n"

        history = None
        if analyze_history:
            try:
                history = self.storage_backend.load_all()
            except Exception as exc:
                logger.warning("Failed to load history for analysis: %s", exc)

        diagnosis = self.ai_backend.analyze(unified_context, history=history, assumption=assumption)
        
        from wincrash_analyzer.core.data_schema import make_report_id, make_timestamp
        import os
        import hashlib

        abs_dump_path = os.path.abspath(dump_path)
        dump_size = None
        dump_hash = None
        try:
            if os.path.exists(abs_dump_path):
                dump_size = os.path.getsize(abs_dump_path)
                sha256 = hashlib.sha256()
                with open(abs_dump_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        sha256.update(chunk)
                dump_hash = sha256.hexdigest()
        except Exception as e:
            logger.warning("Failed to get dump file metadata: %s", e)

        record = {
            "report_id": make_report_id(),
            "timestamp": make_timestamp(),
            "dump_path": abs_dump_path,
            "exception_code": raw_report.get("exception_code", ""),
            "faulting_module": raw_report.get("faulting_module", ""),
            "raw_stack": stack_trace.splitlines(),
            "ai_analysis": diagnosis,
            "engine_type": self.debug_backend.engine_type,
            "ai_model": self.ai_backend.model_name,
            "dump_size": dump_size,
            "dump_hash": dump_hash,
        }
        if "execution_log" in raw_report:
            record["execution_log"] = []
            for entry in raw_report["execution_log"]:
                new_entry = entry.copy()
                if "output" in new_entry and isinstance(new_entry["output"], str):
                    new_entry["output"] = new_entry["output"].splitlines()
                record["execution_log"].append(new_entry)
        if "raw_stdout" in raw_report:
            record["raw_stdout"] = raw_report["raw_stdout"].splitlines()
            
        self.storage_backend.save(record)
        return diagnosis

class CrashOrchestrator:
    """State-machine orchestrator for the full crash-analysis transaction.

    States: IDLE → EXTRACTING → ANALYZING → STORING → COMPLETED

    Graceful degradation: if the AI stage fails the raw extraction data is
    still persisted to the store so no work is lost.
    """

    def __init__(self, debugger, ai, store):
        """
        Initialize the CrashOrchestrator.

        @param debugger: The debug engine instance.
        @param ai: The AI analysis backend instance.
        @param store: The storage backend instance.
        """
        self.debugger = debugger
        self.ai = ai
        self.store = store
        self.state = "IDLE"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, sources: SourceCollection, analyze_history: bool = False, assumption: str = None) -> str:
        """
        Run the full analysis pipeline and return the AI diagnosis.

        @param sources: A collection of data sources (dump, symbols, logs).
        @param analyze_history: Whether to include historical crash data in the analysis.
        @param assumption: Additional context provided by the user.
        @return: The Markdown-formatted AI diagnosis string, or "AI Analysis Unavailable" if the AI stage fails.
        @raises DebuggerError: If the debug-extraction stage fails.
        @raises AIBackendError: If the AI stage fails (raw data is persisted first).
        @raises StorageBackendError: If persistence fails.
        """
        import os
        dump_path = sources.dump.path if sources.dump else None
        sym_path = sources.symbols.path if sources.symbols else ""
        
        if not dump_path:
             logger.error("No dump file provided for analysis.")
             return "Error: No dump file provided."

        dump_filename = os.path.basename(dump_path)
        raw_report: dict | None = None

        try:
            self._update_state("EXTRACTING")
            logger.info("Step 1: Extracting crash data from %s", dump_path)
            raw_report = self.debugger.extract(dump_path, sym_path)
            raw_data = raw_report["raw"]
            logger.info("Successfully extracted stack trace (Size: %d chars)", len(raw_data))

            self._update_state("ANALYZING")
            logger.info("Step 2: Analyzing crash data with AI")
            sanitized = self._sanitize(raw_data)

            # Unified context: add logs if available (assumptions passed separately)
            unified_context = f"STACK TRACE:\n{sanitized}\n\n"
            
            if sources.logs and sources.logs.exists():
                log_content = sources.logs.read_logs(raw_report.get("timestamp"))
                unified_context += f"APPLICATION LOGS:\n{log_content}\n"

            history = None
            if analyze_history:
                try:
                    history = self.store.load_all()
                except Exception as exc:
                    logger.warning("Failed to load history for analysis: %s", exc)

            analysis = self.ai.analyze(unified_context, history=history, assumption=assumption)
            logger.info("AI Analysis completed")

            self._update_state("STORING")
            logger.info("Step 3: Persisting results")
            self._safe_persist(dump_path, raw_report, analysis)

            self._update_state("COMPLETED")
            return analysis

        except DebuggerError:
            logger.error("Debugger stage failed for %s", dump_path)
            raise

        except AIBackendError:
            logger.warning(
                "AI stage failed for %s – persisting raw data only.", dump_path
            )
            if raw_report is not None:
                self._safe_persist(dump_path, raw_report, "AI Analysis Unavailable")
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_state(self, state: str):
        """
        Update the internal state of the orchestrator and log the change.

        @param state: The new state string.
        """
        self.state = state
        logger.info("CrashOrchestrator state: %s", state)

    def _sanitize(self, raw_data: str) -> str:
        """
        Strip uninformative fill patterns to reduce AI token usage.
        Replaces patterns such as ``0xCCCCCCCC`` with a single space.

        @param raw_data: The raw stack trace string.
        @return: The sanitized stack trace string.
        """
        return _FILL_PATTERN.sub(" ", raw_data)

    def _safe_persist(self, dump_path: str, raw_report: dict, analysis: str):
        """
        Persist a crash record, converting OSError to StorageBackendError.

        @param dump_path: Path to the source .dmp file.
        @param raw_report: The raw report dictionary from the debug engine.
        @param analysis: The AI analysis result string.
        @raises StorageBackendError: If an OSError occurs during persistence.
        """
        try:
            from wincrash_analyzer.core.data_schema import make_report_id, make_timestamp
            import os
            import hashlib
            
            abs_dump_path = os.path.abspath(dump_path)
            dump_size = None
            dump_hash = None
            try:
                if os.path.exists(abs_dump_path):
                    dump_size = os.path.getsize(abs_dump_path)
                    sha256 = hashlib.sha256()
                    with open(abs_dump_path, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            sha256.update(chunk)
                    dump_hash = sha256.hexdigest()
            except Exception as e:
                logger.warning("Failed to get dump file metadata: %s", e)

            record = {
                "report_id": make_report_id(),
                "timestamp": make_timestamp(),
                "dump_path": abs_dump_path,
                "exception_code": raw_report.get("exception_code", ""),
                "faulting_module": raw_report.get("faulting_module", ""),
                "raw_stack": raw_report.get("raw", "").splitlines(),
                "ai_analysis": analysis,
                "engine_type": self.debugger.engine_type,
                "ai_model": self.ai.model_name,
                "dump_size": dump_size,
                "dump_hash": dump_hash,
            }
            
            if "execution_log" in raw_report:
                record["execution_log"] = []
                for entry in raw_report["execution_log"]:
                    new_entry = entry.copy()
                    if "output" in new_entry and isinstance(new_entry["output"], str):
                        new_entry["output"] = new_entry["output"].splitlines()
                    record["execution_log"].append(new_entry)
            if "raw_stdout" in raw_report:
                record["raw_stdout"] = raw_report["raw_stdout"].splitlines()

            self.store.save(record)
        except OSError as exc:
            raise StorageBackendError(str(exc)) from exc
