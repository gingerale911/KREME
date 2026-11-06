
"""Tests for KREM's persistent lap-history REST API."""

import pytest
from fastapi.testclient import TestClient

from krem.pipeline import LiveState
from krem.server import create_app


# ---------------------------------------------------------------------
# Fake repository — avoids needing a real DuckDB database for API tests
# ---------------------------------------------------------------------

class FakeLapRepository:
    def __init__(self):
        self.sessions = [
            {
                "sessionId": "session-123",
                "trackName": "Australia",
                "lapCount": 2,
            }
        ]

        self.laps = [
            {
                "id": "lap-001",
                "sessionId": "session-123",
                "lapNumber": 1,
                "lapTimeMs": 90000,
                "sampleCount": 3,
            },
            {
                "id": "lap-002",
                "sessionId": "session-123",
                "lapNumber": 2,
                "lapTimeMs": 91000,
                "sampleCount": 3,
            },
        ]

        self.traces = {
            "lap-001": [
                {
                    "sampleIndex": 0,
                    "elapsedTimeMs": 0,
                    "distance": 0.0,
                    "speed": 180.0,
                    "throttle": 1.0,
                    "brake": 0.0,
                },
                {
                    "sampleIndex": 1,
                    "elapsedTimeMs": 1000,
                    "distance": 50.0,
                    "speed": 220.0,
                    "throttle": 0.8,
                    "brake": 0.0,
                },
                {
                    "sampleIndex": 2,
                    "elapsedTimeMs": 2000,
                    "distance": 100.0,
                    "speed": 150.0,
                    "throttle": 0.0,
                    "brake": 0.7,
                },
            ]
        }

    def get_sessions(self):
        return self.sessions

    def get_laps(self, session_id):
        return [
            lap for lap in self.laps
            if lap["sessionId"] == session_id
        ]

    def get_lap(self, lap_id):
        return next(
            (lap for lap in self.laps if lap["id"] == lap_id),
            None,
        )

    def get_lap_trace(self, lap_id):
        if self.get_lap(lap_id) is None:
            return None

        return self.traces.get(lap_id, [])


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def repository():
    return FakeLapRepository()


@pytest.fixture
def client(repository):
    app = create_app(
        LiveState(),
        lap_repository=repository,
    )

    return TestClient(app)


@pytest.fixture
def client_without_storage():
    app = create_app(LiveState())
    return TestClient(app)


# ---------------------------------------------------------------------
# Successful API responses
# ---------------------------------------------------------------------

def test_sessions_endpoint(client):
    response = client.get("/api/sessions")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["sessionId"] == "session-123"
    assert data[0]["lapCount"] == 2


def test_session_laps_endpoint(client):
    response = client.get("/api/sessions/session-123/laps")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2
    assert data[0]["id"] == "lap-001"
    assert data[1]["id"] == "lap-002"


def test_individual_lap_endpoint(client):
    response = client.get("/api/laps/lap-001")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == "lap-001"
    assert data["lapNumber"] == 1
    assert data["lapTimeMs"] == 90000


def test_lap_trace_endpoint(client):
    response = client.get("/api/laps/lap-001/trace")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 3
    assert data[0]["speed"] == 180.0
    assert data[1]["distance"] == 50.0
    assert data[2]["brake"] == 0.7


def test_lap_trace_preserves_sample_order(client):
    response = client.get("/api/laps/lap-001/trace")

    data = response.json()

    elapsed_times = [
        sample["elapsedTimeMs"]
        for sample in data
    ]

    assert elapsed_times == [0, 1000, 2000]


# ---------------------------------------------------------------------
# Missing resources
# ---------------------------------------------------------------------

def test_unknown_session_returns_404(client):
    response = client.get("/api/sessions/unknown-session/laps")

    assert response.status_code == 404


def test_unknown_lap_returns_404(client):
    response = client.get("/api/laps/unknown-lap")

    assert response.status_code == 404


def test_unknown_lap_trace_returns_404(client):
    response = client.get("/api/laps/unknown-lap/trace")

    assert response.status_code == 404


# ---------------------------------------------------------------------
# Storage not configured
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/sessions",
        "/api/sessions/session-123/laps",
        "/api/laps/lap-001",
        "/api/laps/lap-001/trace",
    ],
)
def test_persistent_endpoints_return_503_without_storage(
    client_without_storage,
    endpoint,
):
    response = client_without_storage.get(endpoint)

    assert response.status_code == 503
    assert response.json()["detail"] == "Lap storage is not configured"


# ---------------------------------------------------------------------
# WebSocket payload
# ---------------------------------------------------------------------

def test_websocket_does_not_send_historical_laps(client):
    with client.websocket_connect("/ws") as websocket:
        snapshot = websocket.receive_json()

    assert "laps" not in snapshot
    assert "session" in snapshot
    assert "player" in snapshot
    assert "stats" in snapshot


# ---------------------------------------------------------------------
# Existing snapshot compatibility
# ---------------------------------------------------------------------

def test_snapshot_endpoint_remains_available(client):
    response = client.get("/api/snapshot")

    assert response.status_code == 200

    data = response.json()

    assert "session" in data
    assert "player" in data
    assert "stats" in data
    assert "laps" in data


# ---------------------------------------------------------------------
# Current in-progress lap replay API
# ---------------------------------------------------------------------

def test_current_lap_returns_404_when_no_active_lap(client):
    response = client.get("/api/laps/current")
    assert response.status_code == 404
    assert response.json()["detail"] == "No active lap in progress"


def test_current_lap_returns_samples_when_active(repository):
    from tests.test_lap_recorder import make, pair
    from krem.core import PacketId

    live_state = LiveState()
    session = make(PacketId.SESSION, 0)
    session.data["trackId"] = 10
    session.data["trackLength"] = 7000
    live_state.update(session)

    p, t = pair(1, lap=1, elapsed=500, distance=30)
    live_state.update(p)
    live_state.update(t)

    app = create_app(live_state, lap_repository=repository)
    client = TestClient(app)

    response = client.get("/api/laps/current")
    assert response.status_code == 200
    data = response.json()
    assert data["lap"] == 1
    assert data["inProgress"] is True
    assert len(data["samples"]) > 0
    assert "speed" in data["samples"][0]
    assert "throttle" in data["samples"][0]
