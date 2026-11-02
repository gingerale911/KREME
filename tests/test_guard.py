"""Test: Guard validation for incoming UDP datagrams."""

from __future__ import annotations

import struct
import pytest

from krem.core import PACKET_FORMAT, GAME_YEAR, HEADER_SIZE, PACKET_SIZES, PacketId
from krem.ingest.guard import guard, RejectReason


def _make_header(
    fmt: int = PACKET_FORMAT,
    year: int = GAME_YEAR,
    packet_id: int = 0,
    total_size: int | None = None,
) -> bytes:
    """Create a fake datagram with the correct header and padding."""
    # Build header bytes
    header = struct.pack(
        "<HBBBBBQfIIBB",
        fmt,      # packetFormat
        year,     # gameYear
        1,        # gameMajorVersion
        0,        # gameMinorVersion
        1,        # packetVersion
        packet_id,  # packetId
        12345,    # sessionUID
        1.0,      # sessionTime
        100,      # frameIdentifier
        100,      # overallFrameIdentifier
        0,        # playerCarIndex
        255,      # secondaryPlayerCarIndex
    )
    if total_size is None:
        total_size = PACKET_SIZES.get(packet_id, HEADER_SIZE)
    # Pad to total size
    padding = b"\x00" * max(0, total_size - len(header))
    return header + padding


class TestGuard:
    def test_accept_valid_motion_packet(self):
        data = _make_header(packet_id=PacketId.MOTION)
        result = guard(data)
        assert result.accepted is True
        assert result.packet_id == PacketId.MOTION

    def test_accept_all_packet_types(self):
        for pid, size in PACKET_SIZES.items():
            data = _make_header(packet_id=pid)
            result = guard(data)
            assert result.accepted is True, f"Packet {pid} rejected"

    def test_reject_too_short(self):
        result = guard(b"\x00" * 10)
        assert result.accepted is False
        assert result.reject_reason == RejectReason.TOO_SHORT

    def test_reject_empty(self):
        result = guard(b"")
        assert result.accepted is False
        assert result.reject_reason == RejectReason.TOO_SHORT

    def test_reject_wrong_format(self):
        data = _make_header(fmt=2026)
        result = guard(data)
        assert result.accepted is False
        assert result.reject_reason == RejectReason.WRONG_FORMAT
        assert result.detected_format == 2026

    def test_reject_wrong_year(self):
        data = _make_header(year=26)
        result = guard(data)
        assert result.accepted is False
        assert result.reject_reason == RejectReason.WRONG_YEAR

    def test_reject_unknown_packet_id(self):
        # Use an invalid packet ID with just header size
        header = struct.pack(
            "<HBBBBBQfIIBB",
            PACKET_FORMAT, GAME_YEAR, 1, 0, 1,
            99,  # bogus packet ID
            12345, 1.0, 100, 100, 0, 255,
        )
        result = guard(header)
        assert result.accepted is False
        assert result.reject_reason == RejectReason.UNKNOWN_PACKET_ID

    def test_reject_size_mismatch(self):
        # Correct header but wrong total length
        data = _make_header(packet_id=PacketId.MOTION, total_size=100)
        result = guard(data)
        assert result.accepted is False
        assert result.reject_reason == RejectReason.SIZE_MISMATCH

    def test_detected_format_and_year_on_rejection(self):
        data = _make_header(fmt=2026, year=26)
        result = guard(data)
        assert result.detected_format == 2026
        assert result.detected_year == 26
