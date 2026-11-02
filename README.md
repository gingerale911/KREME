# KREM — F1 25 Telemetry Dashboard

KREM is a standalone telemetry dashboard for **F1 25**. It listens for the
game's format-2025 UDP telemetry, validates and decodes packets, records raw
captures, and serves a local status dashboard and live JSON API.

## Requirements

- Python 3.9 or newer
- Node.js 18 or newer and npm (to build the dashboard)
- F1 25 configured to send UDP telemetry using **2025** format to port `20777`

## Install

From this directory, create and activate a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Build the React dashboard once so KREM can serve it:

```sh
cd frontend
npm ci
npm run build
cd ..
```

For the planned Gemini coaching integration, install the optional AI Studio
client as well:

```sh
python -m pip install -e ".[coach]"
```

LLM requests will use the Gemini API from Google AI Studio. The coach is not
implemented yet; its API key will remain server-side.

## Run

```sh
python -m krem
```

Open [http://localhost:8765](http://localhost:8765). By default KREM listens
on `0.0.0.0:20777` and records captures in `captures/`. If the frontend has
not been built, the server shows a diagnostic status page instead.

Useful options:

```sh
python -m krem --port 20778 --web-port 8766
python -m krem --no-record
python -m krem --replay captures/example.f1udp --replay-speed 2
```

The dashboard and `/api/status`, `/api/snapshot`, `/api/session`, `/api/player`,
`/api/events`, and `/ws` endpoints are available from the local web server.

## Verification

Run the backend tests inside the virtual environment:

```sh
python -m pytest
```

The in-game capture checks V0–V15 in the
[dashboard plan](F1_25_Telemetry_Dashboard_Plan.md) remain pending until
verified against live F1 25 telemetry. KREM currently provides the ingest,
capture/replay, and live status foundation; the planned map, lap analysis,
graphs, and coaching panels are not yet implemented.

## Attribution

Track map data, when included, must credit **Shfonic Dash Track Maps**
(https://github.com/shfonic/ShfonicDashTracks), © Richard Hawes and contributors,
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

F1® 25 is an official product of the FIA Formula One World Championship™.
KREM is an independent project and is not affiliated with or endorsed by EA.
