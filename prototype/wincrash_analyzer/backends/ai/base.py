"""Abstract Base Class for AI backends."""
from abc import ABC, abstractmethod
import logging
import os


class AIBackendBase(ABC):
    """
    Base class for all AI reasoning backends.
    """

    def __init__(self):
        """
        Initialize the AI backend.
        """
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def model_name(self) -> str:
        """
        Identifier for the AI model used.

        @return: The model name string.
        """

    def get_api_key(self, env_var_name: str) -> "str | None":
        """
        Retrieve an API key from the environment with a stub for Vault/KMS.

        @param env_var_name: The name of the environment variable.
        @return: The API key if found, None otherwise.
        """
        key = os.getenv(env_var_name)
        if not key:
            self.logger.error("Missing API key: %s", env_var_name)
        return key

    @abstractmethod
    def analyze(self, crash_data: str, history: list[dict] | None = None, assumption: str | None = None) -> str:
        """
        Analyze a crash and return a diagnosis.

        @param crash_data: The raw or sanitized crash data (stack trace, logs).
        @param history: Optional list of historical crash records for context.
        @param assumption: Optional user-provided assumption or context.
        @return: The AI-generated analysis string.
        """
