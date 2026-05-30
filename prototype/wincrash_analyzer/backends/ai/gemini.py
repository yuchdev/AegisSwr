"""Gemini-specific AI backend implementation."""
import google.generativeai as genai

from wincrash_analyzer.backends.ai.base import AIBackendBase
from wincrash_analyzer.core.exceptions import AIBackendError

_SYSTEM_INSTRUCTION = (
    "You are an expert Windows Kernel debugger. "
    "Analyze the provided stack trace. "
    "Identify the specific function and offset where the fault occurred. "
    "Explain the Exception Code (e.g., 0xc0000005 as Null Pointer or Use-After-Free)."
)

_SAFETY_SETTINGS = {
    "HATE": "BLOCK_NONE",
    "HARASSMENT": "BLOCK_NONE",
    "SEXUAL": "BLOCK_NONE",
    "DANGEROUS": "BLOCK_NONE",
}


class GeminiBackend(AIBackendBase):
    """
    AI backend that uses Google Gemini 1.5 Pro.
    """

    @property
    def model_name(self) -> str:
        """
        Identifier for the AI model used.

        @return: The model name string "gemini-1.5-pro".
        """
        return "gemini-1.5-pro"

    def analyze(self, crash_data: str, history: list[dict] | None = None, assumption: str | None = None) -> str:
        """
        Analyze crash data using Gemini and return a diagnosis.

        @param crash_data: The raw or sanitized crash data string.
        @param history: Optional list of historical crash records for context.
        @param assumption: Optional user-provided assumption or context.
        @return: The AI-generated analysis string.
        @raises AIBackendError: If the Gemini API key is missing or the API call fails.
        """
        key = self.get_api_key("GEMINI_API_KEY")
        if not key:
            raise AIBackendError("Gemini Key Missing")

        genai.configure(api_key=key)
        model = genai.GenerativeModel(
            "gemini-1.5-pro",
            system_instruction=_SYSTEM_INSTRUCTION,
        )

        user_content = f"Analyze this crash dump and provide a Root Cause Analysis:\n\n{crash_data}"
        if assumption:
            user_content += f"\n\nAdditional User Context/Assumption:\n{assumption}"

        if history:
            history_summary = self._format_history(history)
            user_content = (
                f"History of previous crashes for context:\n{history_summary}\n\n"
                f"Compare the current crash with the history and provide a final diagnosis:\n\n{crash_data}"
            )
            if assumption:
                user_content += f"\n\nAdditional User Context/Assumption:\n{assumption}"

        try:
            response = model.generate_content(
                user_content,
                safety_settings=_SAFETY_SETTINGS,
            )
            return response.text
        except Exception as exc:
            raise AIBackendError(f"Gemini API Failure: {exc}") from exc

    def _format_history(self, history: list[dict]) -> str:
        """
        Format history records for inclusion in the AI prompt.

        @param history: List of historical crash records.
        @return: A formatted string summarizing the crash history.
        """
        formatted = []
        # Sort by timestamp, newest first, and limit to top 5
        sorted_history = sorted(
            history,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:5]

        for record in sorted_history:
            entry = (
                f"- [{record.get('timestamp')}] "
                f"Module: {record.get('faulting_module', 'Unknown')}, "
                f"Code: {record.get('exception_code', 'Unknown')}\n"
                f"  Analysis: {record.get('ai_analysis', 'N/A')[:200]}..."
            )
            formatted.append(entry)
        return "\n".join(formatted)
