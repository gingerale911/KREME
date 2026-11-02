"""KREM guard — validates incoming datagrams before decoding.

Guard rule (plan §2.1):
Accept only if m_packetFormat == 2025 AND m_gameYear == 25
AND datagram length matches the published size for its m_packetId.
Otherwise drop and flag the reason.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from krem.core import (
    HEADER_FORMAT,
    HEADER_SIZE,
    PACKET_FORMAT,
    GAME_YEAR,
    PACKET_SIZES,
    HeaderField,
)


class RejectReason(Enum):
    TOO_SHORT = auto()         # shorter than header
    WRONG_FORMAT = auto()      # m_packetFormat != 2025
    WRONG_YEAR = auto()        # m_gameYear != 25
    UNKNOWN_PACKET_ID = auto() # packet ID not in our table
    SIZE_MISMATCH = auto()     # length != published size


@dataclass(frozen=True)
class GuardResult:
    """Result of validating a datagram."""
    accepted: bool
    packet_id: int = -1
    reject_reason: RejectReason | None = None
    reject_detail: str = ""
    # For accepted packets, the raw format/year for banner display
    detected_format: int = 0
    detected_year: int = 0


# Pre-compute header field offsets for minimal parsing
_FMT_OFFSET: Final[int] = 0                    # u16 packetFormat
_YEAR_OFFSET: Final[int] = 2                    # u8 gameYear
_PACKET_ID_OFFSET: Final[int] = 6              # u8 packetId (after format+year+major+minor+version)


def guard(datagram: bytes) -> GuardResult:
    """Validate a raw UDP datagram.

    Returns a GuardResult indicating whether to accept or reject.
    Designed to be as fast as possible — minimal parsing, no allocation.
    """
    length = len(datagram)

    # 1. Must be at least header-sized
    if length < HEADER_SIZE:
        return GuardResult(
            accepted=False,
            reject_reason=RejectReason.TOO_SHORT,
            reject_detail=f"Datagram too short: {length} < {HEADER_SIZE}",
        )

    # 2. Extract format, year, and packet ID with minimal parsing
    fmt = int.from_bytes(datagram[0:2], "little")
    year = datagram[2]
    packet_id = datagram[6]

    # 3. Check format
    if fmt != PACKET_FORMAT:
        return GuardResult(
            accepted=False,
            packet_id=packet_id,
            reject_reason=RejectReason.WRONG_FORMAT,
            reject_detail=f"Expected format {PACKET_FORMAT}, got {fmt}",
            detected_format=fmt,
            detected_year=year,
        )

    # 4. Check year
    if year != GAME_YEAR:
        return GuardResult(
            accepted=False,
            packet_id=packet_id,
            reject_reason=RejectReason.WRONG_YEAR,
            reject_detail=f"Expected year {GAME_YEAR}, got {year}",
            detected_format=fmt,
            detected_year=year,
        )

    # 5. Check packet ID is known
    expected_size = PACKET_SIZES.get(packet_id)
    if expected_size is None:
        return GuardResult(
            accepted=False,
            packet_id=packet_id,
            reject_reason=RejectReason.UNKNOWN_PACKET_ID,
            reject_detail=f"Unknown packet ID: {packet_id}",
            detected_format=fmt,
            detected_year=year,
        )

    # 6. Check datagram length matches published size
    if length != expected_size:
        return GuardResult(
            accepted=False,
            packet_id=packet_id,
            reject_reason=RejectReason.SIZE_MISMATCH,
            reject_detail=f"Packet {packet_id}: expected {expected_size} bytes, got {length}",
            detected_format=fmt,
            detected_year=year,
        )

    # Accepted
    return GuardResult(
        accepted=True,
        packet_id=packet_id,
        detected_format=fmt,
        detected_year=year,
    )
