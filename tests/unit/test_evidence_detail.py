"""Unit tests for the DEBUG-level Evidence Stream metadata helpers.

These cover the pure helpers in :mod:`aegis_swr.views._evidence_detail`:
human file sizes, filesystem properties, the ±2-minute log window, and the
libpcap header parser (little/big-endian, pcapng detection, malformed input).
"""
from __future__ import annotations
from typing import Optional

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aegis_swr.views.evidence_detail import (
    LOG_WINDOW,
    FileProps,
    describe_log_window,
    file_properties,
    format_size,
    log_window,
    pcap_metadata,
)

# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------


def test_format_size_units():
    """
    [Unit] evidence detail: verifies format size units.

    Scenario:
        Given test inputs and fixtures for format size units
        When test_format_size_units executes the target flow
        Then the expected outcome for format size units is confirmed.

    Boundaries:
        - Focus: format size units
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to format size units
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(5 * 1024 * 1024) == "5.0 MB"
    assert format_size(3 * 1024**3) == "3.0 GB"


# ---------------------------------------------------------------------------
# file_properties
# ---------------------------------------------------------------------------


def test_file_properties_existing(tmp_path: Path):
    """
    [Unit] evidence detail: verifies file properties existing.

    Scenario:
        Given test inputs and fixtures for file properties existing
        When test_file_properties_existing executes the target flow
        Then the expected outcome for file properties existing is confirmed.

    Boundaries:
        - Focus: file properties existing
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file properties existing
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    target = tmp_path / "app.log"
    target.write_text("hello world")
    props = file_properties(str(target))
    assert props.exists is True
    assert props.name == "app.log"
    assert props.size == 11
    assert props.modified is not None
    described = props.describe()
    assert "app.log" in described
    assert "11 B" in described
    assert "modified" in described


def test_file_properties_missing(tmp_path: Path):
    """
    [Unit] evidence detail: verifies file properties missing.

    Scenario:
        Given test inputs and fixtures for file properties missing
        When test_file_properties_missing executes the target flow
        Then the expected outcome for file properties missing is confirmed.

    Boundaries:
        - Focus: file properties missing
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file properties missing
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    props = file_properties(str(tmp_path / "gone.log"))
    assert props.exists is False
    assert props.describe() == "gone.log  (missing)"


# ---------------------------------------------------------------------------
# log_window
# ---------------------------------------------------------------------------


def test_log_window_is_plus_minus_two_minutes():
    """
    [Unit] evidence detail: verifies log window is plus minus two minutes.

    Scenario:
        Given test inputs and fixtures for log window is plus minus two minutes
        When test_log_window_is_plus_minus_two_minutes executes the target flow
        Then the expected outcome for log window is plus minus two minutes is confirmed.

    Boundaries:
        - Focus: log window is plus minus two minutes
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log window is plus minus two minutes
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    incident = datetime(2026, 6, 4, 14, 2, 11)
    start, end = log_window(incident)
    assert end - start == timedelta(minutes=4)
    assert start == incident - timedelta(minutes=2)
    assert end == incident + timedelta(minutes=2)
    assert LOG_WINDOW == timedelta(minutes=2)


def test_describe_log_window_with_timestamp():
    """
    [Unit] evidence detail: verifies describe log window with timestamp.

    Scenario:
        Given test inputs and fixtures for describe log window with timestamp
        When test_describe_log_window_with_timestamp executes the target flow
        Then the expected outcome for describe log window with timestamp is confirmed.

    Boundaries:
        - Focus: describe log window with timestamp
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to describe log window with timestamp
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    incident = datetime(2026, 6, 4, 14, 2, 11)
    text = describe_log_window(incident)
    assert "14:00:11" in text
    assert "14:04:11" in text
    assert "±2m" in text


def test_describe_log_window_without_timestamp():
    """
    [Unit] evidence detail: verifies describe log window without timestamp.

    Scenario:
        Given test inputs and fixtures for describe log window without timestamp
        When test_describe_log_window_without_timestamp executes the target flow
        Then the expected outcome for describe log window without timestamp is confirmed.

    Boundaries:
        - Focus: describe log window without timestamp
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to describe log window without timestamp
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    assert log_window(None) is None
    assert "no incident timestamp" in describe_log_window(None)


# ---------------------------------------------------------------------------
# pcap_metadata
# ---------------------------------------------------------------------------


def _write_pcap(
    path: Path,
    *,
    endian: str = "<",
    nanosecond: bool = False,
    link_type: int = 1,
    packets: Optional[list[tuple[int, int, bytes]]] = None,
) -> Path:
    """Write a minimal but valid libpcap file with *packets* records"""
    if nanosecond:
        magic = 0xA1B23C4D
    else:
        magic = 0xA1B2C3D4
    header = struct.pack(f"{endian}IHHiIII", magic, 2, 4, 0, 0, 65535, link_type)
    body = b""
    for ts_sec, ts_sub, payload in packets or []:
        body += struct.pack(f"{endian}IIII", ts_sec, ts_sub, len(payload), len(payload))
        body += payload
    path.write_bytes(header + body)
    return path


def test_pcap_metadata_little_endian(tmp_path: Path):
    """
    [Unit] evidence detail: verifies pcap metadata little endian.

    Scenario:
        Given test inputs and fixtures for pcap metadata little endian
        When test_pcap_metadata_little_endian executes the target flow
        Then the expected outcome for pcap metadata little endian is confirmed.

    Boundaries:
        - Focus: pcap metadata little endian
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pcap metadata little endian
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    cap = _write_pcap(
        tmp_path / "capture.pcap",
        endian="<",
        packets=[
            (1_700_000_000, 0, b"\xde\xad\xbe\xef"),
            (1_700_000_002, 500_000, b"\x01\x02"),
        ],
    )
    info = pcap_metadata(str(cap))
    assert info.container == "pcap"
    assert info.byte_order == "little"
    assert info.timestamp_resolution == "microsecond"
    assert info.version == "2.4"
    assert info.snaplen == 65535
    assert info.link_type == "ETHERNET"
    assert info.packet_count == 2
    assert info.first_timestamp == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
    assert info.last_timestamp == datetime.fromtimestamp(1_700_000_002.5, tz=timezone.utc)


def test_pcap_metadata_big_endian_and_linktype(tmp_path: Path):
    """
    [Unit] evidence detail: verifies pcap metadata big endian and linktype.

    Scenario:
        Given test inputs and fixtures for pcap metadata big endian and linktype
        When test_pcap_metadata_big_endian_and_linktype executes the target flow
        Then the expected outcome for pcap metadata big endian and linktype is confirmed.

    Boundaries:
        - Focus: pcap metadata big endian and linktype
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pcap metadata big endian and linktype
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    cap = _write_pcap(
        tmp_path / "be.pcap",
        endian=">",
        link_type=113,  # LINUX_SLL
        packets=[(1_700_000_000, 0, b"x" * 8)],
    )
    info = pcap_metadata(str(cap))
    assert info.byte_order == "big"
    assert info.link_type == "LINUX_SLL"
    assert info.packet_count == 1


def test_pcap_metadata_unknown_linktype_falls_back(tmp_path: Path):
    """
    [Unit] evidence detail: verifies pcap metadata unknown linktype falls back.

    Scenario:
        Given test inputs and fixtures for pcap metadata unknown linktype falls back
        When test_pcap_metadata_unknown_linktype_falls_back executes the target flow
        Then the expected outcome for pcap metadata unknown linktype falls back is confirmed.

    Boundaries:
        - Focus: pcap metadata unknown linktype falls back
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pcap metadata unknown linktype falls back
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    cap = _write_pcap(tmp_path / "weird.pcap", link_type=250, packets=[])
    info = pcap_metadata(str(cap))
    assert info.link_type == "LINKTYPE_250"
    assert info.packet_count == 0


def test_pcap_metadata_detects_pcapng(tmp_path: Path):
    """
    [Unit] evidence detail: verifies pcap metadata detects pcapng.

    Scenario:
        Given test inputs and fixtures for pcap metadata detects pcapng
        When test_pcap_metadata_detects_pcapng executes the target flow
        Then the expected outcome for pcap metadata detects pcapng is confirmed.

    Boundaries:
        - Focus: pcap metadata detects pcapng
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pcap metadata detects pcapng
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    cap = tmp_path / "modern.pcapng"
    cap.write_bytes(b"\x0a\x0d\x0d\x0a" + b"\x00" * 32)
    info = pcap_metadata(str(cap))
    assert info.container == "pcapng"
    assert info.note is not None


def test_pcap_metadata_rejects_garbage(tmp_path: Path):
    """
    [Unit] evidence detail: verifies pcap metadata rejects garbage.

    Scenario:
        Given test inputs and fixtures for pcap metadata rejects garbage
        When test_pcap_metadata_rejects_garbage executes the target flow
        Then the expected outcome for pcap metadata rejects garbage is confirmed.

    Boundaries:
        - Focus: pcap metadata rejects garbage
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pcap metadata rejects garbage
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    cap = tmp_path / "garbage.bin"
    cap.write_bytes(b"NOTAPCAP" + b"\x00" * 32)
    info = pcap_metadata(str(cap))
    assert info.container == "unknown"


def test_pcap_metadata_too_small(tmp_path: Path):
    """
    [Unit] evidence detail: verifies pcap metadata too small.

    Scenario:
        Given test inputs and fixtures for pcap metadata too small
        When test_pcap_metadata_too_small executes the target flow
        Then the expected outcome for pcap metadata too small is confirmed.

    Boundaries:
        - Focus: pcap metadata too small
        - Fixtures/params: tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to pcap metadata too small
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    cap = tmp_path / "tiny.pcap"
    cap.write_bytes(b"\xd4\xc3")
    info = pcap_metadata(str(cap))
    assert info.container == "unknown"
    assert info.note == "file too small"


def test_file_props_describe_dataclass_defaults():
    # A bare FileProps with no stat info still describes cleanly.
    """
    [Unit] evidence detail: verifies file props describe dataclass defaults.

    Scenario:
        Given test inputs and fixtures for file props describe dataclass defaults
        When test_file_props_describe_dataclass_defaults executes the target flow
        Then the expected outcome for file props describe dataclass defaults is confirmed.

    Boundaries:
        - Focus: file props describe dataclass defaults
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to file props describe dataclass defaults
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by evidence detail
    """
    props = FileProps(name="x.bin", exists=True)
    assert props.describe() == "x.bin"
