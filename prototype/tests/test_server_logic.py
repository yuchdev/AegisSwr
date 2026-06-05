"""Integration tests for the WinDbg JS callback server (windbg_server.py)"""
from __future__ import annotations

import json
import logging
import os
import socket
import time

import pytest
import requests

from wincrash_analyzer.core.windbg_server import JSCallbackHandler, WinDbgServer, start_listening

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_MOCK_JSON_PATH = os.path.join(_ASSETS_DIR, "mock_js_output.json")

_SERVER_PORT = 9991  # Dedicated port so tests don't collide with production.


def _port_free(port: int) -> bool:
    """Return True if *port* is not currently bound on localhost"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_queue():
    """Drain the class-level queue before every test"""
    while not JSCallbackHandler.data_queue.empty():
        JSCallbackHandler.data_queue.get_nowait()
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mock_json_asset_exists():
    """The mock WinDbg JSON asset must be present"""
    assert os.path.isfile(_MOCK_JSON_PATH), f"Missing asset: {_MOCK_JSON_PATH}"
    with open(_MOCK_JSON_PATH) as fh:
        data = json.load(fh)
    assert "Threads" in data
    assert "ExceptionCode" in data


def test_end_to_end_post_and_dequeue():
    """POST the mock JSON and verify it arrives on the data queue unchanged"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        with open(_MOCK_JSON_PATH) as fh:
            payload = fh.read()

        resp = requests.post(
            f"http://127.0.0.1:{_SERVER_PORT}",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        assert resp.status_code == 200
        assert resp.text == "Data Captured Successfully"

        received = data_queue.get(timeout=5)
        assert received == payload
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_port_released_after_shutdown():
    """After shutdown() + server_close() the port must become available again"""
    httpd, _ = start_listening(_SERVER_PORT)
    httpd.shutdown()
    httpd.server_close()
    # Give the OS a moment to reclaim the port.
    time.sleep(0.2)
    assert _port_free(_SERVER_PORT), f"Port {_SERVER_PORT} is still bound after shutdown."


def test_empty_post_returns_400():
    """A POST with Content-Length: 0 must be rejected with HTTP 400"""
    httpd, _ = start_listening(_SERVER_PORT)
    try:
        resp = requests.post(
            f"http://127.0.0.1:{_SERVER_PORT}",
            data=b"",
            headers={"Content-Length": "0"},
            timeout=5,
        )
        assert resp.status_code == 400
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_malformed_json_still_enqueued(caplog):
    """Malformed JSON payloads are enqueued as raw strings with a CRITICAL log"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        raw = b"this is not valid json {"
        with caplog.at_level(logging.CRITICAL, logger="wincrash_analyzer.windbg_server"):
            resp = requests.post(
                f"http://127.0.0.1:{_SERVER_PORT}",
                data=raw,
                headers={"Content-Type": "text/plain"},
                timeout=5,
            )
        assert resp.status_code == 200
        received = data_queue.get(timeout=5)
        assert received == raw.decode("utf-8")
        assert any("malformed" in r.message.lower() for r in caplog.records)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_windbg_server_class_start_stop():
    """WinDbgServer.start() / stop() lifecycle smoke test"""
    server = WinDbgServer(port=_SERVER_PORT)
    server.start()
    assert server.data_queue is not None
    server.stop()
    time.sleep(0.2)
    assert _port_free(_SERVER_PORT)


def test_windbg_server_data_queue_raises_before_start():
    """Accessing data_queue before start() must raise RuntimeError"""
    server = WinDbgServer(port=_SERVER_PORT)
    with pytest.raises(RuntimeError):
        _ = server.data_queue


def test_port_fallback_on_collision():
    """start_listening falls back to a lower port when the preferred one is busy"""
    # Occupy the preferred port.
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # On Windows, SO_REUSEADDR can allow another socket to bind the same
    # endpoint in tests; use exclusive mode to force a real collision.
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    blocker.bind(("127.0.0.1", _SERVER_PORT))
    blocker.listen(1)
    try:
        httpd, _ = start_listening(_SERVER_PORT)
        # Server must have bound to one of the fallback ports.
        bound_port = httpd.server_address[1]
        assert bound_port in (_SERVER_PORT - 1, _SERVER_PORT - 2)
        httpd.shutdown()
        httpd.server_close()
    finally:
        blocker.close()
