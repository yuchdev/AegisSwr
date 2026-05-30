"""Abstract Base Class for storage backends."""
from abc import ABC, abstractmethod
import logging


class StorageBackendBase(ABC):
    """
    Base class for all persistence backends.
    """

    def __init__(self):
        """
        Initialize the storage backend.
        """
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def save(self, record: dict) -> bool:
        """
        Persist a crash analysis record.

        @param record: The crash analysis record to save.
        @return: True if the record was successfully persisted, False otherwise.
        """

    @abstractmethod
    def load_all(self) -> list:
        """
        Return all previously saved crash analysis records.

        @return: A list of crash analysis records.
        """

    @abstractmethod
    def find_report(self, dump_filename: str, ai_model: str) -> dict | None:
        """
        Check if a crash report for the given filename and AI model exists.

        @param dump_filename: Name of the .dmp file (without path).
        @param ai_model: Name of the AI model used for analysis.
        @return: The existing report as a dictionary, or None if not found.
        """
