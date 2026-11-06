import time
import struct
from krem.core import PACKET_FORMAT, GAME_YEAR, PACKET_SIZES, PacketId
from krem.ingest import decode_packet
from krem.pipeline import LiveState
from krem.server import create_app
from fastapi.testclient import TestClient


def make_packet(pid, uid=1, player=0):
    header = struct.pack(
        '<HBBBBBQfIIBB',
        PACKET_FORMAT,
        GAME_YEAR,
        1,
        0,
        1,
        pid,
        uid,
        1.0,
        1,
        1,
        player,
        255,
    )
    return decode_packet(header + bytes(PACKET_SIZES[pid] - len(header)))


def test_snapshot_include_laps_performance():
    state = LiveState()
    # Populate multiple simulated completed laps with thousands of telemetry samples
    for lap_idx in range(5):
        samples = [
            {"dist": i, "speed": 220, "throttle": 1.0, "brake": 0.0}
            for i in range(3000)
        ]
        state.lap_recorder.records.append(
            {"lap": lap_idx + 1, "samples": samples, "valid": True}
        )

    # With include_laps=False (used by WebSocket 30Hz stream)
    t0 = time.perf_counter()
    snap_live = state.snapshot(include_laps=False)
    elapsed_live = time.perf_counter() - t0

    # Live snapshot should be nearly instantaneous (< 5ms) and laps list should be empty
    assert elapsed_live < 0.01, f"Live snapshot took too long: {elapsed_live*1000:.2f}ms"
    assert snap_live["laps"] == []

    # With include_laps=True (used by REST /api/snapshot)
    snap_full = state.snapshot(include_laps=True)
    assert len(snap_full["laps"]) == 5


def test_db_endpoints_do_not_block_thread():
    state = LiveState()
    app = create_app(state)
    client = TestClient(app)

    # Verify standard endpoints return expected schemas without hanging
    res = client.get("/api/circuits")
    assert res.status_code == 200

    res = client.get("/api/db/engine")
    assert res.status_code == 200
    assert "mode" in res.json()


def test_player_tyres_visual_compound():
    state = LiveState()
    status_pkt = make_packet(PacketId.CAR_STATUS)
    status_pkt.data["cars"] = status_pkt.data["cars"].copy()
    status_pkt.data["cars"][0]["visualTyreCompound"] = 16  # Soft
    state.update(status_pkt)
    snap = state.snapshot()
    assert snap["player"]["tyres"]["visualCompoundName"] == "Soft"
