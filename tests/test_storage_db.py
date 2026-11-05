"""Unit tests for SQLite database manager and DuckDB query acceleration."""

import pytest
from krem.storage import DatabaseManager


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_krem.db"
    return DatabaseManager(db_path=db_file)


def test_schema_initialization(temp_db):
    with temp_db._get_sqlite_connection() as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        assert "circuits" in tables
        assert "circuit_sectors" in tables
        assert "circuit_corners" in tables
        assert "track_benchmarks" in tables
        assert "benchmark_corners" in tables


def test_upsert_and_get_circuit(temp_db):
    temp_db.upsert_circuit(
        track_id=31,
        slug="f1-25_las-vegas",
        name="Las Vegas",
        track_length_m=6200.0,
        orientation=0.0,
        sf_line={"pos": [375.4, 875.4], "heading": 2.42},
        racing_line=[[375.4, 875.4], [380.0, 870.0]],
        left_edge=[[370.0, 875.4]],
        right_edge=[[380.0, 875.4]],
        sectors=[{"sector": 1, "lap_dist_m": 0.0}, {"sector": 2, "lap_dist_m": 1703.8}],
        sections=[{"turn": "1", "name": "Turn 1", "start_m": 10.0, "apex_m": 40.0, "end_m": 80.0}],
    )

    circuit = temp_db.get_circuit(31)
    assert circuit is not None
    assert circuit["track"] == "Las Vegas"
    assert circuit["game_track_length_m"] == 6200.0
    assert len(circuit["lines"]["formula1"]["racing_line"]) == 2
    assert len(circuit["sectors"]) == 2
    assert len(circuit["sections"]) == 1
    assert circuit["sections"][0]["turn"] == "1"


def test_upsert_and_get_benchmark(temp_db):
    # First insert the parent circuit
    temp_db.upsert_circuit(
        track_id=31,
        slug="f1-25_las-vegas",
        name="Las Vegas",
        track_length_m=6200.0,
    )

    temp_db.upsert_benchmark(
        track_id=31,
        track_name="Las Vegas",
        benchmark_lap_time_ms=93500,
        sector_1_time_ms=27000,
        sector_2_time_ms=33000,
        sector_3_time_ms=33500,
        notes="Ghost 110% AI",
        corners=[{
            "turn": "1",
            "name": "Turn 1",
            "sector": 1,
            "start_m": 10.0,
            "apex_m": 40.0,
            "end_m": 80.0,
            "ideal_apex_speed_kph": 105.0,
            "ideal_apex_gear": 3,
            "ideal_brake_point_m": 85.0,
            "ideal_throttle_point_m": 50.0,
            "notes": "Trail brake deep",
        }],
    )

    bm = temp_db.get_benchmark(31)
    assert bm is not None
    assert bm["benchmark_lap_time_ms"] == 93500
    assert len(bm["corners"]) == 1
    assert bm["corners"][0]["ideal_apex_gear"] == 3


def test_duckdb_switch_and_query(temp_db):
    temp_db.upsert_circuit(
        track_id=7,
        slug="f1-25_silverstone",
        name="Silverstone",
        track_length_m=5891.0,
        racing_line=[[10.0, 20.0]],
    )

    # Switch to DuckDB mode (Option 2 attached to SQLite)
    status = temp_db.set_engine_mode("duckdb")
    assert "DuckDB" in status
    assert temp_db.mode == "duckdb"

    # Query through DuckDB
    res = temp_db.get_circuit(7)
    assert res is not None
    assert res["track"] == "Silverstone"
    assert res["game_track_length_m"] == 5891.0

    # Switch back to SQLite
    status_back = temp_db.set_engine_mode("sqlite")
    assert "SQLite" in status_back
    assert temp_db.mode == "sqlite"
