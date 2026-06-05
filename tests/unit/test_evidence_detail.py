"""Unit tests for the DEBUG-level Evidence Stream metadata helpers.

These cover the pure helpers in :mod:`aegis_swr.views._evidence_detail`:
human file sizes, filesystem properties, the ±2-minute log window, and the
libpcap header parser (little/big-endian, pcapng detection, malformed input).
"""
from __future__ import annotations

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
    assert format_size(512) == "512 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(5 * 1024 * 1024) == "5.0 MB"
    assert format_size(3 * 1024**3) == "3.0 GB"


# ---------------------------------------------------------------------------
# file_properties
# ---------------------------------------------------------------------------


def test_file_properties_existing(tmp_path: Path):
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
    props = file_properties(str(tmp_path / "gone.log"))
    assert props.exists is False
    assert props.describe() == "gone.log  (missing)"


# ---------------------------------------------------------------------------
# log_window
# ---------------------------------------------------------------------------


def test_log_window_is_plus_minus_two_minutes():
    incident = datetime(2026, 6, 4, 14, 2, 11)
    start, end = log_window(incident)
    assert end - start == timedelta(minutes=4)
    assert start == incident - timedelta(minutes=2)
    assert end == incident + timedelta(minutes=2)
    assert LOG_WINDOW == timedelta(minutes=2)


def test_describe_log_window_with_timestamp():
    incident = datetime(2026, 6, 4, 14, 2, 11)
    text = describe_log_window(incident)
    assert "14:00:11" in text
    assert "14:04:11" in text
    assert "±2m" in text


def test_describe_log_window_without_timestamp():
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
    packets: list[tuple[int, int, bytes]] | None = None,
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
    cap = _write_pcap(tmp_path / "weird.pcap", link_type=250, packets=[])
    info = pcap_metadata(str(cap))
    assert info.link_type == "LINKTYPE_250"
    assert info.packet_count == 0


def test_pcap_metadata_detects_pcapng(tmp_path: Path):
    cap = tmp_path / "modern.pcapng"
    cap.write_bytes(b"\x0a\x0d\x0d\x0a" + b"\x00" * 32)
    info = pcap_metadata(str(cap))
    assert info.container == "pcapng"
    assert info.note is not None


def test_pcap_metadata_rejects_garbage(tmp_path: Path):
    cap = tmp_path / "garbage.bin"
    cap.write_bytes(b"NOTAPCAP" + b"\x00" * 32)
    info = pcap_metadata(str(cap))
    assert info.container == "unknown"


def test_pcap_metadata_too_small(tmp_path: Path):
    cap = tmp_path / "tiny.pcap"
    cap.write_bytes(b"\xd4\xc3")
    info = pcap_metadata(str(cap))
    assert info.container == "unknown"
    assert info.note == "file too small"


def test_file_props_describe_dataclass_defaults():
    # A bare FileProps with no stat info still describes cleanly.
    props = FileProps(name="x.bin", exists=True)
    assert props.describe() == "x.bin"
