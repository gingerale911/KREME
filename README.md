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

## Live reading availability

Live snapshots include a `freshness` map for telemetry, damage, status, lap,
motion, session and participants. Each entry has `state` (`missing`, `fresh`,
or `stale`) and `ageSeconds`, measured from monotonic packet receipt time.
Frequently sent packets expire after 2 seconds; participants expire after
12 seconds to accommodate their lower rate. These are UI availability
thresholds, not changes to the game's packet rate.

Unavailable readings are JSON `null` and display as an em dash. Actual zero
readings remain zero. New session UIDs or player indices clear the previous
car's cached state. A disconnected browser masks retained live values.
The car panel labels telemetry and damage availability separately.
The top-down car offers Wear, Temperature, Pressure and Damage modes.
Wheel labels map RL/RR/FL/FR packet indices to the correct physical corners.
Temperature shows surface, inner and brake readings for each wheel; pressure
is in psi. Wear displays percent worn (0% new), not remaining tyre life.
Body colours always represent independent component damage; tyre colours
represent wear in Wear mode and damage otherwise. Grey indicates unavailable
data. Both sidepods share the single sidepod damage reading provided by the
packet. Colour is a linear percentage scale, not a calibrated temperature or
pressure safety recommendation. Pedals remain normalized to 0–1 in the API and are
converted to percentages for display.

Run `python -m pytest tests/test_live_freshness.py` for synthetic availability,
recovery, session/player reset and temperature-channel checks. Live game
validation remains pending.

## Lap recording (Step 3)

`krem/pipeline/lap_recorder.py` owns the in-memory lap recorder. It joins
LapData and CarTelemetry on the same overall frame identifier, verifies the
regular frame identifier and session time (within 20 ms), and processes frames
in order. It waits up to 8 advancing frames or 250 ms for packet reordering;
snapshot/API reads drain aged entries. This wait applies to recording only,
not to the live car panel. Packets arriving after the window are ignored by
the recorder. Exact matching intentionally favours gaps over guessed inputs.

Samples include elapsed milliseconds, distance in metres, speed in km/h,
normalized throttle/brake, both frame identifiers, session time, lap number,
player index and the full session UID as a string. Missing/invalid inputs are
null. Gaps over 250 ms are flagged; the existing trace breaks at gaps.

A sequential lap-number transition finalizes the previous lap using the new
packet's last-lap time, while retaining the previous lap's sector splits.
Player SessionHistory packets can supply official sector times and validity.
Invalid flags are sticky. A skipped lap number never supplies a guessed time.

Records expose `invalid`, `partial`, `qualityReasons`, and `sampleCount`.
Near-start coverage requires distance 0–25 m and elapsed time <=250 ms;
near-end coverage requires the last sample within 50 m of the known finish
and within 250 ms of the reported lap time. Mid-lap joins, missing inputs,
large gaps, pit/out laps, reverse distance and missing boundaries are labelled
partial. These conservative capture-quality checks are separate from game
lap validity. Missing trace data cannot be repaired by SessionHistory.

A session UID or player change clears the recorder. A flashback event,
backwards session time or backwards lap progress invalidates the entire
old timeline, increments the recorder epoch and starts a new capture.
This deliberately discards earlier completed laps too. Late packets outside
the reorder window do not cause rewinds. Raw UDP capture files are unchanged.

Retention is capped at 16 completed records and 30,000 samples per lap.
Unfinished laps remain in progress; the API does not claim they are completed.
Samples are still in the existing snapshot payload until Step 4 moves traces
into on-demand APIs and adds DuckDB persistence. Restarting the backend loses
these in-memory laps. The UI no longer merges old browser-cached lap records.

Verification: `python -m pytest tests/test_lap_recorder.py tests/test_recorder.py`.
The tests use synthetic packets; real F1 25 capture/replay validation, including
actual packet alignment and flashbacks, is still required.

## Paused live telemetry

The dashboard uses the Session packet's explicit `gamePaused` flag. While
paused it retains the last driving readings, car status, track position and
rolling telemetry traces. Paused packet repeats do not update the driving
state or lap recorder. Resuming waits for a new driving sample; no artificial
flat line is appended during the pause. The first resumed point starts a new
trace segment. No completed lap is needed to inspect this live window.

Live trace sampling uses the telemetry packet identity and advancing game time,
not the WebSocket refresh count. Repeated snapshots and unrelated packets
cannot append duplicate speed/throttle/brake samples.

Silence is not treated as proof of a game pause. PAUSED requires a recent
Session packet with the flag set; otherwise the UI shows STALE or DISCONNECTED
and clearly identifies retained readings. Individual packet freshness remains
unchanged. Fields never received still show an em dash.

The API keeps its existing fresh-only `player`, `session` and `cars` fields.
`retainedLive` contains the last received values for frozen display; consumers
must respect `freshness`. `gamePaused`, `telemetrySample` and `liveStreamId`
provide pause, sample identity and reset metadata. New sessions/player changes
and recorder timeline resets clear the browser traces. A new backend process
also gets a new stream identity.

Storage is bounded: one latest snapshot plus the existing 360-point browser
trace window. This is not a new historical database. Refreshing the browser
clears the rolling traces; restarting the server clears retained live values.
Persisted lap comparison continues to use the existing DuckDB storage.

Validation: 156 backend tests passed; production frontend build passed. A
simulated DOM/WebSocket check covered pause retention, frozen plots, duplicate
suppression, resume gaps, disconnect retention and session clearing. Actual
F1 25 pause/resume behaviour still needs checking on the game owner's PC.
