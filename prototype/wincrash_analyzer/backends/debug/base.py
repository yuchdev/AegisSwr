"""Abstract Base Class for debugger backends."""
from abc import ABC, abstractmethod


class DebugBackendBase(ABC):
    """
    Base class for all debugger extraction backends.
    """

    @property
    @abstractmethod
    def engine_type(self) -> str:
        """
        Identifier for the debug engine (e.g., 'cdb', 'js').

        @return: The engine type string.
        """

    @abstractmethod
    def extract(self, dump_path: str, symbol_path: str) -> dict:
        """
        Extract a stack trace from the given dump file.

        @param dump_path: Absolute path to the .dmp file.
        @param symbol_path: Path to the symbol files.
        @return: A dictionary containing at least a 'raw' key with the extracted trace.
        """
