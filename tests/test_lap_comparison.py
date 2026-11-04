
"""Tests for distance-aligned lap comparison."""

import pytest

from krem.pipeline.lap_comparison import compare_laps


def make_lap(lap_id, lap_time=10000, track_id=1, track_length=1000):
    return {
        "lapId": lap_id,
        "lapTimeMs": lap_time,
        "trackId": track_id,
        "trackLength": track_length,
    }


def make_trace(
    distances,
    elapsed,
    speed=None,
    throttle=None,
    brake=None,
    gaps=None,
):
    speed = speed if speed is not None else [100.0] * len(distances)
    throttle = throttle if throttle is not None else [0.5] * len(distances)
    brake = brake if brake is not None else [0.0] * len(distances)
    gaps = gaps if gaps is not None else [False] * len(distances)

    return [
        {
            "distance": distance,
            "elapsedTimeMs": time,
            "speed": speed[index],
            "throttle": throttle[index],
            "brake": brake[index],
            "gapBefore": gaps[index],
        }
        for index, (distance, time) in enumerate(zip(distances, elapsed))
    ]


def test_identical_laps_have_zero_delta():
    lap = make_lap("lap-1")

    trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
    )

    result = compare_laps(lap, lap, trace, trace, grid_points=3)

    assert result["totalTimeDeltaMs"] == 0
    assert result["validDeltaPoints"] == 3
    assert all(row["deltaMs"] == 0 for row in result["data"])


def test_comparison_lap_one_second_slower():
    reference = make_lap("reference", lap_time=10000)
    comparison = make_lap("comparison", lap_time=11000)

    reference_trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
    )

    comparison_trace = make_trace(
        [0, 500, 1000],
        [0, 5500, 11000],
    )

    result = compare_laps(
        reference,
        comparison,
        reference_trace,
        comparison_trace,
        grid_points=3,
    )

    assert result["totalTimeDeltaMs"] == 1000
    assert result["data"][1]["deltaMs"] == 500
    assert result["data"][2]["deltaMs"] == 1000


def test_distance_grid_interpolates_different_sample_positions():
    reference = make_lap("reference")
    comparison = make_lap("comparison")

    reference_trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
    )

    comparison_trace = make_trace(
        [0, 250, 750, 1000],
        [0, 2500, 7500, 10000],
    )

    result = compare_laps(
        reference,
        comparison,
        reference_trace,
        comparison_trace,
        grid_points=5,
    )

    assert len(result["data"]) == 5
    assert result["data"][1]["distance"] == 250
    assert result["data"][1]["deltaMs"] == 0


def test_speed_throttle_and_brake_are_compared():
    lap = make_lap("lap")

    reference_trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
        speed=[100, 150, 200],
        throttle=[0.5, 0.7, 1.0],
        brake=[0.2, 0.1, 0.0],
    )

    comparison_trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
        speed=[110, 140, 210],
        throttle=[0.6, 0.6, 0.9],
        brake=[0.1, 0.2, 0.0],
    )

    result = compare_laps(
        lap,
        lap,
        reference_trace,
        comparison_trace,
        grid_points=3,
    )

    middle = result["data"][1]

    assert middle["speedDelta"] == -10
    assert middle["throttleDelta"] == pytest.approx(-0.1)
    assert middle["brakeDelta"] == pytest.approx(0.1)


def test_gap_is_not_interpolated_across():
    lap = make_lap("lap")

    reference_trace = make_trace(
        [0, 250, 500, 750, 1000],
        [0, 2500, 5000, 7500, 10000],
        gaps=[False, False, True, False, False],
    )

    comparison_trace = make_trace(
        [0, 250, 500, 750, 1000],
        [0, 2500, 5000, 7500, 10000],
    )

    result = compare_laps(
        lap,
        lap,
        reference_trace,
        comparison_trace,
        grid_points=5,
    )

    assert result["data"][1]["deltaMs"] == 0
    assert result["data"][2]["deltaMs"] == 0
    assert result["data"][3]["deltaMs"] == 0

    # No interpolation is allowed between the segments.
    between_segments = compare_laps(
        lap,
        lap,
        reference_trace,
        comparison_trace,
        grid_points=9,
    )

    assert between_segments["data"][3]["referenceElapsedTimeMs"] is None
    assert between_segments["data"][3]["deltaMs"] is None


def test_missing_signal_does_not_invent_values():
    lap = make_lap("lap")

    reference_trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
        speed=[100, None, 200],
    )

    comparison_trace = make_trace(
        [0, 500, 1000],
        [0, 5000, 10000],
    )

    result = compare_laps(
        lap,
        lap,
        reference_trace,
        comparison_trace,
        grid_points=3,
    )

    assert result["data"][1]["referenceSpeed"] is None
    assert result["data"][1]["speedDelta"] is None


def test_different_tracks_are_rejected():
    reference = make_lap("a", track_id=1)
    comparison = make_lap("b", track_id=2)

    trace = make_trace([0, 1000], [0, 10000])

    with pytest.raises(ValueError, match="different tracks"):
        compare_laps(reference, comparison, trace, trace)


def test_invalid_grid_size_is_rejected():
    lap = make_lap("lap")
    trace = make_trace([0, 1000], [0, 10000])

    with pytest.raises(ValueError, match="at least 2"):
        compare_laps(lap, lap, trace, trace, grid_points=1)


def test_empty_trace_is_rejected():
    lap = make_lap("lap")

    with pytest.raises(ValueError, match="telemetry samples"):
        compare_laps(lap, lap, [], [])
