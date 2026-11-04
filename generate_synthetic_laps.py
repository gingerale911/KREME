"""Insert two deterministic synthetic laps into KREM's DuckDB database.

Place this file in the KREME project root and run after stopping the backend:
    python generate_synthetic_laps.py

The script uses the same LapDatabase and LapRepository classes as the app.
It is safe to run more than once: the same demo lap IDs are upserted.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from krem.storage import LapDatabase, LapRepository  # noqa: E402


DATABASE_PATH = ROOT / "data" / "krem-live.duckdb"
SESSION_UID = "KREM-SYNTHETIC-DEMO"
PLAYER_INDEX = 0
EPOCH = 0
TRACK_ID = 0
TRACK_LENGTH = 5300.0
SAMPLE_COUNT = 201


def make_lap(lap_number: int, lap_time_ms: int, pace_offset: float) -> dict:
    samples = []

    for index in range(SAMPLE_COUNT):
        fraction = index / (SAMPLE_COUNT - 1)
        distance = TRACK_LENGTH * fraction

        # Smooth, plausible speed variation around a full lap.
        speed = (
            235.0
            + 48.0 * math.sin(2.0 * math.pi * fraction - 0.7)
            - 28.0 * math.sin(6.0 * math.pi * fraction)
            + pace_offset
        )
        speed = max(75.0, min(335.0, speed))

        # Throttle/brake zones vary around the lap and between the two laps.
        throttle = max(
            0.0,
            min(1.0, 0.72 + 0.27 * math.sin(4.0 * math.pi * fraction + 0.25)),
        )
        brake_zone = max(0.0, math.sin(6.0 * math.pi * fraction + 0.6))
        brake = min(1.0, brake_zone ** 3 * (0.78 if lap_number == 1 else 0.72))
        if brake > 0.08:
            throttle = 0.0

        samples.append(
            {
                "elapsedTimeMs": round(lap_time_ms * fraction),
                "distance": round(distance, 3),
                "speed": round(speed, 2),
                "throttle": round(throttle, 3),
                "brake": round(brake, 3),
                "steering": round(0.25 * math.sin(8.0 * math.pi * fraction), 4),
                "frameId": index,
                "overallFrameId": index,
                "sessionTime": index / 60.0,
                "gapBefore": False,
            }
        )

    # Keep sector times internally consistent with the lap time.
    sector1 = round(lap_time_ms * 0.29)
    sector2 = round(lap_time_ms * 0.34)
    sector3 = lap_time_ms - sector1 - sector2

    speeds = [sample["speed"] for sample in samples]
    throttles = [sample["throttle"] for sample in samples]
    brakes = [sample["brake"] for sample in samples]

    return {
        "id": f"{SESSION_UID}:{PLAYER_INDEX}:{EPOCH}:{lap_number}",
        "sessionUid": SESSION_UID,
        "playerCarIndex": PLAYER_INDEX,
        "epoch": EPOCH,
        "lap": lap_number,
        "trackId": TRACK_ID,
        "trackLength": TRACK_LENGTH,
        "lapTimeMs": lap_time_ms,
        "sector1TimeMs": sector1,
        "sector2TimeMs": sector2,
        "sector3TimeMs": sector3,
        "invalid": False,
        "partial": False,
        "qualityReasons": [],
        "sampleCount": len(samples),
        "avgSpeedKph": round(sum(speeds) / len(speeds), 2),
        "maxSpeedKph": round(max(speeds), 2),
        "avgThrottle": round(sum(throttles) / len(throttles), 3),
        "avgBrake": round(sum(brakes) / len(brakes), 3),
        "samples": samples,
    }


def main() -> None:
    if not DATABASE_PATH.parent.exists():
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Database: {DATABASE_PATH}")
    print("Writing two synthetic demo laps using KREM's LapRepository...")

    with LapDatabase(str(DATABASE_PATH)) as database:
        repository = LapRepository(database)

        lap_one = make_lap(lap_number=1, lap_time_ms=91_200, pace_offset=0.0)
        lap_two = make_lap(lap_number=2, lap_time_ms=90_700, pace_offset=2.5)

        id_one = repository.save_lap(lap_one)
        id_two = repository.save_lap(lap_two)

        sessions = repository.get_sessions()
        session_id = repository.session_id_for(lap_one)
        stored_laps = repository.get_laps(session_id)

        print("\nSynthetic data saved successfully.")
        print(f"Session ID: {session_id}")
        print(f"Lap 1 ID: {id_one}")
        print(f"Lap 2 ID: {id_two}")
        print(f"Stored laps in session: {len(stored_laps)}")
        print(f"Samples per lap: {SAMPLE_COUNT}")
        print(f"Sessions in database: {len(sessions)}")
        print("\nLap Compare API can now load these two laps.")


if __name__ == "__main__":
    main()
