from __future__ import annotations

import struct
import time

import pytest

from krem.core import GAME_YEAR, PACKET_FORMAT, PacketId, PACKET_SIZES
from krem.ingest import decode_packet
from krem.ingest.recorder import Recorder, ReplayReader


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
