
"""DuckDB connection and schema management for KREM."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

import duckdb


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR PRIMARY KEY,
    session_uid VARCHAR NOT NULL,
    player_car_index INTEGER NOT NULL,
    epoch INTEGER NOT NULL,
    track_id INTEGER,
    track_length DOUBLE,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS laps (
    lap_id VARCHAR PRIMARY KEY,
    session_id VARCHAR NOT NULL,
    lap_number INTEGER NOT NULL,
    track_id INTEGER,
    track_length DOUBLE,
    lap_time_ms BIGINT,
    sector1_time_ms BIGINT,
    sector2_time_ms BIGINT,
    sector3_time_ms BIGINT,
    invalid BOOLEAN NOT NULL DEFAULT FALSE,
    partial BOOLEAN NOT NULL DEFAULT FALSE,
    quality_reasons VARCHAR,
    sample_count INTEGER NOT NULL DEFAULT 0,
    avg_speed_kph DOUBLE,
    max_speed_kph DOUBLE,
    avg_throttle DOUBLE,
    avg_brake DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lap_samples (
    lap_id VARCHAR NOT NULL,
    sample_index INTEGER NOT NULL,
    elapsed_time_ms BIGINT,
    distance DOUBLE,
    speed DOUBLE,
    throttle DOUBLE,
    brake DOUBLE,
    steering DOUBLE,
    frame_id BIGINT,
    overall_frame_id BIGINT,
    session_time DOUBLE,
    gap_before BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (lap_id, sample_index)
);

CREATE INDEX IF NOT EXISTS idx_laps_session
    ON laps(session_id);

CREATE INDEX IF NOT EXISTS idx_samples_lap
    ON lap_samples(lap_id);
"""


class LapDatabase:
    """Owns one DuckDB connection and serializes its access.

    Use one instance for the application lifetime. Do not create a new
    connection for every UDP packet or API request.
    """

    def __init__(self, database_path: str = "data/krem.duckdb") -> None:
        self.database_path = database_path
        self._lock = threading.RLock()
        self._closed = False

        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)

        self.connection = duckdb.connect(database_path)
        self.initialize()

    def initialize(self) -> None:
        """Create the database schema if it does not already exist."""
        with self._lock:
            self._ensure_open()
            self.connection.execute(SCHEMA)

    def execute(self, query: str, parameters=None):
        """Execute a query while holding the connection lock."""
        with self._lock:
            self._ensure_open()
            if parameters is None:
                return self.connection.execute(query)
            return self.connection.execute(query, parameters)

    def fetchone(self, query: str, parameters=None):
        with self._lock:
            self._ensure_open()
            if parameters is None:
                return self.connection.execute(query).fetchone()
            return self.connection.execute(query, parameters).fetchone()

    def fetchall(self, query: str, parameters=None):
        with self._lock:
            self._ensure_open()
            if parameters is None:
                return self.connection.execute(query).fetchall()
            return self.connection.execute(query, parameters).fetchall()

    def transaction(self):
        """Return the lock used to protect multi-statement transactions."""
        self._ensure_open()
        return self._lock

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("LapDatabase is already closed")

    def close(self) -> None:
        """Close the connection safely."""
        with self._lock:
            if not self._closed:
                self.connection.close()
                self._closed = True

    def __enter__(self) -> "LapDatabase":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
