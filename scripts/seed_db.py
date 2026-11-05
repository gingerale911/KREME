"""Seed the SQLite database from existing JSON track maps and Python benchmark registries.

This script ensures that whenever the project is cloned or pulled from Git,
the SQLite database (`data/krem.db`) can be populated or synchronized in seconds.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from krem.storage import get_db
from krem.coach.benchmarks import BenchmarkRegistry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_db")

TRACK_ID_MAP: dict[str, int] = {
    "f1-25_melbourne.json": 0,
    "f1-25_shanghai.json": 2,
    "f1-25_sakhir.json": 3,
    "f1-25_catalunya.json": 4,
    "f1-25_monaco.json": 5,
    "f1-25_montreal.json": 6,
    "f1-25_silverstone.json": 7,
    "f1-25_hungaroring.json": 9,
    "f1-25_spa.json": 10,
    "f1-25_monza.json": 11,
    "f1-25_singapore.json": 12,
    "f1-25_suzuka.json": 13,
    "f1-25_abu-dhabi.json": 14,
    "f1-25_texas.json": 15,
    "f1-25_brazil.json": 16,
    "f1-25_red-bull-ring.json": 17,
    "f1-25_mexico.json": 19,
    "f1-25_baku.json": 20,
    "f1-25_zandvoort.json": 26,
    "f1-25_imola.json": 27,
    "f1-25_jeddah.json": 29,
    "f1-25_miami.json": 30,
    "f1-25_las-vegas.json": 31,
    "f1-25_losail.json": 32,
    "f1-25_madrid.json": 42,
}


def seed_circuits(db) -> int:
    track_dir = Path(__file__).resolve().parent.parent / "frontend" / "public" / "track_data"
    if not track_dir.is_dir():
        logger.warning("Track data directory not found: %s", track_dir)
        return 0

    count = 0
    for filename, track_id in TRACK_ID_MAP.items():
        file_path = track_dir / filename
        if not file_path.is_file():
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            slug = filename.replace(".json", "")
            name = data.get("track", slug.replace("f1-25_", "").title())
            length_m = float(data.get("game_track_length_m", 5000.0))
            orientation = float(data.get("orientation", 0.0))
            sf_line = data.get("sf_line", {})
            lines = data.get("lines", {}).get("formula1", {})
            racing_line = lines.get("racing_line", [])
            left_edge = data.get("left_edge", [])
            right_edge = data.get("right_edge", [])
            sectors = data.get("sectors", [])
            sections = data.get("sections", [])

            db.upsert_circuit(
                track_id=track_id,
                slug=slug,
                name=name,
                track_length_m=length_m,
                orientation=orientation,
                sf_line=sf_line,
                racing_line=racing_line,
                left_edge=left_edge,
                right_edge=right_edge,
                sectors=sectors,
                sections=sections,
            )
            count += 1
            logger.info("Seeded circuit ID %2d: %s (%d points)", track_id, name, len(racing_line))
        except Exception as e:
            logger.error("Failed to seed %s: %s", filename, e)

    return count


def seed_benchmarks(db) -> int:
    registry = BenchmarkRegistry()
    count = 0
    for track_id in TRACK_ID_MAP.values():
        bm = registry.get_benchmark(track_id)
        if not bm:
            continue
        try:
            corners = [
                {
                    "turn": c.turn,
                    "name": c.name,
                    "sector": c.sector,
                    "start_m": c.start_m,
                    "apex_m": c.apex_m,
                    "end_m": c.end_m,
                    "ideal_apex_speed_kph": c.ideal_apex_speed_kph,
                    "ideal_apex_gear": c.ideal_apex_gear,
                    "ideal_brake_point_m": c.ideal_brake_m,
                    "ideal_throttle_point_m": c.ideal_throttle_m,
                    "notes": c.notes,
                }
                for c in bm.corners
            ]

            lap_time_ms = getattr(bm, "ideal_lap_time_ms", 90000)
            db.upsert_benchmark(
                track_id=track_id,
                track_name=bm.track_name,
                benchmark_lap_time_ms=lap_time_ms,
                sector_1_time_ms=int(lap_time_ms * 0.3),
                sector_2_time_ms=int(lap_time_ms * 0.35),
                sector_3_time_ms=int(lap_time_ms * 0.35),
                notes=f"Track length {bm.track_length_m:.0f}m",
                corners=corners,
            )
            count += 1
            logger.info("Seeded benchmark ID %2d: %s (%d corners)", track_id, bm.track_name, len(corners))
        except Exception as e:
            logger.error("Failed to seed benchmark %d: %s", track_id, e)

    return count


def main() -> None:
    db = get_db()
    logger.info("Initializing database at: %s", db.db_path)
    circuits_count = seed_circuits(db)
    benchmarks_count = seed_benchmarks(db)
    logger.info("Seed complete! %d circuits and %d benchmarks populated into SQLite.", circuits_count, benchmarks_count)


if __name__ == "__main__":
    main()
