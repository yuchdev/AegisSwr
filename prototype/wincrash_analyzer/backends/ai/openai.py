"""OpenAI-specific AI backend implementation."""
from openai import OpenAI

from wincrash_analyzer.backends.ai.base import AIBackendBase
from wincrash_analyzer.core.exceptions import AIBackendError

_TRUNCATE_THRESHOLD = 10_000
_KEEP_HEAD = 5_000
_KEEP_TAIL = 5_000

_SYSTEM_MESSAGE = (
    "You are a senior Windows systems engineer. "
    "Provide a structured analysis with the following sections: "
    "Root Cause Analysis (RCA), Faulting Module, and Recommendation."
)


class OpenAIBackend(AIBackendBase):
    """
    AI backend that uses OpenAI gpt-5.4.
    """

    @property
    def model_name(self) -> str:
        """
        Identifier for the AI model used.

        @return: The model name string "gpt-5.4".
        """
        return "gpt-5.4"

    def analyze(self, crash_data: str, history: list[dict] | None = None, assumption: str | None = None) -> str:
        """
        Analyze crash data using gpt-5.4 and return a diagnosis.

        @param crash_data: The raw or sanitized crash data string (e.g., stack trace).
        @param history: Optional list of historical crash records for context.
        @param assumption: Optional user-provided assumption or context.
        @return: The AI-generated analysis string.
        @raises AIBackendError: If the OpenAI API key is missing or the API call fails.
        """
        key = self.get_api_key("OPENAI_API_KEY")
        if not key:
            raise AIBackendError("OpenAI Key Missing")

        import httpx
        try:
            # Modern httpx uses 'proxy' instead of 'proxies'. 
            # If proxies are set in the environment, we let httpx handle it or pass it explicitly.
            # OpenAI's SyncHttpxClientWrapper might still be using the old 'proxies' kwarg,
            # which is what caused the TypeError in httpx 0.28+.
            client = OpenAI(api_key=key, http_client=httpx.Client())
        except TypeError:
            # Fallback if the above doesn't work for some reason (older OpenAI/httpx)
            client = OpenAI(api_key=key)
        sanitized = self._smart_truncate(crash_data)

        user_content = f"Analyze this crash context:\n\n{sanitized}"
        if assumption:
            user_content += f"\n\nUser Assumption:\n{assumption}"

        if history:
            history_summary = self._format_history(history)
            user_content = (
                f"History of previous crashes:\n{history_summary}\n\n"
                f"Now, analyze this new crash context and compare it with the history:\n\n{sanitized}"
            )
            if assumption:
                user_content += f"\n\nUser Assumption:\n{assumption}"

        try:
            response = client.chat.completions.create(
                model="gpt-5.4",
                messages=[
                    {"role": "system", "content": _SYSTEM_MESSAGE},
                    {"role": "user", "content": user_content},
                ],
                timeout=60.0,
            )
            return response.choices[0].message.content
        except Exception as exc:
            raise AIBackendError(f"OpenAI API Failure: {exc}") from exc

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

    def _smart_truncate(self, crash_data: str) -> str:
        """
        Trim the middle of a long crash dump to stay within token limits.

        If *crash_data* exceeds ``_TRUNCATE_THRESHOLD`` characters, the method
        keeps the first ``_KEEP_HEAD`` characters (exception context) and the
        last ``_KEEP_TAIL`` characters (stack frames), discarding the middle
        noise (symbol-search logs, etc.).

        @param crash_data: The full crash data string.
        @return: The truncated crash data string.
        """
        if len(crash_data) <= _TRUNCATE_THRESHOLD:
            return crash_data
        head = crash_data[:_KEEP_HEAD]
        tail = crash_data[-_KEEP_TAIL:]
        return head + "\n[... middle section truncated ...]\n" + tail
