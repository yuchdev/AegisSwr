"""Integration tests: WinDbg JS callback thread handshake (windbg_server.py).

Validates the synchronisation path between the HTTP listener thread and the
caller's main thread via the shared :class:`queue.Queue`.  A dedicated port
range (9990–9992) is used so these tests do not collide with the
``test_server_logic.py`` suite (port 9991).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import requests

from wincrash_analyzer.core.windbg_server import JSCallbackHandler, start_listening

# ---------------------------------------------------------------------------
# Asset paths
# ---------------------------------------------------------------------------

ASSETS_DIR = Path(__file__).parent / "assets"
UNHANDLED_EXCEPTION_JS = ASSETS_DIR / "unhandled_exception_js.json"

# Dedicated port for this test module.
_SERVER_PORT = 9992


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_queue():
    """Drain the class-level data queue before every test"""
    while not JSCallbackHandler.data_queue.empty():
        JSCallbackHandler.data_queue.get_nowait()
    yield


# ---------------------------------------------------------------------------
# Asset sanity checks
# ---------------------------------------------------------------------------


def test_unhandled_exception_asset_exists():
    """The unhandled_exception_js.json asset must be present"""
    assert UNHANDLED_EXCEPTION_JS.exists(), (
        f"Missing asset: {UNHANDLED_EXCEPTION_JS}"
    )


def test_unhandled_exception_asset_structure():
    """The asset must contain the expected top-level keys"""
    data = json.loads(UNHANDLED_EXCEPTION_JS.read_text(encoding="utf-8"))
    assert "ExceptionCode" in data
    assert "Threads" in data
    assert isinstance(data["Threads"], list)
    assert len(data["Threads"]) > 0


# ---------------------------------------------------------------------------
# Thread handshake tests
# ---------------------------------------------------------------------------


def test_js_server_callback_thread_handshake():
    """POST data arrives on the queue synchronously from the listener thread"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        test_data = {
            "threads": [{"id": 0, "stack": ["ntdll!RtlUserThreadStart+0x21"]}]
        }
        resp = requests.post(
            f"http://127.0.0.1:{_SERVER_PORT}",
            json=test_data,
            timeout=5,
        )
        assert resp.status_code == 200

        captured = data_queue.get(timeout=2)
        assert "RtlUserThreadStart" in captured
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_js_server_callback_with_asset_payload():
    """POST the unhandled_exception_js.json asset and verify it is dequeued"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        payload = UNHANDLED_EXCEPTION_JS.read_text(encoding="utf-8")
        resp = requests.post(
            f"http://127.0.0.1:{_SERVER_PORT}",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        assert resp.status_code == 200
        assert resp.text == "Data Captured Successfully"

        captured = data_queue.get(timeout=2)
        parsed = json.loads(captured)
        assert parsed["ExceptionCode"] == "0xE06D7363"
        assert any(
            frame["Function"] == "RtlUserThreadStart"
            for thread in parsed["Threads"]
            for frame in thread["StackFrames"]
        )
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_js_server_queue_is_empty_before_post():
    """The data queue must start empty before any payload is sent"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        assert data_queue.empty()
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_js_server_malformed_json_still_enqueued_as_raw(caplog):
    """Malformed JSON is enqueued as a raw string; server still returns HTTP 200"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        raw = b"{ invalid json payload <"
        with caplog.at_level(logging.CRITICAL, logger="wincrash_analyzer.windbg_server"):
            resp = requests.post(
                f"http://127.0.0.1:{_SERVER_PORT}",
                data=raw,
                headers={"Content-Type": "text/plain"},
                timeout=5,
            )
        assert resp.status_code == 200
        received = data_queue.get(timeout=2)
        assert received == raw.decode("utf-8")
        assert any("malformed" in r.message.lower() for r in caplog.records)
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_js_server_multiple_sequential_posts():
    """Each POST adds exactly one item to the data queue"""
    httpd, data_queue = start_listening(_SERVER_PORT)
    try:
        payloads = [
            json.dumps({"ExceptionCode": f"0x{i:08X}", "Threads": []})
            for i in range(3)
        ]
        for p in payloads:
            requests.post(
                f"http://127.0.0.1:{_SERVER_PORT}",
                data=p.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=5,
            )

        received = []
        for _ in payloads:
            received.append(data_queue.get(timeout=2))

        assert len(received) == 3
        assert data_queue.empty()
    finally:
        httpd.shutdown()
        httpd.server_close()
