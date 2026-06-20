"""SQLite-based storage backend"""
from __future__ import annotations

import json
import os
import sqlite3

from wincrash_analyzer.backends.store.base import StorageBackendBase
from wincrash_analyzer.core.exceptions import StorageBackendError

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS crash_reports (
    report_id     TEXT PRIMARY KEY,
    timestamp     TEXT,
    dump_path     TEXT,
    report_json   TEXT
);
"""

_INSERT = """
INSERT OR REPLACE INTO crash_reports (report_id, timestamp, dump_path, report_json)
VALUES (?, ?, ?, ?)
"""

_SELECT_ALL = """
SELECT report_json FROM crash_reports
"""

# Maximum report_json characters stored to avoid excessive DB size (legacy safety).
_MAX_JSON_LEN = 1_000_000


class SQLiteBackend(StorageBackendBase):
    """
    Persistence backend that stores records in a SQLite database.
    """

    def __init__(self, db_path: str = "crash_reports.db"):
        """
        Initialize the SQLiteBackend.

        @param db_path: Path to the SQLite database file.
        """
        super().__init__()
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _init_db(self):
        """
        Initialize the database schema if it doesn't already exist.
        """
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            conn.execute(_CREATE_TABLE)

    # ------------------------------------------------------------------
    # StorageBackendBase interface
    # ------------------------------------------------------------------

    def save(self, record: dict) -> bool:
        """
        Insert *record* into the ``crash_reports`` table.

        @param record: The crash analysis record to save.
        @return: True if the record was successfully saved.
        @raises StorageBackendError: If the database write fails.
        """
        try:
            report_json = json.dumps(record)

            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute(
                    _INSERT,
                    (
                        record.get("report_id", ""),
                        record.get("timestamp", ""),
                        record.get("dump_path", ""),
                        report_json,
                    ),
                )
            self.logger.info("Saved crash report id=%s", record.get("report_id"))
            return True
        except sqlite3.Error as exc:
            raise StorageBackendError(f"Database write failed: {exc}") from exc

    def load_all(self) -> list:
        """
        Return all rows from ``crash_reports`` as dictionaries.

        @return: A list of crash analysis records.
        @raises StorageBackendError: If the database cannot be read.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                rows = conn.execute(_SELECT_ALL).fetchall()
            return [json.loads(row[0]) for row in rows]
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            raise StorageBackendError(f"Database read failed: {exc}") from exc

    def find_report(self, dump_filename: str, ai_model: str) -> dict | None:
        """
        Find a report for the given filename and AI model using SQL.

        @param dump_filename: Name of the .dmp file (without path).
        @param ai_model: Name of the AI model used for analysis.
        @return: The existing report as a dictionary, or None if not found.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                # SQLite doesn't have os.path.basename, so we use LIKE for path suffix and search model in JSON
                # Or we can iterate if we want more accuracy, but let's try SQL search first
                # The request says: SQLite can use SQL for requests
                
                # Check dump_path ends with filename (handling both / and \ separator)
                # and then check AI model match.
                # We use REPLACE to normalize separators for the LIKE check if needed, 
                # but simplest is to check for %/filename and %\filename
                cursor = conn.execute(
                    "SELECT report_json FROM crash_reports WHERE (dump_path = ? OR dump_path LIKE ? OR dump_path LIKE ?) AND report_json LIKE ?",
                    (
                        dump_filename,
                        f"%\\{dump_filename}",
                        f"%/{dump_filename}",
                        f'%"ai_model": "{ai_model}"%'
                    )
                )
                rows = cursor.fetchall()
                for (report_json,) in rows:
                    record = json.loads(report_json)
                    if os.path.basename(record.get("dump_path", "")) == dump_filename and record.get("ai_model") == ai_model:
                        return record
            return None
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            self.logger.error("Database search failed: %s", exc)
            return None
