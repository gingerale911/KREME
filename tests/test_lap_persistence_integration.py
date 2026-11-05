
"""Integration test: synthetic telemetry -> LapRecorder -> DuckDB."""

import struct

import numpy as np

from krem.core import PACKET_FORMAT, GAME_YEAR, PACKET_SIZES, PacketId
from krem.ingest import decode_packet, DT_LAP_HISTORY
from krem.pipeline.lap_recorder import LapRecorder
from krem.storage import LapDatabase, LapRepository
from krem.storage.lap_writer import LapStorageWriter


def make(pid, frame, uid=2**60 + 123, player=0, at=None):
    header = struct.pack(
        "<HBBBBBQfIIBB",
        PACKET_FORMAT,
        GAME_YEAR,
        1,
        0,
        1,
        pid,
        uid,
        frame / 60 if at is None else at,
        frame,
        frame,
        player,
        255,
    )

    packet = decode_packet(
        header + bytes(PACKET_SIZES[pid] - len(header))
    )

    if "cars" in packet.data:
        packet.data["cars"] = packet.data["cars"].copy()

    return packet


def pair(frame, lap=1, elapsed=0, distance=0, last=0):
    lap_packet = make(PacketId.LAP_DATA, frame)
    car = lap_packet.data["cars"][0]

    car["currentLapNum"] = lap
    car["currentLapTimeInMS"] = elapsed
    car["lapDistance"] = distance
    car["currentLapInvalid"] = 0
    car["lastLapTimeInMS"] = last
    car["driverStatus"] = 1
    car["sector1TimeMSPart"] = 200 if elapsed >= 200 else 0
    car["sector2TimeMSPart"] = 200 if elapsed >= 400 else 0

    telemetry = make(PacketId.CAR_TELEMETRY, frame)
    telemetry.data["cars"][0]["speed"] = 180
    telemetry.data["cars"][0]["throttle"] = 1.0

    return lap_packet, telemetry


def create_recorder():
    recorder = LapRecorder()

    session = make(PacketId.SESSION, 0)
    session.data["trackId"] = 0
    session.data["trackLength"] = 100

    recorder.ingest(session)

    return recorder


def generate_completed_lap(recorder):
    # Generate six synthetic telemetry frames.
    for i in range(6):
        for packet in pair(
            i + 1,
            elapsed=i * 100,
            distance=i * 18,
        ):
            recorder.ingest(packet)

    # Crossing into lap 2 completes lap 1.
    for packet in pair(
        7,
        lap=2,
        last=600,
    ):
        recorder.ingest(packet)

    recorder.flush(force=True)

    return recorder.records[-1]


def test_synthetic_telemetry_is_saved_to_duckdb(tmp_path):
    database_path = tmp_path / "integration.duckdb"

    database = LapDatabase(str(database_path))
    repository = LapRepository(database)
    writer = LapStorageWriter(repository)

    try:
        recorder = create_recorder()

        # Connect the recorder to the asynchronous database writer.
        recorder.storage_writer = writer

        # Generate and complete a synthetic lap.
        original_lap = generate_completed_lap(recorder)

        # Wait until the background writer has persisted it.
        writer.flush()

        # Retrieve the saved lap using its original recorder ID.
        saved_lap = repository.get_lap(original_lap["id"])

        assert saved_lap is not None
        assert saved_lap["lapNumber"] == 1
        assert saved_lap["lapTimeMs"] == 600
        assert saved_lap["sampleCount"] == 6

        # Verify the session was created.
        sessions = repository.get_sessions()

        assert len(sessions) == 1
        assert sessions[0]["lapCount"] == 1

        # Verify the actual telemetry trace.
        trace = repository.get_lap_trace(original_lap["id"])

        assert trace is not None
        assert len(trace) == 6

        assert trace[0]["speed"] == 180.0
        assert trace[0]["throttle"] == 1.0
        assert trace[-1]["elapsedTimeMs"] == 500

        print("\nSynthetic lap successfully persisted!")
        print(f"Database: {database_path}")
        print(f"Lap ID: {original_lap['id']}")
        print(f"Samples saved: {len(trace)}")

    finally:
        writer.close()
        database.close()
