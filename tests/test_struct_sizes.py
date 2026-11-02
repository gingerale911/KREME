"""Test: Verify all 16 packet struct sizes match the official EA specification.

This is the most critical test — if sizes don't match, every field after the
mismatch will be decoded incorrectly. Corresponds to plan verification D1.
"""

import pytest
import numpy as np

from krem.core import PACKET_SIZES, HEADER_SIZE, PacketId
from krem.ingest import (
    DT_CAR_MOTION,
    DT_LAP_DATA,
    DT_CAR_TELEMETRY,
    DT_CAR_STATUS,
    DT_CAR_DAMAGE,
    DT_PARTICIPANT,
    DT_CAR_SETUP,
    DT_MARSHAL_ZONE,
    DT_WEATHER_FORECAST,
    DT_LAP_HISTORY,
    DT_TYRE_STINT,
    DT_TYRE_SET,
    DT_FINAL_CLASSIFICATION,
    DT_LOBBY_INFO,
    DT_TIME_TRIAL_DATA_SET,
    DT_MOTION_EX,
)


class TestStructSizes:
    """Verify per-car struct sizes (the building blocks of packet sizes)."""

    def test_car_motion_size(self):
        assert DT_CAR_MOTION.itemsize == 60

    def test_lap_data_size(self):
        assert DT_LAP_DATA.itemsize == 57

    def test_car_telemetry_size(self):
        assert DT_CAR_TELEMETRY.itemsize == 60

    def test_car_status_size(self):
        assert DT_CAR_STATUS.itemsize == 55

    def test_car_damage_size(self):
        assert DT_CAR_DAMAGE.itemsize == 46

    def test_participant_size(self):
        assert DT_PARTICIPANT.itemsize == 57

    def test_car_setup_size(self):
        assert DT_CAR_SETUP.itemsize == 50

    def test_marshal_zone_size(self):
        assert DT_MARSHAL_ZONE.itemsize == 5

    def test_weather_forecast_size(self):
        assert DT_WEATHER_FORECAST.itemsize == 8

    def test_lap_history_size(self):
        assert DT_LAP_HISTORY.itemsize == 14

    def test_tyre_stint_size(self):
        assert DT_TYRE_STINT.itemsize == 3

    def test_tyre_set_size(self):
        assert DT_TYRE_SET.itemsize == 10

    def test_final_classification_size(self):
        assert DT_FINAL_CLASSIFICATION.itemsize == 46

    def test_lobby_info_size(self):
        assert DT_LOBBY_INFO.itemsize == 42

    def test_time_trial_data_set_size(self):
        assert DT_TIME_TRIAL_DATA_SET.itemsize == 24

    def test_motion_ex_payload_size(self):
        assert DT_MOTION_EX.itemsize == 244

    def test_header_size(self):
        assert HEADER_SIZE == 29


class TestPacketSizes:
    """Verify full packet sizes = header + per-car arrays + trailers.

    These must match the EA-published sizes exactly.
    All 16 verified (plan Appendix A).
    """

    def test_motion_packet(self):
        expected = HEADER_SIZE + 22 * DT_CAR_MOTION.itemsize
        assert expected == PACKET_SIZES[PacketId.MOTION] == 1349

    def test_session_packet(self):
        assert PACKET_SIZES[PacketId.SESSION] == 753

    def test_lap_data_packet(self):
        expected = HEADER_SIZE + 22 * DT_LAP_DATA.itemsize + 2  # 2 trailer bytes
        assert expected == PACKET_SIZES[PacketId.LAP_DATA] == 1285

    def test_event_packet(self):
        # Header + 4 chars + 12 bytes (largest union: SpeedTrap)
        expected = HEADER_SIZE + 4 + 12
        assert expected == PACKET_SIZES[PacketId.EVENT] == 45

    def test_participants_packet(self):
        expected = HEADER_SIZE + 1 + 22 * DT_PARTICIPANT.itemsize
        assert expected == PACKET_SIZES[PacketId.PARTICIPANTS] == 1284

    def test_car_setups_packet(self):
        expected = HEADER_SIZE + 22 * DT_CAR_SETUP.itemsize + 4  # f32 trailer
        assert expected == PACKET_SIZES[PacketId.CAR_SETUPS] == 1133

    def test_car_telemetry_packet(self):
        expected = HEADER_SIZE + 22 * DT_CAR_TELEMETRY.itemsize + 3  # 3-byte trailer
        assert expected == PACKET_SIZES[PacketId.CAR_TELEMETRY] == 1352

    def test_car_status_packet(self):
        expected = HEADER_SIZE + 22 * DT_CAR_STATUS.itemsize
        assert expected == PACKET_SIZES[PacketId.CAR_STATUS] == 1239

    def test_final_classification_packet(self):
        expected = HEADER_SIZE + 1 + 22 * DT_FINAL_CLASSIFICATION.itemsize
        assert expected == PACKET_SIZES[PacketId.FINAL_CLASSIFICATION] == 1042

    def test_lobby_info_packet(self):
        expected = HEADER_SIZE + 1 + 22 * DT_LOBBY_INFO.itemsize
        assert expected == PACKET_SIZES[PacketId.LOBBY_INFO] == 954

    def test_car_damage_packet(self):
        expected = HEADER_SIZE + 22 * DT_CAR_DAMAGE.itemsize
        assert expected == PACKET_SIZES[PacketId.CAR_DAMAGE] == 1041

    def test_session_history_packet(self):
        expected = HEADER_SIZE + 7 + 100 * DT_LAP_HISTORY.itemsize + 8 * DT_TYRE_STINT.itemsize
        assert expected == PACKET_SIZES[PacketId.SESSION_HISTORY] == 1460

    def test_tyre_sets_packet(self):
        expected = HEADER_SIZE + 1 + 20 * DT_TYRE_SET.itemsize + 1
        assert expected == PACKET_SIZES[PacketId.TYRE_SETS] == 231

    def test_motion_ex_packet(self):
        expected = HEADER_SIZE + DT_MOTION_EX.itemsize
        assert expected == PACKET_SIZES[PacketId.MOTION_EX] == 273

    def test_time_trial_packet(self):
        expected = HEADER_SIZE + 3 * DT_TIME_TRIAL_DATA_SET.itemsize
        assert expected == PACKET_SIZES[PacketId.TIME_TRIAL] == 101

    def test_lap_positions_packet(self):
        expected = HEADER_SIZE + 2 + 50 * 22
        assert expected == PACKET_SIZES[PacketId.LAP_POSITIONS] == 1131

    def test_all_16_packets_verified(self):
        """Ensure we have sizes for exactly 16 packet types."""
        assert len(PACKET_SIZES) == 16
