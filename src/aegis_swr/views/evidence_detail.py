"""Pure helpers for the DEBUG-level Evidence Stream metadata.

These functions turn on-disk artifacts (log files, screenshots, network
captures) into structured, human-readable metadata for the war-room Evidence
Stream.  They are deliberately free of any Rich/UI dependency so they can be
unit-tested in isolation; :mod:`aegis_swr.views.rich_view` formats their output
into styled lines.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: Display window shown around the incident for every analyzed log file.
LOG_WINDOW = timedelta(minutes=2)

# Common libpcap link-layer header types (DLT/LINKTYPE_* values).
_LINK_TYPES: dict[int, str] = {
    0: "NULL",
    1: "ETHERNET",
    6: "IEEE802_5",
    9: "PPP",
    101: "RAW",
    105: "IEEE802_11",
    113: "LINUX_SLL",
    127: "IEEE802_11_RADIOTAP",
    143: "DOCSIS",
    228: "IPV4",
    229: "IPV6",
    276: "LINUX_SLL2",
}

# pcap global-header magic numbers → (byte order, timestamp resolution).
_PCAP_MAGICS: dict[bytes, tuple[str, str]] = {
    b"\xa1\xb2\xc3\xd4": ("big", "microsecond"),
    b"\xd4\xc3\xb2\xa1": ("little", "microsecond"),
    b"\xa1\xb2\x3c\x4d": ("big", "nanosecond"),
    b"\x4d\x3c\xb2\xa1": ("little", "nanosecond"),
}
_PCAPNG_MAGIC = b"\x0a\x0d\x0d\x0a"


def format_size(num_bytes: int) -> str:
    """Render a byte count as a compact human string (``1.2 KB``)"""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - unreachable


@dataclass
class FileProps:
    """Filesystem properties of an evidence artifact"""

    name: str
    exists: bool
    size: int | None = None
    modified: datetime | None = None

    def describe(self) -> str:
        """One-line ``name  (1.2 KB, modified 2026-06-04 14:02:11)``"""
        if not self.exists:
            return f"{self.name}  (missing)"
        parts: list[str] = []
        if self.size is not None:
            parts.append(format_size(self.size))
        if self.modified is not None:
            parts.append(f"modified {self.modified:%Y-%m-%d %H:%M:%S}")
        suffix = f"  ({', '.join(parts)})" if parts else ""
        return f"{self.name}{suffix}"


def file_properties(raw_path: str) -> FileProps:
    """Stat *raw_path*, returning name/size/mtime (gracefully if it's gone)"""
    path = Path(raw_path)
    try:
        stat = path.stat()
    except OSError:
        return FileProps(name=path.name or raw_path, exists=False)
    return FileProps(
        name=path.name or raw_path,
        exists=True,
        size=stat.st_size,
        modified=datetime.fromtimestamp(stat.st_mtime),
    )


def log_window(
    incident_ts: datetime | None,
    window: timedelta = LOG_WINDOW,
) -> tuple[datetime, datetime] | None:
    """Return the ``[incident - window, incident + window]`` span, or None.

    None means there is no incident timestamp to anchor the window to.
    """
    if incident_ts is None:
        return None
    return incident_ts - window, incident_ts + window


def describe_log_window(
    incident_ts: datetime | None,
    window: timedelta = LOG_WINDOW,
) -> str:
    """Human-readable temporal window, e.g. ``14:00:11 → 14:04:11 (±2m)``"""
    span = log_window(incident_ts, window)
    if span is None:
        return "no incident timestamp — fell back to last 500 lines"
    start, end = span
    minutes = int(window.total_seconds() // 60)
    return f"{start:%H:%M:%S} → {end:%H:%M:%S}  (±{minutes}m)"


@dataclass
class PcapInfo:
    """Parsed metadata from a network traffic capture file"""

    name: str
    container: str  # "pcap" | "pcapng" | "unknown"
    byte_order: str | None = None
    timestamp_resolution: str | None = None
    version: str | None = None
    snaplen: int | None = None
    link_type: str | None = None
    packet_count: int | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    note: str | None = None


def _pcap_timestamp(sec: int, sub: int, resolution: str) -> datetime:
    frac = sub / 1_000_000_000 if resolution == "nanosecond" else sub / 1_000_000
    return datetime.fromtimestamp(sec + frac, tz=timezone.utc)


def pcap_metadata(raw_path: str, *, max_packets: int = 5_000_000) -> PcapInfo:
    """Parse the global/record headers of a libpcap (or detect pcapng) file.

    Walks record headers without reading packet payloads, so it stays cheap on
    large captures.  ``max_packets`` bounds the walk as a runaway guard.  All
    parse failures are reported via :attr:`PcapInfo.note` rather than raised.
    """
    path = Path(raw_path)
    name = path.name or raw_path
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
            if len(header) < 24:
                return PcapInfo(name=name, container="unknown", note="file too small")

            magic = header[:4]
            if magic == _PCAPNG_MAGIC:
                return PcapInfo(
                    name=name,
                    container="pcapng",
                    note="pcapng block structure not parsed",
                )
            if magic not in _PCAP_MAGICS:
                return PcapInfo(
                    name=name, container="unknown", note="unrecognized magic number"
                )

            byte_order, resolution = _PCAP_MAGICS[magic]
            endian = "<" if byte_order == "little" else ">"
            (major, minor, _tz, _sig, snaplen, network) = struct.unpack(
                f"{endian}HHiIII", header[4:24]
            )
            link_type = _LINK_TYPES.get(network, f"LINKTYPE_{network}")

            count = 0
            first_ts: datetime | None = None
            last_ts: datetime | None = None
            while count < max_packets:
                rec = handle.read(16)
                if len(rec) < 16:
                    break
                ts_sec, ts_sub, incl_len, _orig = struct.unpack(f"{endian}IIII", rec)
                ts = _pcap_timestamp(ts_sec, ts_sub, resolution)
                if first_ts is None:
                    first_ts = ts
                last_ts = ts
                count += 1
                handle.seek(incl_len, 1)

            return PcapInfo(
                name=name,
                container="pcap",
                byte_order=byte_order,
                timestamp_resolution=resolution,
                version=f"{major}.{minor}",
                snaplen=snaplen,
                link_type=link_type,
                packet_count=count,
                first_timestamp=first_ts,
                last_timestamp=last_ts,
            )
    except OSError as exc:
        return PcapInfo(name=name, container="unknown", note=f"unreadable: {exc}")
