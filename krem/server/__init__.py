"""KREM server — FastAPI application with WebSocket for real-time telemetry.

Serves:
- WebSocket at /ws: 30 Hz UI frames with live state snapshots
- REST endpoints for session info, history, and settings
- Static files for the frontend
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel
from krem.pipeline import LiveState
from krem.coach import BenchmarkRegistry, compare_lap_to_benchmark, generate_coach_advice, get_gemini_api_key, persist_gemini_api_key
from krem.ingest.protocol import F1UDPProtocol, PacketStats

logger = logging.getLogger("krem.server")

# Target 30 Hz WebSocket frame rate (plan §4.3)
WS_FRAME_INTERVAL = 1.0 / 30.0


def create_app(
    live_state: LiveState,
    protocol: F1UDPProtocol | None = None,
) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="KREM — F1 25 Telemetry Dashboard",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Store references
    app.state.live_state = live_state
    app.state.protocol = protocol

    frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="frontend-assets",
        )

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """Serve Vite's production app or the explicit development fallback."""
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        logger.warning(
            "Frontend build not found at %s; serving the development status fallback",
            index_file,
        )
        return _status_page(live_state, protocol)

    @app.get("/track_data/{track_file}")
    async def track_data(track_file: str):
        """Serve prerendered Shfonic track geometry files for the live map."""
        file_path = frontend_dist / "track_data" / track_file
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Track data not found")
        return FileResponse(file_path)

    @app.get("/api/status")
    async def status():
        """Get current server and connection status."""
        return _stats_snapshot(protocol)

    @app.get("/api/snapshot")
    async def live_snapshot():
        """Get the full compact dashboard payload without opening a WebSocket."""
        return _dashboard_snapshot(live_state, protocol)

    @app.get("/api/session")
    async def session_info():
        """Get current session information."""
        return live_state.snapshot()["session"]

    @app.get("/api/player")
    async def player_info():
        """Get current player state."""
        return live_state.snapshot()["player"]

    @app.get("/api/events")
    async def events():
        """Get recent events."""
        return live_state.events_snapshot()

    @app.get("/api/laps")
    async def lap_history():
        """Get the lap-by-lap telemetry summary for the current session."""
        return live_state.lap_history_snapshot()

    benchmark_registry = BenchmarkRegistry()

    class CoachRequest(BaseModel):
        lapNum: int | None = None
        trackId: int | None = None

    class ApiKeyRequest(BaseModel):
        apiKey: str

    @app.get("/api/coach/status")
    async def coach_status():
        """Check if Gemini API key is configured."""
        api_key = get_gemini_api_key()
        return {
            "hasApiKey": bool(api_key),
            "model": "gemini-3.5-flash",
        }

    @app.post("/api/coach/key")
    async def set_coach_api_key(req: ApiKeyRequest):
        """Configure or update Gemini API key dynamically."""
        if not req.apiKey or not req.apiKey.strip():
            raise HTTPException(status_code=400, detail="API key cannot be empty")
        persist_gemini_api_key(req.apiKey.strip())
        return {"status": "ok", "message": "Gemini API key configured successfully"}

    @app.get("/api/coach/benchmark/{track_id}")
    async def get_track_benchmark(track_id: int):
        """Retrieve the ideal benchmark targets for a track."""
        benchmark = benchmark_registry.get_benchmark(track_id)
        if not benchmark:
            raise HTTPException(status_code=404, detail=f"No benchmark available for track {track_id}")
        return benchmark.to_dict()

    @app.post("/api/coach/analyse")
    async def analyse_lap(req: CoachRequest | None = None):
        """Analyze the last completed lap against the track's ideal benchmark for the upcoming sector."""
        session_info = live_state.snapshot()["session"]
        player_info = live_state.snapshot()["player"]
        track_id = (req.trackId if req and req.trackId is not None else session_info.get("trackId", -1))

        # Retrieve benchmark for the EXACT track_id
        benchmark = benchmark_registry.get_benchmark(track_id)

        lap_history = live_state.lap_history_snapshot()
        target_lap_data = None

        if req and req.lapNum is not None:
            for l in lap_history:
                if l.get("lap") == req.lapNum:
                    target_lap_data = l
                    break

        if not target_lap_data and lap_history:
            target_lap_data = lap_history[-1]

        current_sector_idx = int(player_info.get("sector", 0) or 0)
        next_sector = ((current_sector_idx + 1) % 3) + 1

        samples = target_lap_data.get("samples", []) if target_lap_data else []
        lap_time_ms = target_lap_data.get("lapTimeMs", 0) if target_lap_data else 0
        last_lap_num = target_lap_data.get("lap") if target_lap_data else None

        all_deltas = compare_lap_to_benchmark(samples, benchmark)
        sector_deltas = [d for d in all_deltas if d.sector == next_sector]
        if not sector_deltas:
            sector_deltas = all_deltas[:4]

        advice = generate_coach_advice(
            track=benchmark,
            player_lap_time_ms=lap_time_ms,
            corner_deltas=all_deltas,
            focus_sector=next_sector,
            last_lap_num=last_lap_num,
        )

        return {
            "track": benchmark.to_dict(),
            "lapNum": last_lap_num,
            "lapTimeMs": lap_time_ms,
            "nextSector": next_sector,
            "currentSector": current_sector_idx + 1,
            "hasApiKey": bool(get_gemini_api_key()),
            "deltas": [d.to_dict() for d in sector_deltas],
            "advice": advice,
        }


    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time telemetry frames at 30 Hz."""
        await websocket.accept()
        logger.info("WebSocket client connected")
        try:
            while True:
                start = time.monotonic()
                snapshot = _dashboard_snapshot(live_state, protocol)
                try:
                    await websocket.send_json(snapshot)
                except Exception:
                    break
                # Maintain 30 Hz
                elapsed = time.monotonic() - start
                sleep_time = max(0, WS_FRAME_INTERVAL - elapsed)
                await asyncio.sleep(sleep_time)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)

    return app


def _status_page(live_state: LiveState, protocol: F1UDPProtocol | None) -> str:
    """Generate a diagnostic HTML page when frontend is not built."""
    stats = _stats_snapshot(protocol)
    snapshot = live_state.snapshot()
    session = snapshot["session"]
    player = snapshot["player"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KREM — F1 25 Telemetry</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0a0a0f;
            color: #e0e0e8;
            font-family: 'Inter', 'SF Pro', -apple-system, sans-serif;
            padding: 2rem;
        }}
        h1 {{
            font-size: 2rem;
            background: linear-gradient(135deg, #A855F7, #EC4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        .subtitle {{ color: #6B7280; margin-bottom: 2rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
        .card {{
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 1.25rem;
            backdrop-filter: blur(10px);
        }}
        .card h2 {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #A855F7;
            margin-bottom: 0.75rem;
        }}
        .stat {{ display: flex; justify-content: space-between; padding: 0.3rem 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        .stat-label {{ color: #9CA3AF; font-size: 0.85rem; }}
        .stat-value {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
        .connected {{ color: #22C55E; }}
        .disconnected {{ color: #EF4444; }}
        .badge {{
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-ok {{ background: rgba(34,197,94,0.15); color: #22C55E; }}
        .badge-warn {{ background: rgba(239,68,68,0.15); color: #EF4444; }}
        #live-data {{ font-variant-numeric: tabular-nums; }}
        .refresh {{ color: #6B7280; font-size: 0.75rem; margin-top: 1rem; }}
    </style>
</head>
<body>
    <h1>KREM</h1>
    <p class="subtitle">Development fallback · build frontend/dist for the dashboard</p>
    <div class="grid">
        <div class="card">
            <h2>Connection</h2>
            <div class="stat">
                <span class="stat-label">Status</span>
                <span class="stat-value {'connected' if stats['connected'] else 'disconnected'}">
                    {'● Receiving' if stats['connected'] else '○ Waiting for UDP'}
                </span>
            </div>
            <div class="stat">
                <span class="stat-label">Packets/sec</span>
                <span class="stat-value">{stats['packetsPerSecond']:.0f}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Accepted</span>
                <span class="stat-value">{stats['packetsAccepted']:,}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Rejected</span>
                <span class="stat-value">{stats['packetsRejected']:,}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Frame Gaps</span>
                <span class="stat-value">{stats['frameGaps']:,}</span>
            </div>
        </div>
        <div class="card">
            <h2>Session</h2>
            <div class="stat">
                <span class="stat-label">Track</span>
                <span class="stat-value">{session['trackName']}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Track Length</span>
                <span class="stat-value">{session['trackLength']} m</span>
            </div>
            <div class="stat">
                <span class="stat-label">Weather</span>
                <span class="stat-value">{session['weather']}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Track Temp</span>
                <span class="stat-value">{session['trackTemp']}°C</span>
            </div>
            <div class="stat">
                <span class="stat-label">Safety Car</span>
                <span class="stat-value">{session['safetyCar']}</span>
            </div>
        </div>
        <div class="card">
            <h2>Player</h2>
            <div class="stat">
                <span class="stat-label">Speed</span>
                <span class="stat-value">{player['speed']} km/h</span>
            </div>
            <div class="stat">
                <span class="stat-label">Gear</span>
                <span class="stat-value">{player['gear']}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Lap</span>
                <span class="stat-value">{player['lapNum']}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Position</span>
                <span class="stat-value">P{player['position']}</span>
            </div>
            <div class="stat">
                <span class="stat-label">Throttle / Brake</span>
                <span class="stat-value">{player['throttle']:.0%} / {player['brake']:.0%}</span>
            </div>
        </div>
    </div>
    <p class="refresh">Development status only · WebSocket: ws://localhost:8765/ws</p>
    <script>
        // Auto-refresh the status page every 2 seconds
        setTimeout(() => location.reload(), 2000);
    </script>
</body>
</html>"""


def _stats_snapshot(protocol: F1UDPProtocol | None) -> dict:
    """Return a consistent copy of packet statistics for JSON responses."""
    return (protocol.stats if protocol else PacketStats()).snapshot()


def _dashboard_snapshot(
    live_state: LiveState,
    protocol: F1UDPProtocol | None,
) -> dict:
    """Combine the compact live telemetry snapshot with connection statistics."""
    snapshot = live_state.snapshot()
    snapshot["stats"] = _stats_snapshot(protocol)
    return snapshot
