from __future__ import annotations

import struct
import time
from types import SimpleNamespace

import pytest

from krem.core import GAME_YEAR, PACKET_FORMAT, PacketId, PACKET_SIZES
from krem.ingest import decode_packet
from krem.ingest.recorder import Recorder, ReplayReader
from krem.pipeline import LiveState


def _event_packet(frame: int) -> bytes:
    header = struct.pack(
        "<HBBBBBQfIIBB",
        PACKET_FORMAT,
        GAME_YEAR,
        1,
        0,
        1,
        PacketId.EVENT,
        123,
        frame / 60,
        frame,
        frame,
        0,
        255,
    )
    payload = b"SSTA" + bytes(PACKET_SIZES[PacketId.EVENT] - len(header) - 4)
    return header + payload


def test_recorder_replays_identical_decodable_stream(tmp_path):
    datagrams = [_event_packet(frame) for frame in range(1, 4)]
    recorder = Recorder(tmp_path)
    capture_path = recorder.start(session_uid=123)
    try:
        for datagram in datagrams:
            assert recorder.write(datagram)
            time.sleep(0.002)
    finally:
        recorder.stop()

    replayed = ReplayReader(capture_path).packets()
    assert [datagram for _, datagram in replayed] == datagrams
    assert [packet.header.overall_frame_identifier for _, data in replayed
            if (packet := decode_packet(data)) is not None] == [1, 2, 3]
    assert [timestamp for timestamp, _ in replayed] == sorted(
        timestamp for timestamp, _ in replayed
    )
    assert recorder.packet_count == len(datagrams)
    assert recorder.dropped_packets == 0


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (b"not a capture", "supported"),
        (b"F1UDP\x01\x00\x00\x01", "record header"),
        (b"F1UDP\x01\x00\x00" + struct.pack("<Id", 4, 0.0) + b"ab", "datagram"),
        (b"F1UDP\x01\x00\x00" + struct.pack("<Id", 65_508, 0.0), "length"),
        (b"F1UDP\x01\x00\x00" + struct.pack("<Id", 0, float("nan")), "timestamp"),
    ],
)
def test_replay_rejects_malformed_capture(tmp_path, contents, message):
    capture_path = tmp_path / "broken.f1udp"
    capture_path.write_bytes(contents)

    with pytest.raises(ValueError, match=message):
        ReplayReader(capture_path).packets()


def test_write_requires_started_recorder(tmp_path):
    with pytest.raises(RuntimeError, match="started"):
        Recorder(tmp_path).write(b"packet")


def test_live_state_records_lap_history():
    state = LiveState()
    base_header = {
        "session_uid": 1,
        "session_time": 12.5,
        "overall_frame_identifier": 42,
        "player_car_index": 0,
    }

    def lap_car(current_lap: int, last_lap_ms: int, current_lap_ms: int, sector1_ms: int, sector2_ms: int):
        return {
            "lapDistance": 100.0,
            "totalDistance": 1200.0,
            "lastLapTimeInMS": last_lap_ms,
            "currentLapTimeInMS": current_lap_ms,
            "sector1TimeMinutesPart": sector1_ms // 60_000,
            "sector1TimeMSPart": sector1_ms % 60_000,
            "sector2TimeMinutesPart": sector2_ms // 60_000,
            "sector2TimeMSPart": sector2_ms % 60_000,
            "sector": 1,
            "carPosition": 1,
            "currentLapNum": current_lap,
            "currentLapInvalid": 0,
            "pitStatus": 0,
            "driverStatus": 0,
            "penalties": 0,
        }

    lap_packet = SimpleNamespace(
        header=SimpleNamespace(packet_id=PacketId.LAP_DATA, **base_header),
        data={"cars": [lap_car(1, 0, 52_000, 18_000, 16_000)]},
    )
    telemetry_packet = SimpleNamespace(
        header=SimpleNamespace(packet_id=PacketId.CAR_TELEMETRY, **base_header),
        data={"cars": [{
            "speed": 180,
            "throttle": 0.8,
            "brake": 0.1,
            "steer": 0.1,
            "gear": 3,
            "engineRPM": 8300,
            "drs": 0,
        }]},
    )
    next_lap_packet = SimpleNamespace(
        header=SimpleNamespace(packet_id=PacketId.LAP_DATA, **base_header),
        data={"cars": [lap_car(2, 52_000, 41_000, 17_000, 15_000)]},
    )

    state.update(lap_packet)
    state.update(telemetry_packet)
    state.update(next_lap_packet)

    laps = state.lap_history_snapshot()
    assert laps[-1]["lap"] == 1
    assert laps[-1]["lapTimeMs"] == 52_000
    assert laps[-1]["avgSpeedKph"] == 180.0
