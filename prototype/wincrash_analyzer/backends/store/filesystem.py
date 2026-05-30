"""JSON-based filesystem storage backend."""
from __future__ import annotations

import json
import os
import re
import datetime
import random
import string

from wincrash_analyzer.backends.store.base import StorageBackendBase
from wincrash_analyzer.core.exceptions import StorageBackendError

# Characters not allowed in file names on Windows or that confuse most OSes.
_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_filename(name: str) -> str:
    """
    Replace filesystem-unsafe characters with underscores.

    @param name: The filename to sanitize.
    @return: The sanitized filename string.
    """
    return _UNSAFE_CHARS.sub("_", name)


class FilesystemBackend(StorageBackendBase):
    """
    Persistence backend that stores records as JSON files.
    """

    def __init__(self, output_dir: str = "."):
        """
        Initialize the FilesystemBackend.

        @param output_dir: The directory where JSON reports will be stored.
        """
        super().__init__()
        self.output_dir = output_dir

    def save(self, record: dict) -> bool:
        """
        Write *record* to a JSON file inside :attr:`output_dir`.

        @param record: The crash analysis record to save.
        @return: True if the record was successfully saved.
        @raises StorageBackendError: If the file cannot be written.
        """
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Format: report-YYYYMMDD-HHMMSS.json
            now = datetime.datetime.now()
            timestamp_str = now.strftime("%Y%m%d-%H%M%S")
            base_filename = f"report-{timestamp_str}"
            filename = f"{base_filename}.json"
            filepath = os.path.join(self.output_dir, filename)

            # Handling Collisions: If file exists, append a short random suffix
            if os.path.exists(filepath):
                suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                filename = f"{base_filename}-{suffix}.json"
                filepath = os.path.join(self.output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(record, fh, indent=4)
            self.logger.info("Saved crash report to %s", filepath)
            return True
        except OSError as exc:
            raise StorageBackendError(f"File write failed: {exc}") from exc

    def load_all(self) -> list:
        """
        Return all crash records stored in :attr:`output_dir`.

        @return: A list of crash analysis records.
        @raises StorageBackendError: If the directory cannot be read.
        """
        try:
            records = []
            if not os.path.isdir(self.output_dir):
                return records
            for entry in os.listdir(self.output_dir):
                if entry.endswith(".json"):
                    filepath = os.path.join(self.output_dir, entry)
                    try:
                        with open(filepath, encoding="utf-8") as fh:
                            records.append(json.load(fh))
                    except (json.JSONDecodeError, OSError) as exc:
                        self.logger.warning("Skipping %s: %s", filepath, exc)
            return records
        except OSError as exc:
            raise StorageBackendError(f"Directory read failed: {exc}") from exc

    def find_report(self, dump_filename: str, ai_model: str) -> dict | None:
        """
        Find a report for the given filename and AI model in the output directory.

        @param dump_filename: Name of the .dmp file (without path).
        @param ai_model: Name of the AI model used for analysis.
        @return: The existing report as a dictionary, or None if not found.
        """
        try:
            if not os.path.isdir(self.output_dir):
                return None
            for entry in os.listdir(self.output_dir):
                if entry.endswith(".json"):
                    filepath = os.path.join(self.output_dir, entry)
                    try:
                        with open(filepath, encoding="utf-8") as fh:
                            record = json.load(fh)
                            # Filename only comparison
                            existing_filename = os.path.basename(record.get("dump_path", ""))
                            if existing_filename == dump_filename and record.get("ai_model") == ai_model:
                                return record
                    except (json.JSONDecodeError, OSError):
                        continue
            return None
        except OSError as exc:
            self.logger.error("Failed to search reports in %s: %s", self.output_dir, exc)
            return None
