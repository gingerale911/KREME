"""Test: Decoder — verify packet decoding with synthetic data."""

import struct
import numpy as np
import pytest

from krem.core import PACKET_FORMAT, GAME_YEAR, PACKET_SIZES, PacketId, HEADER_SIZE
from krem.ingest import decode_packet, decode_header, PacketHeader
from krem.ingest import (
    DT_CAR_MOTION,
    DT_LAP_DATA,
    DT_CAR_TELEMETRY,
    DT_CAR_STATUS,
    DT_CAR_DAMAGE,
)


def _make_packet(packet_id: int, payload: bytes = b"") -> bytes:
    """Build a complete packet with header + payload, padded to correct size."""
    header = struct.pack(
        "<HBBBBBQfIIBB",
        PACKET_FORMAT, GAME_YEAR, 1, 0, 1,
        packet_id,
        0xDEADBEEF,  # sessionUID
        42.5,         # sessionTime
        1000,         # frameIdentifier
        1000,         # overallFrameIdentifier
        0,            # playerCarIndex
        255,          # secondaryPlayerCarIndex
    )
    total_size = PACKET_SIZES[packet_id]
    if payload:
        padding = b"\x00" * max(0, total_size - len(header) - len(payload))
        return header + payload + padding
    else:
        padding = b"\x00" * (total_size - len(header))
        return header + padding


class TestHeaderDecoding:
    def test_decode_header_fields(self):
        data = _make_packet(PacketId.MOTION)
        header = decode_header(data)
        assert header.packet_format == PACKET_FORMAT
        assert header.game_year == GAME_YEAR
        assert header.packet_id == PacketId.MOTION
        assert header.session_uid == 0xDEADBEEF
        assert abs(header.session_time - 42.5) < 0.01
        assert header.frame_identifier == 1000
        assert header.overall_frame_identifier == 1000
        assert header.player_car_index == 0
        assert header.secondary_player_car_index == 255


class TestMotionDecoding:
    def test_decode_motion_car_count(self):
        data = _make_packet(PacketId.MOTION)
        packet = decode_packet(data)
        assert packet is not None
        assert len(packet.data["cars"]) == 22

    def test_decode_motion_with_position(self):
        # Put known position in car[0]
        data = bytearray(_make_packet(PacketId.MOTION))
        # Write world position X at offset HEADER_SIZE (first field of first car)
        struct.pack_into("<f", data, HEADER_SIZE, 100.5)
        packet = decode_packet(bytes(data))
        assert abs(float(packet.data["cars"][0]["worldPositionX"]) - 100.5) < 0.01


class TestLapDataDecoding:
    def test_decode_lap_data_car_count(self):
        data = _make_packet(PacketId.LAP_DATA)
        packet = decode_packet(data)
        assert len(packet.data["cars"]) == 22

    def test_decode_lap_data_trailer(self):
        data = bytearray(_make_packet(PacketId.LAP_DATA))
        # Write trailer values
        trailer_offset = HEADER_SIZE + 22 * DT_LAP_DATA.itemsize
        data[trailer_offset] = 3      # timeTrialPBCarIdx
        data[trailer_offset + 1] = 7  # timeTrialRivalCarIdx
        packet = decode_packet(bytes(data))
        assert packet.data["timeTrialPBCarIdx"] == 3
        assert packet.data["timeTrialRivalCarIdx"] == 7


class TestEventDecoding:
    def test_decode_session_started(self):
        data = bytearray(_make_packet(PacketId.EVENT))
        # Write event code "SSTA" at header offset
        data[HEADER_SIZE:HEADER_SIZE + 4] = b"SSTA"
        packet = decode_packet(bytes(data))
        assert packet.data["code"] == "SSTA"

    def test_decode_fastest_lap(self):
        data = bytearray(_make_packet(PacketId.EVENT))
        data[HEADER_SIZE:HEADER_SIZE + 4] = b"FTLP"
        data[HEADER_SIZE + 4] = 5  # vehicleIdx
        struct.pack_into("<f", data, HEADER_SIZE + 5, 78.123)  # lapTime
        packet = decode_packet(bytes(data))
        assert packet.data["code"] == "FTLP"
        assert packet.data["vehicleIdx"] == 5
        assert abs(packet.data["lapTime"] - 78.123) < 0.01

    def test_decode_safety_car(self):
        data = bytearray(_make_packet(PacketId.EVENT))
        data[HEADER_SIZE:HEADER_SIZE + 4] = b"SCAR"
        data[HEADER_SIZE + 4] = 1  # full SC
        data[HEADER_SIZE + 5] = 0  # deployed
        packet = decode_packet(bytes(data))
        assert packet.data["code"] == "SCAR"
        assert packet.data["safetyCarType"] == 1


class TestTelemetryDecoding:
    def test_decode_telemetry_car_count(self):
        data = _make_packet(PacketId.CAR_TELEMETRY)
        packet = decode_packet(data)
        assert len(packet.data["cars"]) == 22

    def test_decode_telemetry_speed(self):
        data = bytearray(_make_packet(PacketId.CAR_TELEMETRY))
        # Write speed for car 0 — first field is u16
        struct.pack_into("<H", data, HEADER_SIZE, 312)
        packet = decode_packet(bytes(data))
        assert int(packet.data["cars"][0]["speed"]) == 312


class TestCarStatusDecoding:
    def test_decode_status_car_count(self):
        data = _make_packet(PacketId.CAR_STATUS)
        packet = decode_packet(data)
        assert len(packet.data["cars"]) == 22


class TestCarDamageDecoding:
    def test_decode_damage_car_count(self):
        data = _make_packet(PacketId.CAR_DAMAGE)
        packet = decode_packet(data)
        assert len(packet.data["cars"]) == 22


class TestSessionDecoding:
    def test_decode_session_sector_boundaries(self):
        data = bytearray(_make_packet(PacketId.SESSION))
        struct.pack_into("<ff", data, len(data) - 8, 1234.5, 2456.75)

        packet = decode_packet(bytes(data))

        assert packet.data["sector2LapDistanceStart"] == pytest.approx(1234.5)
        assert packet.data["sector3LapDistanceStart"] == pytest.approx(2456.75)
        assert len(packet.data["weekendStructure"]) == 12


class TestAllPacketsDecode:
    """Verify that every packet type can be decoded without error from zeroed data."""

    @pytest.mark.parametrize("packet_id", list(PACKET_SIZES.keys()))
    def test_decode_zeroed_packet(self, packet_id):
        data = _make_packet(packet_id)
        packet = decode_packet(data)
        assert packet is not None
        assert packet.header.packet_id == packet_id
