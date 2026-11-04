
"""Tests for the persisted lap comparison API."""

import pytest
from fastapi.testclient import TestClient

from krem.pipeline import LiveState
from krem.server import create_app


class FakeLapRepository:
    def __init__(self):
        self.laps = {
            "lap-1": {
                "lapId": "lap-1",
                "lapTimeMs": 10000,
                "trackId": 1,
                "trackLength": 1000,
            },
            "lap-2": {
                "lapId": "lap-2",
                "lapTimeMs": 11000,
                "trackId": 1,
                "trackLength": 1000,
            },
        }

        self.traces = {
            "lap-1": [
                {
                    "distance": 0,
                    "elapsedTimeMs": 0,
                    "speed": 100,
                    "throttle": 1.0,
                    "brake": 0.0,
                    "gapBefore": False,
                },
                {
                    "distance": 500,
                    "elapsedTimeMs": 5000,
                    "speed": 150,
                    "throttle": 0.7,
                    "brake": 0.0,
                    "gapBefore": False,
                },
                {
                    "distance": 1000,
                    "elapsedTimeMs": 10000,
                    "speed": 200,
                    "throttle": 1.0,
                    "brake": 0.0,
                    "gapBefore": False,
                },
            ],
            "lap-2": [
                {
                    "distance": 0,
                    "elapsedTimeMs": 0,
                    "speed": 90,
                    "throttle": 0.9,
                    "brake": 0.1,
                    "gapBefore": False,
                },
                {
                    "distance": 500,
                    "elapsedTimeMs": 5500,
                    "speed": 140,
                    "throttle": 0.6,
                    "brake": 0.1,
                    "gapBefore": False,
                },
                {
                    "distance": 1000,
                    "elapsedTimeMs": 11000,
                    "speed": 190,
                    "throttle": 0.9,
                    "brake": 0.0,
                    "gapBefore": False,
                },
            ],
        }

    def get_lap(self, lap_id):
        return self.laps.get(lap_id)

    def get_lap_trace(self, lap_id):
        if lap_id not in self.laps:
            return None
        return self.traces[lap_id]


@pytest.fixture
def client():
    app = create_app(
        LiveState(),
        lap_repository=FakeLapRepository(),
    )
    return TestClient(app)


@pytest.fixture
def client_without_storage():
    return TestClient(create_app(LiveState()))


def test_compare_two_stored_laps(client):
    response = client.get(
        "/api/laps/compare",
        params={
            "reference_id": "lap-1",
            "comparison_id": "lap-2",
            "grid_points": 3,
        },
    )

    assert response.status_code == 200

    result = response.json()

    assert result["referenceLapId"] == "lap-1"
    assert result["comparisonLapId"] == "lap-2"
    assert result["totalTimeDeltaMs"] == 1000
    assert len(result["data"]) == 3


def test_comparison_contains_signal_differences(client):
    response = client.get(
        "/api/laps/compare",
        params={
            "reference_id": "lap-1",
            "comparison_id": "lap-2",
            "grid_points": 3,
        },
    )

    middle = response.json()["data"][1]

    assert middle["speedDelta"] == -10
    assert middle["throttleDelta"] == pytest.approx(-0.1)
    assert middle["brakeDelta"] == pytest.approx(0.1)


def test_unknown_reference_lap_returns_404(client):
    response = client.get(
        "/api/laps/compare",
        params={
            "reference_id": "unknown",
            "comparison_id": "lap-2",
        },
    )

    assert response.status_code == 404


def test_unknown_comparison_lap_returns_404(client):
    response = client.get(
        "/api/laps/compare",
        params={
            "reference_id": "lap-1",
            "comparison_id": "unknown",
        },
    )

    assert response.status_code == 404


def test_same_lap_cannot_be_compared(client):
    response = client.get(
        "/api/laps/compare",
        params={
            "reference_id": "lap-1",
            "comparison_id": "lap-1",
        },
    )

    assert response.status_code == 400


def test_invalid_grid_size_returns_422(client):
    response = client.get(
        "/api/laps/compare",
        params={
            "reference_id": "lap-1",
            "comparison_id": "lap-2",
            "grid_points": 1,
        },
    )

    assert response.status_code == 422


def test_comparison_requires_storage(client_without_storage):
    response = client_without_storage.get(
        "/api/laps/compare",
        params={
            "reference_id": "lap-1",
            "comparison_id": "lap-2",
        },
    )

    assert response.status_code == 503
