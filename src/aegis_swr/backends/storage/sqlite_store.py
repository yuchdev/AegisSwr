"""SQLite storage backend.

Stores ``RCAReport`` objects as serialised JSON rows in a SQLite database.
Suitable for local development and single-host deployments without a full
database server.

Schema::

    reports (
        incident_id  TEXT  PRIMARY KEY,
        dump_hash    TEXT,
        created_at   TEXT  NOT NULL,
        mode         TEXT  NOT NULL,
        report_json  TEXT  NOT NULL
    )
"""
from __future__ import annotations
from typing import Optional

import asyncio
import json
import sqlite3
from pathlib import Path
from uuid import UUID

from loguru import logger

from aegis_swr.backends.base import RelationalStore
from aegis_swr.core.exceptions import IncidentNotFoundError
from aegis_swr.core.schemas import RCAReport
from aegis_swr.config.settings import StorageSettings

_CREATE = """
CREATE TABLE IF NOT EXISTS reports (
    incident_id TEXT PRIMARY KEY,
    dump_hash   TEXT,
    created_at  TEXT NOT NULL,
    mode        TEXT NOT NULL,
    report_json TEXT NOT NULL
)
"""

_CREATE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_dump_hash
    ON reports(dump_hash)
    WHERE dump_hash IS NOT NULL
"""

_UPSERT = """
INSERT OR REPLACE INTO reports (incident_id, dump_hash, created_at, mode, report_json)
VALUES (?, ?, ?, ?, ?)
"""


class SQLiteStore(RelationalStore):
    """SQLite-backed report store; no external services required"""

    def __init__(self, settings: StorageSettings):
        self._db_path = Path(settings.db_path).expanduser()
        self._init_db()

    def _init_db(self):
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db_path), timeout=30) as conn:
            conn.execute(_CREATE)
            conn.execute(_CREATE_INDEX)
        logger.debug(f"SQLiteStore: initialised DB at {self._db_path}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), timeout=30)

    # ------------------------------------------------------------------
    # RelationalStore
    # ------------------------------------------------------------------

    async def save_report(self, report: RCAReport):
        await asyncio.to_thread(self._sync_save, report)

    def _sync_save(self, report: RCAReport):
        row = (
            str(report.incident_id),
            report.dump_hash,
            report.created_at.isoformat(),
            report.mode.value,
            report.model_dump_json(),
        )
        with self._connect() as conn:
            conn.execute(_UPSERT, row)
        logger.debug(f"SQLiteStore: saved report {report.incident_id}")

    async def get_report(self, incident_id: UUID) -> Optional[RCAReport]:
        return await asyncio.to_thread(self._sync_get, str(incident_id))

    def _sync_get(self, incident_id: str) -> Optional[RCAReport]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM reports WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
        if row is None:
            return None
        return RCAReport.model_validate_json(row[0])

    async def find_by_hash(self, dump_hash: str) -> Optional[RCAReport]:
        return await asyncio.to_thread(self._sync_find_by_hash, dump_hash)

    def _sync_find_by_hash(self, dump_hash: str) -> Optional[RCAReport]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM reports WHERE dump_hash = ?",
                (dump_hash,),
            ).fetchone()
        if row is None:
            return None
        return RCAReport.model_validate_json(row[0])

    async def update_hitl_response(
        self,
        incident_id: UUID,
        response: dict[str, object],
    ):
        await asyncio.to_thread(self._sync_update_hitl, str(incident_id), response)

    def _sync_update_hitl(
        self,
        incident_id: str,
        response: dict[str, object],
    ):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_json FROM reports WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise IncidentNotFoundError(f"Report not found: {incident_id}")
            data = json.loads(row[0])
            data["hitl_request"] = response
            conn.execute(
                "UPDATE reports SET report_json = ? WHERE incident_id = ?",
                (json.dumps(data), incident_id),
            )

    async def load_recent(self, limit: int = 100) -> list[RCAReport]:
        return await asyncio.to_thread(self._sync_load_recent, limit)

    def _sync_load_recent(self, limit: int) -> list[RCAReport]:
        sql = "SELECT report_json FROM reports ORDER BY created_at DESC"
        if limit > 0:
            sql += f" LIMIT {limit}"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [RCAReport.model_validate_json(row[0]) for row in rows]
