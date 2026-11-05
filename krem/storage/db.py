"""KREM Database Engine & Storage Layer.

Supports:
- SQLite (default embedded storage): zero-dependency, ultra-lightweight, Git-portable via seed script.
- DuckDB Mode (analytical fallback / query accelerator): attaches directly to the SQLite database
  via DuckDB's sqlite extension, querying identical tables in columnar mode without duplicating data.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("krem.storage")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "krem.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS circuits (
    track_id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    track_length_m REAL NOT NULL,
    orientation REAL DEFAULT 0.0,
    sf_line_pos_x REAL,
    sf_line_pos_z REAL,
    sf_line_heading REAL,
    racing_line_json TEXT,
    left_edge_json TEXT,
    right_edge_json TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS circuit_sectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    sector_number INTEGER NOT NULL,
    lap_dist_m REAL NOT NULL,
    FOREIGN KEY (track_id) REFERENCES circuits (track_id) ON DELETE CASCADE,
    UNIQUE (track_id, sector_number)
);

CREATE TABLE IF NOT EXISTS circuit_corners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    turn_number TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'corner',
    start_m REAL NOT NULL,
    apex_m REAL NOT NULL,
    end_m REAL NOT NULL,
    FOREIGN KEY (track_id) REFERENCES circuits (track_id) ON DELETE CASCADE,
    UNIQUE (track_id, turn_number)
);

CREATE TABLE IF NOT EXISTS track_benchmarks (
    track_id INTEGER PRIMARY KEY,
    track_name TEXT NOT NULL,
    benchmark_lap_time_ms INTEGER NOT NULL,
    sector_1_time_ms INTEGER NOT NULL,
    sector_2_time_ms INTEGER NOT NULL,
    sector_3_time_ms INTEGER NOT NULL,
    notes TEXT,
    source TEXT DEFAULT 'ideal_ghost_110',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (track_id) REFERENCES circuits (track_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS benchmark_corners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    turn_number TEXT NOT NULL,
    name TEXT NOT NULL,
    sector INTEGER NOT NULL,
    start_m REAL NOT NULL,
    apex_m REAL NOT NULL,
    end_m REAL NOT NULL,
    ideal_apex_speed_kph REAL NOT NULL,
    ideal_apex_gear INTEGER NOT NULL,
    ideal_brake_point_m REAL,
    ideal_throttle_point_m REAL,
    notes TEXT,
    FOREIGN KEY (track_id) REFERENCES track_benchmarks (track_id) ON DELETE CASCADE,
    UNIQUE (track_id, turn_number)
);

CREATE INDEX IF NOT EXISTS idx_circuit_corners_track ON circuit_corners(track_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_corners_track ON benchmark_corners(track_id);
"""


class DatabaseManager:
    """Manages SQLite storage and optional DuckDB query acceleration."""

    def __init__(self, db_path: Path | str | None = None, mode: Literal["sqlite", "duckdb"] = "sqlite"):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self._duck_con = None
        self._init_sqlite()

        if self.mode == "duckdb":
            self._init_duckdb()

    def _get_sqlite_connection(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=30.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON;")
        return con

    def _init_sqlite(self) -> None:
        """Create tables if they do not exist."""
        with self._get_sqlite_connection() as con:
            con.executescript(SCHEMA_SQL)

    def _init_duckdb(self) -> None:
        """Initialize DuckDB and attach to the SQLite database."""
        try:
            import duckdb
            self._duck_con = duckdb.connect()
            self._duck_con.execute("INSTALL sqlite;")
            self._duck_con.execute("LOAD sqlite;")
            self._duck_con.execute(f"ATTACH '{self.db_path}' AS krem (TYPE SQLITE);")
            logger.info("DuckDB engine attached to SQLite db at %s", self.db_path)
        except Exception as e:
            logger.warning("Failed to initialize DuckDB mode, falling back to SQLite: %s", e)
            self.mode = "sqlite"
            self._duck_con = None

    def set_engine_mode(self, mode: Literal["sqlite", "duckdb"]) -> str:
        """Switch query engine mode at runtime."""
        if mode == "duckdb":
            self._init_duckdb()
            if self._duck_con is not None:
                self.mode = "duckdb"
                return "Switched to DuckDB engine attached to SQLite storage"
            return "DuckDB initialization failed; staying on SQLite engine"
        else:
            self.mode = "sqlite"
            if self._duck_con:
                try:
                    self._duck_con.close()
                except Exception:
                    pass
                self._duck_con = None
            return "Switched to standard SQLite engine"

    # --- Query API ---

    def get_circuit(self, track_id: int) -> dict[str, Any] | None:
        """Retrieve full circuit geometry and sections."""
        if self.mode == "duckdb" and self._duck_con:
            try:
                row = self._duck_con.execute(
                    "SELECT * FROM krem.circuits WHERE track_id = ?", [track_id]
                ).fetchone()
                if not row:
                    return None
                cols = [desc[0] for desc in self._duck_con.description]
                c = dict(zip(cols, row))
            except Exception as e:
                logger.warning("DuckDB query failed, fallback to SQLite: %s", e)
                return self._get_circuit_sqlite(track_id)
        else:
            c = self._get_circuit_sqlite(track_id)

        if not c:
            return None

        sectors = self.get_circuit_sectors(track_id)
        corners = self.get_circuit_corners(track_id)

        racing_line = json.loads(c["racing_line_json"]) if c.get("racing_line_json") else []
        left_edge = json.loads(c["left_edge_json"]) if c.get("left_edge_json") else []
        right_edge = json.loads(c["right_edge_json"]) if c.get("right_edge_json") else []

        return {
            "track_id": c["track_id"],
            "slug": c["slug"],
            "track": c["name"],
            "game_track_length_m": c["track_length_m"],
            "orientation": c["orientation"],
            "sf_line": {
                "pos": [c["sf_line_pos_x"], c["sf_line_pos_z"]],
                "heading": c["sf_line_heading"],
            },
            "lines": {
                "formula1": {
                    "racing_line": racing_line
                }
            },
            "left_edge": left_edge,
            "right_edge": right_edge,
            "sectors": sectors,
            "sections": corners,
        }

    def _get_circuit_sqlite(self, track_id: int) -> dict[str, Any] | None:
        with self._get_sqlite_connection() as con:
            cur = con.execute("SELECT * FROM circuits WHERE track_id = ?", (track_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_circuit_sectors(self, track_id: int) -> list[dict[str, Any]]:
        with self._get_sqlite_connection() as con:
            cur = con.execute(
                "SELECT sector_number AS sector, lap_dist_m FROM circuit_sectors WHERE track_id = ? ORDER BY sector_number",
                (track_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    def get_circuit_corners(self, track_id: int) -> list[dict[str, Any]]:
        with self._get_sqlite_connection() as con:
            cur = con.execute(
                "SELECT turn_number AS turn, name, type, start_m, apex_m, end_m FROM circuit_corners WHERE track_id = ? ORDER BY start_m",
                (track_id,)
            )
            return [dict(r) for r in cur.fetchall()]

    def list_circuits(self) -> list[dict[str, Any]]:
        with self._get_sqlite_connection() as con:
            cur = con.execute("SELECT track_id, slug, name, track_length_m, orientation FROM circuits ORDER BY track_id")
            return [dict(r) for r in cur.fetchall()]

    def get_benchmark(self, track_id: int) -> dict[str, Any] | None:
        """Fetch benchmark metadata and corner targets."""
        with self._get_sqlite_connection() as con:
            cur = con.execute("SELECT * FROM track_benchmarks WHERE track_id = ?", (track_id,))
            bm = cur.fetchone()
            if not bm:
                return None
            bm_dict = dict(bm)

            c_cur = con.execute(
                "SELECT turn_number AS turn, name, sector, start_m, apex_m, end_m, "
                "ideal_apex_speed_kph, ideal_apex_gear, ideal_brake_point_m, ideal_throttle_point_m, notes "
                "FROM benchmark_corners WHERE track_id = ? ORDER BY start_m",
                (track_id,)
            )
            bm_dict["corners"] = [dict(r) for r in c_cur.fetchall()]
            return bm_dict

    # --- Write / Seed API ---

    def upsert_circuit(
        self,
        track_id: int,
        slug: str,
        name: str,
        track_length_m: float,
        orientation: float = 0.0,
        sf_line: dict[str, Any] | None = None,
        racing_line: list[list[float]] | None = None,
        left_edge: list[list[float]] | None = None,
        right_edge: list[list[float]] | None = None,
        sectors: list[dict[str, Any]] | None = None,
        sections: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert a circuit and its related sectors and corners."""
        sf_pos = (sf_line or {}).get("pos", [0.0, 0.0])
        sf_heading = (sf_line or {}).get("heading", 0.0)

        with self._get_sqlite_connection() as con:
            con.execute(
                """
                INSERT INTO circuits (
                    track_id, slug, name, track_length_m, orientation,
                    sf_line_pos_x, sf_line_pos_z, sf_line_heading,
                    racing_line_json, left_edge_json, right_edge_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    slug=excluded.slug,
                    name=excluded.name,
                    track_length_m=excluded.track_length_m,
                    orientation=excluded.orientation,
                    sf_line_pos_x=excluded.sf_line_pos_x,
                    sf_line_pos_z=excluded.sf_line_pos_z,
                    sf_line_heading=excluded.sf_line_heading,
                    racing_line_json=excluded.racing_line_json,
                    left_edge_json=excluded.left_edge_json,
                    right_edge_json=excluded.right_edge_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    track_id,
                    slug,
                    name,
                    track_length_m,
                    orientation,
                    sf_pos[0] if len(sf_pos) > 0 else 0.0,
                    sf_pos[1] if len(sf_pos) > 1 else 0.0,
                    sf_heading,
                    json.dumps(racing_line or []),
                    json.dumps(left_edge or []),
                    json.dumps(right_edge or []),
                )
            )

            # Refresh sectors (normalize index or sector)
            if sectors:
                con.execute("DELETE FROM circuit_sectors WHERE track_id = ?", (track_id,))
                seen_sectors = set()
                for idx, s in enumerate(sectors, start=1):
                    sec_num = int(s.get("sector", s.get("index", idx)))
                    if sec_num in seen_sectors:
                        sec_num = max(seen_sectors) + 1
                    seen_sectors.add(sec_num)
                    con.execute(
                        """
                        INSERT INTO circuit_sectors (track_id, sector_number, lap_dist_m)
                        VALUES (?, ?, ?)
                        ON CONFLICT(track_id, sector_number) DO UPDATE SET lap_dist_m=excluded.lap_dist_m
                        """,
                        (track_id, sec_num, float(s.get("lap_dist_m", 0.0)))
                    )

            # Refresh corners
            if sections:
                con.execute("DELETE FROM circuit_corners WHERE track_id = ?", (track_id,))
                seen_turns = set()
                for sec in sections:
                    t_num = str(sec.get("turn", ""))
                    if not t_num or t_num in seen_turns:
                        continue
                    seen_turns.add(t_num)
                    con.execute(
                        """
                        INSERT INTO circuit_corners (track_id, turn_number, name, type, start_m, apex_m, end_m)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            track_id,
                            t_num,
                            sec.get("name", f"Turn {t_num}"),
                            sec.get("type", "corner"),
                            float(sec.get("start_m", 0.0)),
                            float(sec.get("apex_m", 0.0)),
                            float(sec.get("end_m", 0.0)),
                        )
                    )

    def upsert_benchmark(
        self,
        track_id: int,
        track_name: str,
        benchmark_lap_time_ms: int,
        sector_1_time_ms: int,
        sector_2_time_ms: int,
        sector_3_time_ms: int,
        notes: str = "",
        corners: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert benchmark lap targets and corner parameters."""
        with self._get_sqlite_connection() as con:
            con.execute(
                """
                INSERT INTO track_benchmarks (
                    track_id, track_name, benchmark_lap_time_ms,
                    sector_1_time_ms, sector_2_time_ms, sector_3_time_ms, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    track_name=excluded.track_name,
                    benchmark_lap_time_ms=excluded.benchmark_lap_time_ms,
                    sector_1_time_ms=excluded.sector_1_time_ms,
                    sector_2_time_ms=excluded.sector_2_time_ms,
                    sector_3_time_ms=excluded.sector_3_time_ms,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    track_id,
                    track_name,
                    benchmark_lap_time_ms,
                    sector_1_time_ms,
                    sector_2_time_ms,
                    sector_3_time_ms,
                    notes,
                )
            )

            if corners:
                con.execute("DELETE FROM benchmark_corners WHERE track_id = ?", (track_id,))
                seen_turns = set()
                for c in corners:
                    t_num = str(c.get("turn", ""))
                    if not t_num or t_num in seen_turns:
                        continue
                    seen_turns.add(t_num)
                    con.execute(
                        """
                        INSERT INTO benchmark_corners (
                            track_id, turn_number, name, sector, start_m, apex_m, end_m,
                            ideal_apex_speed_kph, ideal_apex_gear, ideal_brake_point_m,
                            ideal_throttle_point_m, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            track_id,
                            t_num,
                            c.get("name", f"Turn {t_num}"),
                            int(c.get("sector", 1)),
                            float(c.get("start_m", 0.0)),
                            float(c.get("apex_m", 0.0)),
                            float(c.get("end_m", 0.0)),
                            float(c.get("ideal_apex_speed_kph", 0.0)),
                            int(c.get("ideal_apex_gear", 1)),
                            float(c["ideal_brake_point_m"]) if c.get("ideal_brake_point_m") is not None else None,
                            float(c["ideal_throttle_point_m"]) if c.get("ideal_throttle_point_m") is not None else None,
                            c.get("notes", ""),
                        )
                    )


# Global singleton instance
_db_instance: DatabaseManager | None = None


def get_db(mode: Literal["sqlite", "duckdb"] = "sqlite") -> DatabaseManager:
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager(mode=mode)
    return _db_instance
