
"""Distance-aligned comparison calculations for two recorded laps."""

from __future__ import annotations

import math
from typing import Any


DEFAULT_GRID_POINTS = 201
COMPARISON_SIGNALS = ("speed", "throttle", "brake")


def _number(value: Any) -> float | None:
    """Return a finite float, or None for missing/invalid values."""
    if value is None:
        return None

    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return result if math.isfinite(result) else None


def _build_segments(
    trace: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Split a trace at gaps, invalid coordinates and reverse distance."""

    segments: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for sample in trace:
        distance = _number(sample.get("distance"))
        elapsed = _number(sample.get("elapsedTimeMs"))

        if distance is None or elapsed is None:
            if current:
                segments.append(current)
                current = []
            continue

        point = dict(sample)
        point["distance"] = distance
        point["elapsedTimeMs"] = elapsed

        gap_before = bool(sample.get("gapBefore", False))

        if gap_before and current:
            segments.append(current)
            current = []

        if current and distance <= current[-1]["distance"]:
            segments.append(current)
            current = []

        current.append(point)

    if current:
        segments.append(current)

    return segments


def _interpolate(
    segments: list[list[dict[str, Any]]],
    distance: float,
    field: str,
) -> float | None:
    """Interpolate a signal without crossing a recorded telemetry gap."""

    for segment in segments:
        if not segment:
            continue

        first_distance = segment[0]["distance"]
        last_distance = segment[-1]["distance"]

        if distance < first_distance or distance > last_distance:
            continue

        for point in segment:
            if math.isclose(
                point["distance"],
                distance,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                return _number(point.get(field))

        for left, right in zip(segment, segment[1:]):
            x0 = left["distance"]
            x1 = right["distance"]

            if x0 < distance < x1:
                y0 = _number(left.get(field))
                y1 = _number(right.get(field))

                if y0 is None or y1 is None:
                    return None

                ratio = (distance - x0) / (x1 - x0)

                return y0 + ratio * (y1 - y0)

    return None


def compare_laps(
    reference_lap: dict[str, Any],
    comparison_lap: dict[str, Any],
    reference_trace: list[dict[str, Any]],
    comparison_trace: list[dict[str, Any]],
    grid_points: int = DEFAULT_GRID_POINTS,
) -> dict[str, Any]:
    """Compare two laps on a shared distance grid.

    Positive deltaMs means the comparison lap is behind the reference lap.
    Negative deltaMs means the comparison lap is ahead.

    Missing samples and recorded gaps remain None. No extrapolation is used.
    """

    if grid_points < 2:
        raise ValueError("grid_points must be at least 2")

    if not reference_trace or not comparison_trace:
        raise ValueError("Both laps must contain telemetry samples")

    reference_track = reference_lap.get("trackId")
    comparison_track = comparison_lap.get("trackId")

    if (
        reference_track is not None
        and comparison_track is not None
        and reference_track != comparison_track
    ):
        raise ValueError("Cannot compare laps from different tracks")

    reference_length = _number(reference_lap.get("trackLength"))
    comparison_length = _number(comparison_lap.get("trackLength"))

    if reference_length is None or comparison_length is None:
        raise ValueError("Both laps must have a known track length")

    if reference_length <= 0 or comparison_length <= 0:
        raise ValueError("Track lengths must be positive")

    if abs(reference_length - comparison_length) > 1.0:
        raise ValueError("Lap track lengths do not match")

    reference_time = _number(reference_lap.get("lapTimeMs"))
    comparison_time = _number(comparison_lap.get("lapTimeMs"))

    if reference_time is None or comparison_time is None:
        raise ValueError("Both laps must have valid lap times")

    if reference_time <= 0 or comparison_time <= 0:
        raise ValueError("Lap times must be positive")

    reference_segments = _build_segments(reference_trace)
    comparison_segments = _build_segments(comparison_trace)

    if not reference_segments or not comparison_segments:
        raise ValueError("No usable telemetry segments found")

    # Use the shorter common track length. Never extrapolate beyond it.
    common_length = min(reference_length, comparison_length)

    reference_total_delta = comparison_time - reference_time

    rows = []

    for index in range(grid_points):
        distance = common_length * index / (grid_points - 1)

        reference_elapsed = _interpolate(
            reference_segments,
            distance,
            "elapsedTimeMs",
        )

        comparison_elapsed = _interpolate(
            comparison_segments,
            distance,
            "elapsedTimeMs",
        )

        delta = None

        if reference_elapsed is not None and comparison_elapsed is not None:
            delta = comparison_elapsed - reference_elapsed

        row = {
            "distance": round(distance, 3),
            "referenceElapsedTimeMs": (
                round(reference_elapsed, 3)
                if reference_elapsed is not None else None
            ),
            "comparisonElapsedTimeMs": (
                round(comparison_elapsed, 3)
                if comparison_elapsed is not None else None
            ),
            "deltaMs": round(delta, 3) if delta is not None else None,
        }

        for signal in COMPARISON_SIGNALS:
            reference_value = _interpolate(
                reference_segments,
                distance,
                signal,
            )

            comparison_value = _interpolate(
                comparison_segments,
                distance,
                signal,
            )

            signal_delta = None

            if reference_value is not None and comparison_value is not None:
                signal_delta = comparison_value - reference_value

            row[f"reference{signal.title()}"] = reference_value
            row[f"comparison{signal.title()}"] = comparison_value
            row[f"{signal}Delta"] = (
                round(signal_delta, 6)
                if signal_delta is not None else None
            )

        rows.append(row)

    valid_deltas = [
        row["deltaMs"]
        for row in rows
        if row["deltaMs"] is not None
    ]

    return {
        "referenceLapId": reference_lap.get(
            "lapId", reference_lap.get("id")
        ),
        "comparisonLapId": comparison_lap.get(
            "lapId", comparison_lap.get("id")
        ),
        "referenceLapTimeMs": reference_time,
        "comparisonLapTimeMs": comparison_time,
        "totalTimeDeltaMs": reference_total_delta,
        "commonTrackLength": common_length,
        "gridPoints": grid_points,
        "validDeltaPoints": len(valid_deltas),
        "data": rows,
    }

