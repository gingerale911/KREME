"""KREM UDP protocol — asyncio DatagramProtocol for receiving F1 25 telemetry.

This is the entry point for all UDP data. It:
1. Guards each datagram (format/size check)
2. Decodes valid packets via numpy
3. Updates live state
4. Feeds the raw recorder
5. Tracks packet statistics

Concurrency model (plan §4.3):
- Event loop: receive → guard → decode → update live state (no disk I/O)
- Recorder uses a background thread queue
- Heavy processing (lap finalization, DuckDB) in worker thread/process
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from krem.ingest.guard import guard, GuardResult, RejectReason
from krem.ingest import decode_header, decode_packet, DecodedPacket, PacketHeader
from krem.ingest.recorder import Recorder
from krem.core import PACKET_SIZES, PacketId, CONSUMED_PACKET_IDS

logger = logging.getLogger("krem.protocol")


DEFAULT_STATS_PATH = Path(__file__).resolve().parents[2] / "data" / "ingest_stats.json"


@dataclass
class PacketStats:
    """Running statistics for monitoring."""
    total_received: int = 0
    total_accepted: int = 0
    total_rejected: int = 0
    reject_reasons: dict[str, int] = field(default_factory=dict)
    packets_per_type: dict[int, int] = field(default_factory=dict)
    last_frame_id: int = 0
    frame_gaps: int = 0
    bytes_received: int = 0
    bytes_accepted: int = 0
    cumulative_received: int = 0
    cumulative_accepted: int = 0
    cumulative_rejected: int = 0
    cumulative_bytes_received: int = 0
    cumulative_bytes_accepted: int = 0
    persist_path: Path | None = None
    start_time: float = field(default_factory=time.monotonic)
    last_packet_time: float | None = None
    last_accepted_time: float | None = None
    _last_flush_time: float = field(default_factory=time.monotonic, repr=False, compare=False)
    _dirty: bool = field(default=False, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.persist_path is not None:
            self._load_cumulative()

    def _load_cumulative(self) -> None:
        if self.persist_path is None or not self.persist_path.is_file():
            return
        try:
            data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            self.cumulative_received = int(data.get("packetsReceived", 0))
            self.cumulative_accepted = int(data.get("packetsAccepted", 0))
            self.cumulative_rejected = int(data.get("packetsRejected", 0))
            self.cumulative_bytes_received = int(data.get("bytesReceived", 0))
            self.cumulative_bytes_accepted = int(data.get("bytesAccepted", 0))
        except Exception:
            logger.debug("Failed to load cumulative stats from %s", self.persist_path)

    def flush(self, force: bool = True) -> None:
        """Persist cumulative counters to disk if configured."""
        if self.persist_path is None:
            return
        with self._lock:
            now = time.monotonic()
            if not self._dirty or (not force and now - self._last_flush_time < 5.0):
                return
            payload = {
                "packetsReceived": self.cumulative_received,
                "packetsAccepted": self.cumulative_accepted,
                "packetsRejected": self.cumulative_rejected,
                "bytesReceived": self.cumulative_bytes_received,
                "bytesAccepted": self.cumulative_bytes_accepted,
            }
            self._dirty = False
            self._last_flush_time = now
        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.persist_path)
        except Exception:
            logger.debug("Failed to persist cumulative stats to %s", self.persist_path)

    @property
    def packets_per_second(self) -> float:
        with self._lock:
            elapsed = time.monotonic() - self.start_time
            return self.total_received / max(elapsed, 0.001)

    @property
    def bytes_per_second(self) -> float:
        with self._lock:
            elapsed = time.monotonic() - self.start_time
            return self.bytes_received / max(elapsed, 0.001)

    def record_received(self, size: int) -> None:
        with self._lock:
            self.total_received += 1
            self.bytes_received += size
            self.cumulative_received += 1
            self.cumulative_bytes_received += size
            self.last_packet_time = time.monotonic()
            self._dirty = True

    def record_rejected(self, reason: str) -> None:
        with self._lock:
            self.total_rejected += 1
            self.cumulative_rejected += 1
            self.reject_reasons[reason] = self.reject_reasons.get(reason, 0) + 1
            self._dirty = True

    def record_accepted(self, packet_id: int | None = None, size: int = 0) -> None:
        with self._lock:
            self.total_accepted += 1
            self.bytes_accepted += size
            self.cumulative_accepted += 1
            self.cumulative_bytes_accepted += size
            self.last_accepted_time = time.monotonic()
            self._dirty = True
            if packet_id is not None:
                self.packets_per_type[packet_id] = (
                    self.packets_per_type.get(packet_id, 0) + 1
                )

    def record_frame(self, frame_id: int) -> None:
        with self._lock:
            if self.last_frame_id > 0:
                gap = frame_id - self.last_frame_id
                if gap > 1:
                    self.frame_gaps += gap - 1
            self.last_frame_id = frame_id

    def snapshot(self) -> dict[str, Any]:
        """Return a consistent, JSON-safe copy of packet and connection stats."""
        self.flush(force=False)
        with self._lock:
            now = time.monotonic()
            age = (
                round(now - self.last_accepted_time, 2)
                if self.last_accepted_time is not None
                else None
            )
            datagram_age = (
                round(now - self.last_packet_time, 2)
                if self.last_packet_time is not None
                else None
            )
            elapsed = max(now - self.start_time, 0.001)
            return {
                "connected": age is not None and age <= 2.0,
                "packetsReceived": self.total_received,
                "packetsAccepted": self.total_accepted,
                "packetsRejected": self.total_rejected,
                "rejectReasons": dict(self.reject_reasons),
                "packetsByType": {
                    str(packet_id): count
                    for packet_id, count in self.packets_per_type.items()
                },
                "frameGaps": self.frame_gaps,
                "packetsPerSecond": round(self.total_received / elapsed, 1),
                "bytesReceived": self.bytes_received,
                "bytesAccepted": self.bytes_accepted,
                "cumulativePacketsReceived": self.cumulative_received,
                "cumulativePacketsAccepted": self.cumulative_accepted,
                "cumulativePacketsRejected": self.cumulative_rejected,
                "cumulativeBytesReceived": self.cumulative_bytes_received,
                "cumulativeBytesAccepted": self.cumulative_bytes_accepted,
                "bytesPerSecond": round(self.bytes_received / elapsed, 0),
                "lastPacketAgeSeconds": age,
                "lastDatagramAgeSeconds": datagram_age,
            }


# Type for packet callbacks
PacketCallback = Callable[[DecodedPacket], None]


class F1UDPProtocol(asyncio.DatagramProtocol):
    """Asyncio protocol for receiving F1 25 UDP datagrams.

    Usage:
        protocol = F1UDPProtocol(
            on_packet=my_handler,
            recorder=my_recorder,
        )
        transport, _ = await loop.create_datagram_endpoint(
            lambda: protocol,
            local_addr=("0.0.0.0", 20777),
        )
    """

    def __init__(
        self,
        on_packet: PacketCallback | None = None,
        recorder: Recorder | None = None,
        persist_stats: bool = False,
        stats_path: Path | None = None,
    ) -> None:
        self._on_packet = on_packet
        self._recorder = recorder
        self._transport: asyncio.DatagramTransport | None = None
        resolved_path = stats_path if stats_path is not None else (DEFAULT_STATS_PATH if persist_stats else None)
        self.stats = PacketStats(persist_path=resolved_path)
        self._wrong_format_logged = False

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self._transport = transport
        logger.info("UDP listener ready")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle an incoming UDP datagram — the hot path."""
        self.stats.record_received(len(data))

        # 1. Guard
        result = guard(data)
        if not result.accepted:
            reason_name = result.reject_reason.name if result.reject_reason else "UNKNOWN"
            self.stats.record_rejected(reason_name)
            # Log wrong-format banner once
            if (
                result.reject_reason in (RejectReason.WRONG_FORMAT, RejectReason.WRONG_YEAR)
                and not self._wrong_format_logged
            ):
                logger.warning(
                    "Game is sending UDP format %d (year %d). "
                    "Set UDP Format to 2025 in the game's UDP settings.",
                    result.detected_format,
                    result.detected_year,
                )
                self._wrong_format_logged = True
            return

        self.stats.record_accepted(result.packet_id, len(data))

        # 2. Record raw (non-blocking, background thread)
        if self._recorder is not None:
            self._recorder.write(data)

        # 3. Decode
        try:
            packet = decode_packet(data)
        except Exception:
            logger.exception("Decode error for packet %d", result.packet_id)
            return

        if packet is None:
            return

        # 4. Track frame gaps (plan §4.3)
        if result.packet_id in {PacketId.MOTION, PacketId.LAP_DATA, PacketId.CAR_TELEMETRY}:
            self.stats.record_frame(packet.header.overall_frame_identifier)

        # 5. Dispatch to callback
        if self._on_packet is not None:
            try:
                self._on_packet(packet)
            except Exception:
                logger.exception("Callback error for packet %d", result.packet_id)

    def error_received(self, exc: Exception) -> None:
        logger.error("UDP error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        self.stats.flush(force=True)
        logger.info("UDP connection lost: %s", exc)
