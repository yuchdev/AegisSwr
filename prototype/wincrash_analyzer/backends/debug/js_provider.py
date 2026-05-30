"""WinDbg JavaScript engine backend."""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import tempfile

from wincrash_analyzer.backends.debug.base import DebugBackendBase
from wincrash_analyzer.core.exceptions import DebuggerEngineError, DebuggerNotFoundError
from wincrash_analyzer.core.windbg_server import start_listening

logger = logging.getLogger(__name__)

# JavaScript template executed inside the WinDbg JS engine.
# Placeholder: __CALLBACK_URL__
_JS_TEMPLATE = '''"use strict";

function initializeScript() {
    return [new host.apiVersionSupport(1, 9)];
}

(function () {
    var callbackUrl = "__CALLBACK_URL__";
    var maxFrames = 100;

    var process = host.currentProcess;
    var result = {
        ProcessID: process.Id,
        ProcessName: process.Name,
        ExceptionCode: "",
        FaultingModule: "",
        Threads: []
    };

    try {
        var exception = process.LastEvent.Attributes.Exception;
        result.ExceptionCode = "0x" + exception.Code.toString(16);
    } catch (e) {}

    for (var thread of process.Threads) {
        var threadObj = {
            ThreadID: thread.Id,
            Attributes: { IsFaulting: false, Priority: 0 },
            StackFrames: []
        };
        var frameIdx = 0;
        for (var frame of thread.Stack.Frames) {
            if (frameIdx >= maxFrames) { break; }
            threadObj.StackFrames.push({
                FrameNumber: frameIdx,
                Module: frame.Module ? frame.Module.Name : "Unknown",
                Function: frame.FunctionName || "Unknown",
                Offset: "0x" + frame.Offset.toString(16)
            });
            frameIdx++;
        }
        if (thread.Attributes.IsFaulting) {
            result.FaultingModule = threadObj.StackFrames.length > 0 ? threadObj.StackFrames[0].Module : "";
        }
        result.Threads.push(threadObj);
    }

    var payload = JSON.stringify(result);
    var xhr = new ActiveXObject("MSXML2.XMLHTTP");
    xhr.open("POST", callbackUrl, false);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Content-Length", payload.length.toString());
    xhr.send(payload);
})();
'''


class JSProviderBackend(DebugBackendBase):
    """
    Debugger backend that uses the WinDbg JS engine.

    The backend:
    1. Starts a local HTTP server (via :class:`WinDbgServer`) to receive callbacks.
    2. Generates a temporary ``.js`` file containing the diagnostic script.
    3. Spawns ``cdb.exe`` with ``.scriptload <file>; q``.
    4. Waits up to ``_CALLBACK_TIMEOUT`` seconds for the JS engine to POST
       the crash data back, then returns the raw JSON payload.
    """

    @property
    def engine_type(self) -> str:
        """
        Identifier for the debug engine.

        @return: The engine type string "js".
        """
        return "js"

    _CDB_TIMEOUT = 300      # seconds: hard watchdog for the cdb.exe process
    _CALLBACK_PORT = 9999   # preferred callback port
    _CALLBACK_TIMEOUT = 60  # seconds: wait for the JS→HTTP handshake

    def _generate_js(self, port: int, sym_path: str) -> str:
        """
        Return the JS diagnostic script with substituted values.

        @param port: TCP port on which the callback server is listening.
        @param sym_path: Windows symbol path.
        @return: The populated JS source string.
        """
        callback_url = f"http://127.0.0.1:{port}/"
        return _JS_TEMPLATE.replace("__CALLBACK_URL__", callback_url)

    def extract(self, dump_path: str, symbol_path: str) -> dict:
        """
        Extract crash data via the WinDbg JavaScript engine.

        @param dump_path: Path to the Windows crash dump (``.dmp``) file.
        @param symbol_path: Symbol search path passed to the JS script.
        @return: A dictionary with 'raw' containing the JSON payload from the JS callback.
        @raises DebuggerEngineError: If an error occurs during extraction or callback.
        @raises DebuggerNotFoundError: If cdb.exe cannot be found.
        """
        if not os.access(dump_path, os.R_OK):
            raise DebuggerEngineError(f"Dump file is not readable: {dump_path}")

        httpd, data_queue = start_listening(self._CALLBACK_PORT)
        actual_port = httpd.server_address[1]

        try:
            js_source = self._generate_js(actual_port, symbol_path)

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".js",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(js_source)
                tmp_path = tmp.name

            try:
                dbg_cmds = f'.scriptload "{tmp_path}"; q'
                logger.debug("CDB commands: %s", dbg_cmds)
                logger.info("Spawning CDB (JS mode) for dump: %s", dump_path)

                try:
                    result = subprocess.run(
                        ["cdb.exe", "-z", dump_path, "-c", dbg_cmds],
                        capture_output=True,
                        text=True,
                        timeout=self._CDB_TIMEOUT,
                    )
                except subprocess.TimeoutExpired:
                    raise DebuggerEngineError("CDB timed out during JS script execution.")
                except FileNotFoundError:
                    raise DebuggerNotFoundError("cdb.exe not found in system PATH.")

                if "JavaScript provider not found" in (result.stdout + result.stderr):
                    raise DebuggerEngineError(
                        "WinDbg JS provider is unavailable; "
                        "ensure JsProvider.dll is loaded."
                    )

                if result.returncode != 0:
                    logger.warning("CDB exited with code %d", result.returncode)

                try:
                    payload = data_queue.get(timeout=self._CALLBACK_TIMEOUT)
                except queue.Empty:
                    raise DebuggerEngineError(
                        "Timed out waiting for JS callback; "
                        "the script may have failed silently."
                    )

                report_data = {"raw": payload}

                # Try to parse the payload to extract metadata
                try:
                    import json
                    data = json.loads(payload)
                    report_data["exception_code"] = data.get("ExceptionCode", "")
                    report_data["faulting_module"] = data.get("FaultingModule", "")
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Could not parse JS callback payload for metadata.")

                if logger.isEnabledFor(logging.DEBUG):
                    report_data["execution_log"] = [{"cmd": dbg_cmds, "output": result.stdout}]
                    report_data["raw_stdout"] = result.stdout

                return report_data

            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.warning("Could not remove temp JS file: %s", tmp_path)

        finally:
            httpd.shutdown()
            httpd.server_close()
