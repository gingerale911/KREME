
import pytest

from krem.storage import LapDatabase, LapRepository


@pytest.fixture
def sample_lap():
    return {
        "id": "12345:0:1:3",
        "sessionUid": "12345",
        "playerCarIndex": 0,
        "epoch": 1,
        "lap": 3,
        "trackId": 0,
        "trackLength": 5000.0,
        "lapTimeMs": 90000,
        "sector1TimeMs": 30000,
        "sector2TimeMs": 30000,
        "sector3TimeMs": 30000,
        "invalid": False,
        "partial": False,
        "qualityReasons": [],
        "avgSpeedKph": 200.0,
        "maxSpeedKph": 250.0,
        "avgThrottle": 0.8,
        "avgBrake": 0.2,
        "samples": [
            {
                "elapsedTimeMs": 0,
                "distance": 0.0,
                "speed": 180.0,
                "throttle": 1.0,
                "brake": 0.0,
            },
            {
                "elapsedTimeMs": 1000,
                "distance": 100.0,
                "speed": 200.0,
                "throttle": 0.8,
                "brake": 0.0,
            },
            {
                "elapsedTimeMs": 2000,
                "distance": 200.0,
                "speed": 220.0,
                "throttle": 0.0,
                "brake": 0.7,
            },
        ],
    }


def test_database_tables_created():
    with LapDatabase(":memory:") as db:
        tables = {row[0] for row in db.fetchall("SHOW TABLES")}
        assert tables == {"sessions", "laps", "lap_samples"}


def test_save_and_retrieve_lap(tmp_path, sample_lap):
    with LapDatabase(str(tmp_path / "krem.duckdb")) as db:
        repo = LapRepository(db)
        lap_id = repo.save_lap(sample_lap)

        lap = repo.get_lap(lap_id)

        assert lap is not None
        assert lap["lapNumber"] == 3
        assert lap["lapTimeMs"] == 90000
        assert lap["sampleCount"] == 3


def test_retrieve_lap_samples(sample_lap):
    with LapDatabase(":memory:") as db:
        repo = LapRepository(db)
        lap_id = repo.save_lap(sample_lap)

        trace = repo.get_lap_trace(lap_id)

        assert len(trace) == 3
        assert trace[0]["speed"] == 180.0
        assert trace[1]["throttle"] == 0.8
        assert trace[2]["brake"] == 0.7


def test_missing_values_remain_null(sample_lap):
    sample_lap["samples"][1]["speed"] = None

    with LapDatabase(":memory:") as db:
        repo = LapRepository(db)
        lap_id = repo.save_lap(sample_lap)

        trace = repo.get_lap_trace(lap_id)

        assert trace[1]["speed"] is None


def test_lap_metadata_update_does_not_duplicate_samples(sample_lap):
    with LapDatabase(":memory:") as db:
        repo = LapRepository(db)
        lap_id = repo.save_lap(sample_lap)

        repaired = dict(sample_lap)
        repaired["lapTimeMs"] = 90100
        repaired["sector3TimeMs"] = 30100
        repaired["qualityReasons"] = ["history_repaired"]

        repo.save_lap(repaired)

        lap = repo.get_lap(lap_id)
        trace = repo.get_lap_trace(lap_id)

        assert lap["lapTimeMs"] == 90100
        assert lap["sector3TimeMs"] == 30100
        assert lap["qualityReasons"] == ["history_repaired"]
        assert len(trace) == 3


def test_session_and_lap_listing(sample_lap):
    with LapDatabase(":memory:") as db:
        repo = LapRepository(db)
        repo.save_lap(sample_lap)

        sessions = repo.get_sessions()

        assert len(sessions) == 1
        assert sessions[0]["lapCount"] == 1

        laps = repo.get_laps(sessions[0]["sessionId"])

        assert len(laps) == 1
        assert laps[0]["lapNumber"] == 3


def test_database_persistence_after_reopening(tmp_path, sample_lap):
    path = str(tmp_path / "persistent.duckdb")

    db = LapDatabase(path)
    repo = LapRepository(db)
    lap_id = repo.save_lap(sample_lap)
    db.close()

    db = LapDatabase(path)
    repo = LapRepository(db)

    assert repo.get_lap(lap_id)["lapTimeMs"] == 90000
    assert len(repo.get_lap_trace(lap_id)) == 3

    db.close()


def test_unknown_lap_returns_none():
    with LapDatabase(":memory:") as db:
        repo = LapRepository(db)

        assert repo.get_lap("unknown") is None
        assert repo.get_lap_trace("unknown") is None
