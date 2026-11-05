
"""Repository for persistent KREM sessions, laps and telemetry samples."""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from krem.storage.database import LapDatabase


def _finite_number(value: Any) -> Optional[float]:
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return result if math.isfinite(result) else None


def _integer(value: Any) -> Optional[int]:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


class LapRepository:
    """Stores and retrieves completed lap records.

    Expected input is the dictionary produced by KREM's LapRecorder.
    """

    def __init__(self, database: LapDatabase) -> None:
        self.database = database

    @staticmethod
    def session_id_for(record: dict[str, Any]) -> str:
        """Build a session identity scoped to player and timeline epoch."""
        return "{}:{}:{}".format(
            record["sessionUid"],
            int(record["playerCarIndex"]),
            int(record["epoch"]),
        )

    def save_lap(self, record: dict[str, Any]) -> str:
        """Insert or update a lap and replace its sample trace atomically.

        Returns the persistent lap ID.
        """
        lap_id = str(record["id"])
        session_id = self.session_id_for(record)

        session_uid = str(record["sessionUid"])
        player_index = int(record["playerCarIndex"])
        epoch = int(record["epoch"])

        reasons = record.get("qualityReasons") or []
        reasons_json = json.dumps(list(reasons))

        samples = record.get("samples") or []

        with self.database.transaction():
            connection = self.database.connection
            connection.execute("BEGIN TRANSACTION")

            try:
                # Create or update the session metadata.
                existing_session = connection.execute(
                    """
                    SELECT session_id
                    FROM sessions
                    WHERE session_id = ?
                    """,
                    [session_id],
                ).fetchone()

                session_values = [
                    session_uid,
                    player_index,
                    epoch,
                    _integer(record.get("trackId")),
                    _finite_number(record.get("trackLength")),
                    session_id,
                ]

                if existing_session:
                    connection.execute(
                        """
                        UPDATE sessions
                        SET session_uid = ?,
                            player_car_index = ?,
                            epoch = ?,
                            track_id = ?,
                            track_length = ?,
                            updated_at = now()
                        WHERE session_id = ?
                        """,
                        session_values,
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO sessions (
                            session_uid,
                            player_car_index,
                            epoch,
                            track_id,
                            track_length,
                            session_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        session_values,
                    )

                # Insert or update the lap summary.
                lap_values = [
                    lap_id,
                    session_id,
                    int(record["lap"]),
                    _integer(record.get("trackId")),
                    _finite_number(record.get("trackLength")),
                    _integer(record.get("lapTimeMs")),
                    _integer(record.get("sector1TimeMs")),
                    _integer(record.get("sector2TimeMs")),
                    _integer(record.get("sector3TimeMs")),
                    bool(record.get("invalid", False)),
                    bool(record.get("partial", False)),
                    reasons_json,
                    len(samples),
                    _finite_number(record.get("avgSpeedKph")),
                    _finite_number(record.get("maxSpeedKph")),
                    _finite_number(record.get("avgThrottle")),
                    _finite_number(record.get("avgBrake")),
                ]

                connection.execute(
                    """
                    INSERT INTO laps (
                        lap_id,
                        session_id,
                        lap_number,
                        track_id,
                        track_length,
                        lap_time_ms,
                        sector1_time_ms,
                        sector2_time_ms,
                        sector3_time_ms,
                        invalid,
                        partial,
                        quality_reasons,
                        sample_count,
                        avg_speed_kph,
                        max_speed_kph,
                        avg_throttle,
                        avg_brake
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT (lap_id) DO UPDATE SET
                        session_id = excluded.session_id,
                        lap_number = excluded.lap_number,
                        track_id = excluded.track_id,
                        track_length = excluded.track_length,
                        lap_time_ms = excluded.lap_time_ms,
                        sector1_time_ms = excluded.sector1_time_ms,
                        sector2_time_ms = excluded.sector2_time_ms,
                        sector3_time_ms = excluded.sector3_time_ms,
                        invalid = excluded.invalid,
                        partial = excluded.partial,
                        quality_reasons = excluded.quality_reasons,
                        sample_count = excluded.sample_count,
                        avg_speed_kph = excluded.avg_speed_kph,
                        max_speed_kph = excluded.max_speed_kph,
                        avg_throttle = excluded.avg_throttle,
                        avg_brake = excluded.avg_brake,
                        updated_at = now()
                    """,
                    lap_values,
                )

                # Replace samples so metadata repairs do not duplicate traces.
                connection.execute(
                    "DELETE FROM lap_samples WHERE lap_id = ?",
                    [lap_id],
                )

                if samples:
                    sample_rows = []

                    for index, sample in enumerate(samples):
                        sample_rows.append((
                            lap_id,
                            index,
                            _integer(sample.get("elapsedTimeMs")),
                            _finite_number(
                                sample.get("distance", sample.get("lapDistance"))
                            ),
                            _finite_number(sample.get("speed")),
                            _finite_number(sample.get("throttle")),
                            _finite_number(sample.get("brake")),
                            _finite_number(sample.get("steering")),
                            _integer(sample.get("frameId")),
                            _integer(sample.get("overallFrameId")),
                            _finite_number(sample.get("sessionTime")),
                            bool(sample.get("gapBefore", False)),
                        ))

                    connection.executemany(
                        """
                        INSERT INTO lap_samples (
                            lap_id,
                            sample_index,
                            elapsed_time_ms,
                            distance,
                            speed,
                            throttle,
                            brake,
                            steering,
                            frame_id,
                            overall_frame_id,
                            session_time,
                            gap_before
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        sample_rows,
                    )

                connection.execute("COMMIT")

            except Exception:
                connection.execute("ROLLBACK")
                raise

        return lap_id

    def get_sessions(self) -> list[dict[str, Any]]:
        """Return sessions with their completed lap counts."""
        rows = self.database.fetchall(
            """
            SELECT
                s.session_id,
                s.session_uid,
                s.player_car_index,
                s.epoch,
                s.track_id,
                s.track_length,
                s.started_at,
                s.updated_at,
                COUNT(l.lap_id) AS lap_count
            FROM sessions s
            LEFT JOIN laps l ON l.session_id = s.session_id
            GROUP BY
                s.session_id,
                s.session_uid,
                s.player_car_index,
                s.epoch,
                s.track_id,
                s.track_length,
                s.started_at,
                s.updated_at
            ORDER BY s.updated_at DESC
            """
        )

        keys = [
            "sessionId",
            "sessionUid",
            "playerCarIndex",
            "epoch",
            "trackId",
            "trackLength",
            "startedAt",
            "updatedAt",
            "lapCount",
        ]

        return [dict(zip(keys, row)) for row in rows]

    def get_laps(self, session_id: str) -> list[dict[str, Any]]:
        """Return lap summaries for one session, without sample arrays."""
        rows = self.database.fetchall(
            """
            SELECT
                lap_id,
                session_id,
                lap_number,
                track_id,
                track_length,
                lap_time_ms,
                sector1_time_ms,
                sector2_time_ms,
                sector3_time_ms,
                invalid,
                partial,
                quality_reasons,
                sample_count,
                avg_speed_kph,
                max_speed_kph,
                avg_throttle,
                avg_brake
            FROM laps
            WHERE session_id = ?
            ORDER BY lap_number ASC, lap_id ASC
            """,
            [session_id],
        )

        keys = [
            "lapId",
            "sessionId",
            "lapNumber",
            "trackId",
            "trackLength",
            "lapTimeMs",
            "sector1TimeMs",
            "sector2TimeMs",
            "sector3TimeMs",
            "invalid",
            "partial",
            "qualityReasons",
            "sampleCount",
            "avgSpeedKph",
            "maxSpeedKph",
            "avgThrottle",
            "avgBrake",
        ]

        result = []

        for row in rows:
            item = dict(zip(keys, row))

            try:
                item["qualityReasons"] = json.loads(
                    item["qualityReasons"] or "[]"
                )
            except (TypeError, ValueError):
                item["qualityReasons"] = []

            result.append(item)

        return result

    def get_lap(self, lap_id: str) -> Optional[dict[str, Any]]:
        """Return one lap summary, or None if it does not exist."""
        row = self.database.fetchone(
            """
            SELECT
                lap_id,
                session_id,
                lap_number,
                track_id,
                track_length,
                lap_time_ms,
                sector1_time_ms,
                sector2_time_ms,
                sector3_time_ms,
                invalid,
                partial,
                quality_reasons,
                sample_count,
                avg_speed_kph,
                max_speed_kph,
                avg_throttle,
                avg_brake
            FROM laps
            WHERE lap_id = ?
            """,
            [lap_id],
        )

        if row is None:
            return None

        keys = [
            "lapId",
            "sessionId",
            "lapNumber",
            "trackId",
            "trackLength",
            "lapTimeMs",
            "sector1TimeMs",
            "sector2TimeMs",
            "sector3TimeMs",
            "invalid",
            "partial",
            "qualityReasons",
            "sampleCount",
            "avgSpeedKph",
            "maxSpeedKph",
            "avgThrottle",
            "avgBrake",
        ]

        item = dict(zip(keys, row))

        try:
            item["qualityReasons"] = json.loads(
                item["qualityReasons"] or "[]"
            )
        except (TypeError, ValueError):
            item["qualityReasons"] = []

        return item

    def get_lap_trace(self, lap_id: str) -> Optional[list[dict[str, Any]]]:
        """Return ordered telemetry samples, or None for an unknown lap."""
        if self.get_lap(lap_id) is None:
            return None

        rows = self.database.fetchall(
            """
            SELECT
                sample_index,
                elapsed_time_ms,
                distance,
                speed,
                throttle,
                brake,
                steering,
                frame_id,
                overall_frame_id,
                session_time,
                gap_before
            FROM lap_samples
            WHERE lap_id = ?
            ORDER BY sample_index ASC
            """,
            [lap_id],
        )

        keys = [
            "sampleIndex",
            "elapsedTimeMs",
            "distance",
            "speed",
            "throttle",
            "brake",
            "steering",
            "frameId",
            "overallFrameId",
            "sessionTime",
            "gapBefore",
        ]

        return [dict(zip(keys, row)) for row in rows]
