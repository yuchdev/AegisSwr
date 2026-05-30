"""WinDbg JavaScript engine debug backend.

Uses the WinDbg Debugger Data Model (DDM) via a JavaScript script injected into
``cdb.exe`` via ``.scriptload``. The script queries the DDM for typed structured
data (exception record, all thread call stacks, module addresses) and POSTs the
result as JSON to an ephemeral local HTTP bridge started by Python.

Advantages over CdbBackend:
- Returns typed JSON — no regex parsing of ``!analyze -v`` free text.
- All threads returned (faulting thread at full depth; others summarised).
- ``ExceptionAddress`` from DDM ``exc.Address`` — more reliable than inferring
  it from the top stack frame.
- Path toward live-process attachment (not only static dump files).

Windows-only: the JS script uses ``ActiveXObject("MSXML2.XMLHTTP")`` (COM),
which is only available inside the cdb/WinDbg Chakra-based WScript runtime.
"""
from __future__ import annotations

import contextlib
import json
import os
import queue
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from loguru import logger

from aegis_swr.backends.debug._base import _BaseDebugBackend, normalize_address
from aegis_swr.backends.debug._symbol_path import resolve_symbol_path
from aegis_swr.core.data_adapter import apply_noise_filter
from aegis_swr.core.exceptions import DebugExtractionError
from aegis_swr.core.fault_codes import map_windows_ntstatus
from aegis_swr.core.schemas import DebugExtractionResult, DumpFormat, StackFrame

if TYPE_CHECKING:
    from aegis_swr.core.schemas import IncidentSource

_DEFAULT_SYMBOL_SERVER = "https://msdl.microsoft.com/download/symbols"
_JS_ASSET_NAME = "windbg_diagnostic.js"
_JS_PROVIDER_MARKER = "JsProvider"


# ---------------------------------------------------------------------------
# Callback bridge
# ---------------------------------------------------------------------------


def _make_handler(data_queue: queue.Queue[str]) -> type[BaseHTTPRequestHandler]:
    """Return a handler class whose POST enqueues payloads into *data_queue*.

    Uses a closure rather than a class-level attribute so each
    :class:`_CallbackBridge` instance has its own isolated queue.
    """

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                data_queue.put(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as exc:  # pragma: no cover
                logger.error(f"Bridge handler error: {exc}")
                self.send_response(500)
                self.end_headers()

        def log_message(self, *args: object) -> None:
            pass  # suppress noisy HTTP access log lines

    return _Handler


class _CallbackBridge:
    """RAII context manager: binds an ephemeral HTTP listener for one extraction.

    ``port=0`` instructs the OS to choose a free port; the actual port is
    available as ``self.port`` after ``__enter__``.
    """

    def __init__(self, callback_timeout: int) -> None:
        self._timeout = callback_timeout
        self._queue: queue.Queue[str] = queue.Queue()
        self._server: HTTPServer | None = None
        self.port: int = 0

    def __enter__(self) -> _CallbackBridge:
        handler_cls = _make_handler(self._queue)
        self._server = HTTPServer(("127.0.0.1", 0), handler_cls)
        self.port = self._server.server_address[1]
        thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        thread.start()
        logger.debug(f"WinDbg bridge listening on 127.0.0.1:{self.port}")
        return self

    def __exit__(self, *_: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def wait_for_payload(self) -> str:
        """Block until the JS callback POST arrives, then return the raw body.

        Raises :class:`DebugExtractionError` if the wait times out.
        """
        try:
            return self._queue.get(timeout=self._timeout)
        except queue.Empty as exc:
            raise DebugExtractionError(
                f"Timed out after {self._timeout}s waiting for WinDbg JS callback. "
                "The script may have failed silently — check that JsProvider.dll is loaded."
            ) from exc


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


def _unlink_safe(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        logger.warning(f"Could not remove temp JS file: {path}")


class WinDbgJSBackend(_BaseDebugBackend):
    """WinDbg JavaScript engine debug backend (Windows only).

    Preferred over :class:`CdbBackend` when ``JsProvider.dll`` is available
    because it queries the Debugger Data Model directly and returns typed JSON.
    """

    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]] = [DumpFormat.WINDOWS_MINIDUMP]
    SUPPORTED_PLATFORMS: ClassVar[list[str]] = ["Windows"]

    # ------------------------------------------------------------------
    # Public entry point (overrides base template method entirely)
    # ------------------------------------------------------------------

    def extract(
        self,
        source: IncidentSource,
        symbol_path: str | None,
    ) -> DebugExtractionResult:
        self._validate(source)
        js_content = self._prepare_js_template()  # raises early if asset missing

        with contextlib.ExitStack() as stack:
            bridge = stack.enter_context(
                _CallbackBridge(self._settings.callback_timeout_seconds)
            )
            js_source = self._inject_params(js_content, bridge.port)

            fd, tmp_path = tempfile.mkstemp(suffix=".js")
            stack.callback(_unlink_safe, tmp_path)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(js_source)

            raw_stdout = self._run(self._js_command(source, symbol_path, tmp_path))

            if _JS_PROVIDER_MARKER not in raw_stdout:
                raise DebugExtractionError(
                    "WinDbg JavaScript provider (JsProvider.dll) did not load. "
                    "Ensure Debugging Tools for Windows includes JsProvider.dll "
                    "and that cdb.exe supports .scriptload."
                )

            payload = bridge.wait_for_payload()

        return self._parse(payload, source)

    # ------------------------------------------------------------------
    # ABC requirement — _build_command_sequence
    # ------------------------------------------------------------------

    def _build_command_sequence(
        self,
        source: IncidentSource,
        symbol_path: str | None,
    ) -> list[str]:
        # This method satisfies the ABC contract and is used when the base
        # template method (which we override) would call it. In practice
        # extract() always calls _js_command() directly with a concrete path.
        return self._js_command(source, symbol_path, "<tmp_js_path>")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _asset_path(self) -> Path:
        return Path(__file__).parent / "assets" / _JS_ASSET_NAME

    def _prepare_js_template(self) -> str:
        """Read the JS asset; raise DebugExtractionError if it is missing."""
        path = self._asset_path()
        if not path.exists():
            raise DebugExtractionError(
                f"WinDbg JS asset not found: {path}. "
                "Reinstall or repair the aegis-swr package."
            )
        return path.read_text(encoding="utf-8")

    def _inject_params(self, template: str, port: int) -> str:
        """Substitute runtime tokens into the JS template."""
        settings = self._settings
        max_faulting = getattr(settings, "max_faulting_frames", 20)
        max_other = getattr(settings, "max_other_thread_frames", 3)
        return (
            template
            .replace("__CALLBACK_URL__", f"http://127.0.0.1:{port}/")
            .replace("__MAX_FAULTING_FRAMES__", str(max_faulting))
            .replace("__MAX_OTHER_FRAMES__", str(max_other))
        )

    def _symbol_path_string(self, symbol_path: str | None) -> str:
        cache = resolve_symbol_path(self._settings.symbol_cache)
        server = self._settings.symbol_server_url or _DEFAULT_SYMBOL_SERVER
        chain = f"srv*{cache}*{server}"
        if symbol_path:
            chain = f"{chain};{symbol_path}"
        return chain

    def _js_command(
        self,
        source: IncidentSource,
        symbol_path: str | None,
        tmp_js_path: str,
    ) -> list[str]:
        return [
            "cdb.exe",
            "-z",
            str(source.dump_path),
            "-y",
            self._symbol_path_string(symbol_path),
            "-c",
            f'.scriptload "{tmp_js_path}"; g; q',
        ]

    def _parse(self, raw_json: str, source: IncidentSource) -> DebugExtractionResult:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise DebugExtractionError(
                f"WinDbg JS callback returned invalid JSON: {exc}"
            ) from exc

        exception_code = data.get("ExceptionCode") or "0x0"
        fault_class = map_windows_ntstatus(exception_code)
        exception_address = normalize_address(data.get("ExceptionAddress") or "0x0")
        faulting_module = data.get("FaultingModule") or None

        frames: list[StackFrame] = []
        faulting_thread = data.get("FaultingThread")
        if isinstance(faulting_thread, dict):
            raw_frames = faulting_thread.get("Frames") or []
            for f in raw_frames:
                module = f.get("Module") or None
                function = f.get("Function") or None
                frames.append(
                    StackFrame(
                        frame_number=int(f.get("FrameNumber", len(frames))),
                        module=module if module else None,
                        function=function if function else None,
                        source_file=None,
                        source_line=None,
                        instruction_address=normalize_address(f.get("Offset") or "0x0"),
                    )
                )
            if frames and faulting_module is None:
                faulting_module = frames[0].module

        faulting_function = frames[0].function if frames else None

        # raw_text_excerpt: the whole DDM JSON capped at 8k chars,
        # passed through the noise filter (strips fill patterns etc.).
        raw_text_excerpt = apply_noise_filter(raw_json[:8000])

        return DebugExtractionResult(
            fault_class=fault_class,
            exception_code_raw=exception_code,
            exception_address=exception_address,
            faulting_module=faulting_module,
            faulting_function=faulting_function,
            stack_frames=frames,
            symbol_resolution_score=self._symbol_score(frames),
            raw_text_excerpt=raw_text_excerpt,
        )
