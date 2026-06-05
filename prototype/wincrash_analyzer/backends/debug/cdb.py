"""Python/subprocess CDB debugger backend"""
import logging
import os
import re
import subprocess

from wincrash_analyzer.backends.debug.base import DebugBackendBase
from wincrash_analyzer.core.exceptions import DebuggerEngineError, DebuggerNotFoundError

logger = logging.getLogger(__name__)


class CDBBackend(DebugBackendBase):
    """
    Debugger backend that drives cdb.exe via subprocess.
    """
    @property
    def engine_type(self) -> str:
        """
        Identifier for the debug engine.

        @return: The engine type string "cdb".
        """
        return "cdb"

    def __init__(self, cdb_path: str = "cdb.exe"):
        """
        Initialize the CDB backend.

        @param cdb_path: Path to the cdb.exe binary.
        """
        self.cdb_path = cdb_path

    _TIMEOUT = 300  # 5-minute watchdog
    _FALLBACK_CHAR_LIMIT = 10000
    _DEFAULT_SYMBOL_CACHE = r"c:\symbols"

    def extract(self, dump_path: str, symbol_path: str) -> dict:
        """
        Extract a stack trace from the given dump file using cdb.exe.

        @param dump_path: Absolute path to the .dmp file.
        @param symbol_path: Path to the symbol files.
        @return: A dictionary containing 'raw', 'exception_code', and 'faulting_module'.
        @raises DebuggerEngineError: If an error occurs during extraction.
        @raises DebuggerNotFoundError: If cdb.exe cannot be found.
        """
        if not os.access(dump_path, os.R_OK):
            raise DebuggerEngineError(f"Dump file is not readable: {dump_path}")

        symbol_cache = os.environ.get("WINCRASH_SYMBOL_CACHE", self._DEFAULT_SYMBOL_CACHE)

        # .reload /f /i forces symbol loading while ignoring build ID mismatches
        sympath = f'srv*{symbol_cache}*https://msdl.microsoft.com/download/symbols'
        if symbol_path:
            sympath = f'{symbol_path};{sympath}'

        dbg_cmds = (
            f'.sympath "{sympath}";'
            f'.reload /f /i;'
            f'!analyze -v;'
            f'q'
        )

        logger.debug("CDB commands: %s", dbg_cmds)
        logger.info("Spawning CDB for dump: %s", dump_path)

        try:
            result = subprocess.run(
                [self.cdb_path, "-z", dump_path, "-c", dbg_cmds],
                capture_output=True,
                text=True,
                timeout=self._TIMEOUT,
            )

            if result.returncode != 0:
                logger.error("CDB exited with error code %d", result.returncode)

            parsed = self._parse_raw_output(result.stdout)
            report_data = {"raw": parsed}

            # Extract metadata from raw output
            report_data["exception_code"] = self._extract_exception_code(result.stdout)
            report_data["faulting_module"] = self._extract_faulting_module(result.stdout)
            report_data["timestamp"] = self._extract_timestamp(result.stdout)

            if logger.isEnabledFor(logging.DEBUG):
                report_data["execution_log"] = [{"cmd": dbg_cmds, "output": result.stdout}]
                report_data["raw_stdout"] = result.stdout

            return report_data

        except subprocess.TimeoutExpired:
            raise DebuggerEngineError("CDB timed out during symbol resolution.")
        except PermissionError as e:
            raise DebuggerEngineError(
                f"Access Denied when running '{self.cdb_path}': {e}\n"
                "This typically occurs with WinDbg Preview from Microsoft Store.\n"
                "Please install 'Debugging Tools for Windows' from the Windows SDK "
                "and ensure its path is first in your PATH or provided via --cdb-path."
            )
        except FileNotFoundError:
            raise DebuggerNotFoundError(f"'{self.cdb_path}' not found.")

    def _parse_raw_output(self, raw_text: str) -> str:
        """
        Extract the high-value sections for AI ingestion from the raw CDB output.

        @param raw_text: The full output from cdb.exe.
        @return: A sanitized and focused stack trace string.
        """
        match = re.search(
            r"(Exception Analysis.*?)(?=^0:000>|quit:)",
            raw_text,
            re.DOTALL | re.IGNORECASE | re.MULTILINE,
        )

        if match:
            content = match.group(1)
            # Remove repetitive "file not found" lines to save 20-40% of token space
            content = re.sub(r"DBGHELP:.*?file not found\n", "", content)
            return content

        return raw_text[: self._FALLBACK_CHAR_LIMIT]  # Fallback to first 10k chars

    def _extract_exception_code(self, raw_text: str) -> str:
        """
        Extract EXCEPTION_CODE from !analyze -v output.

        @param raw_text: The full output from cdb.exe.
        @return: The extracted exception code string.
        """
        match = re.search(r"EXCEPTION_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)", raw_text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return ""

    def _extract_faulting_module(self, raw_text: str) -> str:
        """
        Extract MODULE_NAME from !analyze -v output.

        @param raw_text: The full output from cdb.exe.
        @return: The extracted module name string.
        """
        match = re.search(r"MODULE_NAME:\s+(\S+)", raw_text, re.IGNORECASE)
        if match:
            return match.group(1)
        return ""

    def _extract_timestamp(self, raw_text: str) -> str:
        """
        Extract Debug session time from CDB output.

        @param raw_text: The full output from cdb.exe.
        @return: The extracted timestamp string or "".
        """
        match = re.search(r"Debug session time:\s+(.*?)\s+\(UTC", raw_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

