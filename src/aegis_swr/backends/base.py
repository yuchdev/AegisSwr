from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, ClassVar, Optional
from uuid import UUID

from pydantic import BaseModel

from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    BlameRecord,
    CommitRecord,
    DebugExtractionResult,
    DumpFormat,
    IncidentSource,
    RCAReport,
)


class AIAPIBackend(ABC):
    """Manages LLM communication, token streaming, and structured output"""

    model_name: str

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]] = None,
    ) -> BaseModel | str:
        """Send a completion request.

        Returns a validated Pydantic instance when output_schema is provided,
        otherwise returns the raw response string. Raises AIOutputValidationError
        if the schema cannot be satisfied after one retry.
        System prompt is always sent with provider-level prompt caching enabled.
        """

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """Return an async generator yielding token-by-token text deltas"""


class DebugBackend(ABC):
    """Wraps native debugger binaries to extract structured crash data"""

    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]]
    SUPPORTED_PLATFORMS: ClassVar[list[str]]

    @abstractmethod
    def extract(
        self,
        source: IncidentSource,
        symbol_path: list[str],
    ) -> DebugExtractionResult:
        """Open the dump/core file using the native debugger and extract structured fields.

        Maps all platform-native fault codes to FaultClass. Runs the debugger subprocess
        in a RAII context (always terminates on exception). Timeout is enforced by config.
        Each entry in *symbol_path* is appended as a bare directory to the debugger's
        symbol search chain (semicolon-separated after the SRV* cache entry).
        """

    @abstractmethod
    def _build_command_sequence(
        self,
        source: IncidentSource,
        symbol_path: Optional[str],
    ) -> list[str]:
        """Return the debugger argv list for subprocess.run()"""


class RelationalStore(ABC):
    """Persists structured incident data, dialogue logs, and RCA reports"""

    @abstractmethod
    async def save_report(self, report: RCAReport):
        """Insert or update a completed RCA report"""

    @abstractmethod
    async def get_report(self, incident_id: UUID) -> Optional[RCAReport]:
        """Retrieve a completed RCA report by incident ID"""

    @abstractmethod
    async def find_by_hash(self, dump_hash: str) -> Optional[RCAReport]:
        """Return the most recent report for the given content hash, or None.

        This is the primary deduplication gate - called before any analysis begins.
        """

    @abstractmethod
    async def update_hitl_response(
        self,
        incident_id: UUID,
        response: dict[str, Any],
    ):
        """Attach user-supplied HITL data to a pending investigation"""

    @abstractmethod
    async def load_recent(self, limit: int = 100) -> list[RCAReport]:
        """Return up to *limit* reports ordered by created_at descending.

        ``limit=0`` means return all reports.  Used by ``aegis export``.
        """


class ObjectStore(ABC):
    """Stores raw incident artifacts: dump files, logs, screenshots"""

    @abstractmethod
    async def upload_raw(
        self,
        incident_id: UUID,
        filename: str,
        data: bytes,
    ) -> str:
        """Upload a raw artifact and return the object key"""

    @abstractmethod
    async def get_raw(self, object_key: str) -> bytes:
        """Download a raw artifact by object key"""


class VectorStore(ABC):
    """Stores and searches semantic embeddings of resolved incidents"""

    @abstractmethod
    async def upsert_incident(self, report: RCAReport):
        """Embed the report summary and upsert into the vector collection"""

    @abstractmethod
    async def search_similar(
        self,
        fault_class: FaultClass,
        faulting_module: Optional[str],
        top_k: int = 5,
    ) -> list[RCAReport]:
        """Return the top-k most similar historical incidents"""


class LogBackend(ABC):
    """Fetches log lines from centralized observability sources"""

    @abstractmethod
    async def query_window(
        self,
        service: str,
        start_time: datetime,
        end_time: datetime,
        severity_levels: Optional[list[str]] = None,
    ) -> list[str]:
        """Return filtered log lines from the configured source within the time window"""


class CodeBackend(ABC):
    """Reads commit history and diffs from version control systems"""

    @abstractmethod
    def get_commits_before(
        self,
        repo_path: str,
        before: datetime,
        window_hours: int = 2,
        limit: int = 10,
    ) -> list[CommitRecord]:
        """Return commits in the window immediately before the given timestamp"""

    @abstractmethod
    def get_file_diff(
        self,
        repo_path: str,
        file_path: str,
        commit_sha: str,
    ) -> str:
        """Return the unified diff for a specific file at a specific commit"""

    @abstractmethod
    def blame(
        self,
        repo_path: str,
        file_path: str,
        line_range: tuple[int, int],
    ) -> list[BlameRecord]:
        """Return blame records for the given line range"""
