"""Live snapshots must distinguish missing, stale and real zero values."""
import struct
from unittest.mock import patch

from krem.core import PACKET_FORMAT, GAME_YEAR, PACKET_SIZES, PacketId
from krem.ingest import decode_packet
from krem.pipeline import LiveState


def packet(pid, uid=1, player=0):
    header = struct.pack('<HBBBBBQfIIBB', PACKET_FORMAT, GAME_YEAR, 1, 0, 1,
                         pid, uid, 1.0, 1, 1, player, 255)
    return decode_packet(header + bytes(PACKET_SIZES[pid] - len(header)))


def test_missing_values_are_null():
    snap = LiveState().snapshot()
    assert snap['player']['speed'] is None
    assert snap['player']['invalid'] is None
    assert snap['session']['trackTemp'] is None
    assert snap['player']['tyres']['ageLaps'] is None
    assert snap['freshness']['damage']['state'] == 'missing'


def test_real_zero_is_valid_and_temperature_channels_stay_separate():
    state = LiveState()
    telemetry = packet(PacketId.CAR_TELEMETRY)
    telemetry.data['cars'] = telemetry.data['cars'].copy()
    car = telemetry.data['cars'][0]
    car['throttle'] = 1.0
    car['tyresSurfaceTemperature'] = [80, 81, 82, 83]
    car['tyresInnerTemperature'] = [90, 91, 92, 93]
    car['brakesTemperature'] = [400, 410, 420, 430]
    state.update(telemetry)
    state.update(packet(PacketId.CAR_DAMAGE))
    snap = state.snapshot()
    assert snap['player']['throttle'] == 1.0
    assert snap['player']['brake'] == 0.0
    assert snap['player']['tyres']['wearPct'] == [0, 0, 0, 0]
    assert snap['player']['tyres']['surfaceTempC'] == [80, 81, 82, 83]
    assert snap['player']['tyres']['brakeTempC'] == [400, 410, 420, 430]


def test_other_packets_do_not_refresh_stale_damage_and_recovery_works():
    state = LiveState()
    with patch('krem.pipeline.time.monotonic', return_value=10):
        state.update(packet(PacketId.CAR_DAMAGE))
        state.update(packet(PacketId.CAR_TELEMETRY))
    with patch('krem.pipeline.time.monotonic', return_value=12.1):
        state.update(packet(PacketId.CAR_TELEMETRY))
        snap = state.snapshot()
        assert snap['freshness']['telemetry']['state'] == 'fresh'
        assert snap['freshness']['damage']['state'] == 'stale'
        assert snap['player']['tyres']['wearPct'] is None
        assert snap['player']['damage']['frontLeftWingDamage'] is None
        assert snap['player']['speed'] == 0
        state.update(packet(PacketId.CAR_DAMAGE))
        assert state.snapshot()['player']['tyres']['wearPct'] == [0, 0, 0, 0]
    with patch('krem.pipeline.time.monotonic', return_value=15):
        assert state.snapshot()['player']['speed'] is None


def test_session_change_on_any_packet_clears_previous_car():
    state = LiveState()
    state.update(packet(PacketId.CAR_DAMAGE, uid=1))
    state.update(packet(PacketId.CAR_TELEMETRY, uid=2))
    snap = state.snapshot()
    assert snap['session']['uid'] == 2
    assert snap['player']['tyres']['wearPct'] is None
    assert snap['freshness']['damage']['state'] == 'missing'


def test_player_change_and_invalid_player_do_not_reuse_old_values():
    state = LiveState()
    state.update(packet(PacketId.CAR_DAMAGE))
    state.update(packet(PacketId.CAR_TELEMETRY, player=1))
    assert state.snapshot()['player']['tyres']['wearPct'] is None
    state.update(packet(PacketId.CAR_TELEMETRY, player=255))
    assert state.snapshot()['player']['speed'] is None


def test_fallback_page_accepts_missing_pedals():
    from krem.server import _pedal_text
    assert _pedal_text(None) == '—'
    assert _pedal_text(1.0) == '100%'
