"""Data source abstractions for WinCrash Analyzer"""
from __future__ import annotations

from abc import ABC, abstractmethod
import os


class DataSource(ABC):
    """
    Abstract base class for all crash analysis data sources.
    """

    def __init__(self, path: str):
        self.path = path

    @property
    @abstractmethod
    def source_type(self) -> str:
        """
        Identifier for the source type (e.g., 'dump', 'symbols', 'logs').

        @return: The source type string.
        """

    def exists(self) -> bool:
        """
        Check if the data source exists on disk.

        @return: True if the path exists, False otherwise.
        """
        return os.path.exists(self.path)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(path='{self.path}')"


class DumpSource(DataSource):
    """
    Represents a crash dump file (.dmp).
    """

    @property
    def source_type(self) -> str:
        return "dump"


class SymbolSource(DataSource):
    """
    Represents a symbol search path or directory containing PDB files.
    """

    @property
    def source_type(self) -> str:
        return "symbols"


class LogSource(DataSource):
    """
    Represents a log file or a directory containing application logs.
    """

    @property
    def source_type(self) -> str:
        return "logs"

    def read_logs(self, crash_timestamp: str | None = None) -> str:
        """
        Read logs from the source path, optionally filtering by crash timestamp.

        @param crash_timestamp: The ISO-8601 or string timestamp of the crash event.
        @return: The combined content of the logs.
        """
        if not self.exists():
            return f"Log source not found: {self.path}"

        logs = []
        if crash_timestamp:
            logs.append(f"CRASH TIMESTAMP: {crash_timestamp}")
            logs.append("--- Correlation window: +/- 1 minute around the crash ---")

        if os.path.isfile(self.path):
            files = [self.path]
        elif os.path.isdir(self.path):
            files = [
                os.path.join(self.path, f)
                for f in os.listdir(self.path)
                if os.path.isfile(os.path.join(self.path, f))
            ]
        else:
            return f"Log source path is invalid: {self.path}"

        for file in files:
            try:
                with open(file, "r", encoding="utf-8", errors="replace") as f:
                    # For now, read the last 100 lines.
                    # Future implementation could filter based on crash_timestamp.
                    lines = f.readlines()
                    logs.append(
                        f"\n--- File: {os.path.basename(file)} ---\n" + "".join(lines[-100:])
                    )
            except Exception as e:
                logs.append(f"\nCould not read log file {file}: {e}")

        return "\n".join(logs)


class SourceCollection:
    """
    A collection of data sources to be analyzed together.
    """

    def __init__(self, dump: DumpSource | None = None, symbols: SymbolSource | None = None, logs: LogSource | None = None):
        self.dump = dump
        self.symbols = symbols
        self.logs = logs

    def get_all(self) -> list[DataSource]:
        """
        Return all provided and existing data sources.

        @return: A list of DataSource objects.
        """
        sources = []
        if self.dump and self.dump.exists():
            sources.append(self.dump)
        if self.symbols and self.symbols.exists():
            sources.append(self.symbols)
        if self.logs and self.logs.exists():
            sources.append(self.logs)
        return sources

    def __repr__(self) -> str:
        return f"SourceCollection(dump={self.dump}, symbols={self.symbols}, logs={self.logs})"
