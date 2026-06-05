"""WinDbg JS callback thread server"""
from __future__ import annotations

import json
import logging
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)

# Maximum payload size accepted without chunked reading (10 MB).
_CHUNK_THRESHOLD = 10 * 1024 * 1024


class JSCallbackHandler(BaseHTTPRequestHandler):
    """
    Handles the POST callback from WinDbg's JavaScript engine.
    """

    # Static queue shared across all handler instances and threads.
    data_queue: queue.Queue = queue.Queue()

    def do_POST(self):
        """
        Process an incoming crash-data payload from WinDbg.
        """
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self.send_response(400)
                self.end_headers()
                return

            # For very large payloads read in chunks to avoid a single huge
            # allocation that could exhaust memory.
            if content_length > _CHUNK_THRESHOLD:
                chunks: list[bytes] = []
                remaining = content_length
                while remaining > 0:
                    chunk = self.rfile.read(min(_CHUNK_THRESHOLD, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw_body = b"".join(chunks).decode("utf-8")
            else:
                raw_body = self.rfile.read(content_length).decode("utf-8")

            # Validate JSON; log a critical warning but still enqueue the raw
            # string so nothing is lost.
            try:
                json.loads(raw_body)
            except json.JSONDecodeError:
                logger.critical(
                    "Received malformed JSON from WinDbg JS engine; "
                    "enqueuing raw string for manual inspection."
                )

            self.data_queue.put(raw_body)

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Data Captured Successfully")

            logger.debug("Captured %d bytes from WinDbg JS.", content_length)

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Server handler error: %s", exc)
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        """
        Suppress the default per-request log lines.

        @param format: Log format string.
        @param args: Log arguments.
        """
        pass  # Intentionally empty – output is handled via the module logger.


def start_listening(port: int = 9999) -> tuple[HTTPServer, queue.Queue]:
    """
    Start the HTTP listener in a background daemon thread.

    Tries *port* first; on ``OSError`` (port already in use) it falls back to
    ``port - 1`` and ``port - 2`` before giving up.

    @param port: Preferred TCP port (default ``9999``).
    @return: A ``(httpd, data_queue)`` tuple.
    @raises OSError: If none of the attempted ports could be bound.
    """
    last_exc: OSError | None = None
    for candidate in (port, port - 1, port - 2):
        try:
            httpd = HTTPServer(("127.0.0.1", candidate), JSCallbackHandler)
        except OSError as exc:
            logger.warning("Port %d unavailable: %s – trying next port.", candidate, exc)
            last_exc = exc
            continue

        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        logger.info("WinDbg Bridge listening on http://127.0.0.1:%d", candidate)
        return httpd, JSCallbackHandler.data_queue

    raise OSError(f"Could not bind to any port in range [{port - 2}, {port}]") from last_exc


class WinDbgServer:
    """
    Lightweight HTTP server that receives callbacks from the WinDbg JS engine.
    """

    def __init__(self, port: int = 9999):
        """
        Initialize the WinDbgServer.

        @param port: The port to listen on.
        """
        self._port = port
        self._httpd: HTTPServer | None = None
        self._data_queue: queue.Queue | None = None

    @property
    def data_queue(self) -> queue.Queue:
        """
        The shared data queue (available after :meth:`start`).

        @return: The queue where received data is stored.
        @raises RuntimeError: If the server has not been started yet.
        """
        if self._data_queue is None:
            raise RuntimeError("Server has not been started yet.")
        return self._data_queue

    def start(self):
        """
        Start the callback listener in a background thread.
        """
        self._httpd, self._data_queue = start_listening(self._port)

    def stop(self):
        """
        Stop the callback listener and release the port.
        """
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
