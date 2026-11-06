# KREM — F1 25 Telemetry Dashboard

> **AGENTS.md** — Living document. Updated after every code change.

## Project Identity
- **Name:** KREM
- **Purpose:** Standalone real-time telemetry dashboard focused on F1 25
- **Current stack:** Python asyncio/FastAPI backend · NumPy decoder · React + TypeScript + Vite frontend · WebSocket
- **AI provider:** Gemini API via Google AI Studio; coaching runs server-side and keeps the key out of the browser
- **UDP Format:** 2025 only (`m_packetFormat == 2025 && m_gameYear == 25`)
- **Source Plan:** [`F1_25_Telemetry_Dashboard_Plan.md`](file:///Users/dp/Desktop/F1/KREM/F1_25_Telemetry_Dashboard_Plan.md)
- **Protocol reference:** EA SPORTS F1 25 UDP Specification (see source note in the plan). The local third-party struct transcription is intentionally not tracked.

---

## Current Architecture

```
F1 25 ──UDP :20777──▶ ingest (asyncio DatagramProtocol)
                        ├─ guard (format 2025, size per id) → NumPy decoder
                        ├─ raw recorder → captures/*.f1udp; replay reader
                        ├─ live state → compact JSON snapshots
                        └─ FastAPI/uvicorn: WebSocket (30 Hz) · REST
Browser (React+TS/Vite): [1 Track position] [2 Lap analysis] [3 Live graphs] [4 Player values]
```

Lap persistence, reference traces, calibrated track maps, and AI coaching remain roadmap work. The coach must use Gemini through Google AI Studio; its key stays server-side.

---

## Milestones & Progress

| M | Deliverable | Status |
|---|---|---|
| **M0** | Capture tool + verification tests V0–V15 | 🔨 In Progress — requires live game captures |
| **M1** | Ingest, guard, decode, recorder, replay | 🔨 Core implemented; capture-based exit check pending |
| M2 | Panel 1 map + calibration + learned-line fallback | 🔨 Live world-position view; calibration/map overlays pending |
| M3 | Lap segmenter, resampler, DuckDB, reference store | ✅ Implemented; live-game validation pending |
| M4 | Panel 2 sectors/colours | 🔨 Live lap/sector display; reference-based colours pending |
| M5 | Panel 3 graphs, Panel 4 values/classifier | 🔨 Live rolling charts and values; reference/classifier work pending |
| M6 | AI coach + eval harness (Gemini / Google AI Studio) | ✅ Coach and benchmark APIs implemented; live-game validation pending |
| M7 | Packaging, settings, attribution screen | 🔨 Python package and frontend build work; installer/settings pending |
| M8 | Track-edge estimation (stretch) | ⬜ Not Started |

---

## Directory Structure

```
KREM/
├── .gitignore
├── AGENTS.md                              ← this living status file
├── README.md
├── F1_25_Telemetry_Dashboard_Plan.md      ← master plan
├── pyproject.toml
├── krem/
│   ├── __main__.py                        ← live listener and replay CLI
│   ├── core/                              ← packet constants and enums
│   ├── ingest/                            ← guard, decoder, protocol, recorder
│   ├── pipeline/live_state.py             ← live telemetry snapshot
│   └── server/                            ← REST, WebSocket, static frontend
├── frontend/                              ← React + TypeScript + Vite dashboard
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   └── src/                               ← four live dashboard panels
└── tests/
    ├── test_decoder.py
    ├── test_guard.py
    ├── test_recorder.py
    └── test_struct_sizes.py
```

---

## Current Build State

### Last Updated: 2026-11-03T03:45:00+05:30

**Implemented this turn:**
- Live FastAPI snapshot/REST/WebSocket integration and static frontend serving
- Four-panel React dashboard with a live map, sector/timing panel, rolling charts, and player values
- Frontend wired to backend world-position, sector-split, event, and UDP-feed status fields
- Recorder/replay format correction, malformed-capture validation, and session decoder field-count correction
- Install/build/run instructions; optional `google-genai` coach dependency
- This status file updated after implementation
- Ignored the local EA-copyrighted telemetry-structure transcription so it is not redistributed with the repository

**Key Decisions Made:**
- Python + asyncio for backend (plan §4); run Python commands from `.venv`
- DuckDB for storage — no big-data engine needed (plan §4.2: 0.38 MB/s)
- numpy packed dtypes for zero-copy decoding
- 16/16 packet sizes verified (Appendix A)
- Guard on `m_packetFormat == 2025 && m_gameYear == 25`
- Wheel order: RL=0, RR=1, FL=2, FR=3
- Little-endian, packed, no padding
- Gemini API through Google AI Studio for future coaching; model/pricing selection deferred to M6

**Verification Matrix (from Plan §12):**

| ID | Check | Status |
|---|---|---|
| D1 | 16/16 packet sizes match | ✅ Verified |
| D2 | Sizes match Rust crate | ✅ Verified |
| D3 | 2025 vs 2026 differences | ✅ Documented |
| D4 | LLM provider decision | ✅ Google AI Studio Gemini API; model/pricing deferred to M6 |
| V0–V15 | Capture-based tests | ⬜ Awaiting M0 |

**Checks this turn:** Python test suite **79 passed** in `.venv`; `pip check` clean; CLI help works; final `npm run build` succeeds; browser smoke test verified the dashboard, active synthetic UDP values, map marker, and correct waiting-for-UDP state when the feed goes stale.

---

## Packet Reference (Quick Lookup)

| ID | Packet | Size (B) | Rate |
|---|---|---|---|
| 0 | Motion | 1349 | menu rate |
| 1 | Session | 753 | 2/s |
| 2 | LapData | 1285 | menu rate |
| 3 | Event | 45 | on event |
| 4 | Participants | 1284 | 5s |
| 5 | CarSetups | 1133 | 2/s |
| 6 | CarTelemetry | 1352 | menu rate |
| 7 | CarStatus | 1239 | menu rate |
| 8 | FinalClassification | 1042 | — |
| 9 | LobbyInfo | 954 | — |
| 10 | CarDamage | 1041 | 10/s |
| 11 | SessionHistory | 1460 | 20/s cycling |
| 12 | TyreSets | 231 | 20/s cycling |
| 13 | MotionEx | 273 | menu rate |
| 14 | TimeTrial | 101 | 1/s TT only |
| 15 | LapPositions | 1131 | — |

---

## Change Log

| Timestamp | Files Changed | Description |
|---|---|---|
| 2026-11-03 03:00 | `AGENTS.md` | Initial creation |
| 2026-11-03 03:45 | Backend, `frontend/`, `tests/`, `README.md`, `pyproject.toml`, plan, `.gitignore`, `AGENTS.md` | Built and integrated the first live dashboard path; documented Gemini / Google AI Studio; fixed and verified recorder replay/session decoding; aligned the UI with the API's actual field names and feed status |

## Step 1 update — 2026-11-04

- Fixed historical pedal chart scaling and summary percentage formatting.
- Added monotonic per-packet freshness and null masking in live snapshots.
- Reset cached player/session data on UID or player-index changes; fixed the
  telemetry handler's invalid-player-index path.
- Replaced healthy-looking missing values, exposed telemetry/damage freshness,
  separated tyre surface/inner/brake temperature averages, and masked live
  values after WebSocket loss. Car silhouette is temporarily neutral.
- Made development fallback pedal formatting accept missing values.
- Added `tests/test_live_freshness.py` (6 synthetic tests).
- Validation: 87 backend tests passed on Python 3.12; TypeScript/Vite production
  build passed. Windows replacement build and live F1 25 validation pending.
- Top-down SVG/modes and reliable lap recorder/persistence/comparison remain
  the next steps; this update does not implement them.

## Step 2 update — 2026-11-04

- Extracted the car panel into `frontend/src/components/CarStatusPanel.tsx`
  and scoped CSS. The main dashboard retains the existing telemetry stream.
- Added top-down SVG, correct wheel mapping, Wear/Temperature/Pressure/Damage
  buttons, per-wheel surface/inner/brake temperatures and pressure.
- Added independent wing/floor/diffuser/sidepod damage colours, explicit
  percentage legend, grey unavailable parts, and six damage detail rows.
- The single sidepod packet reading colours both sidepods; this is labelled.
- No new runtime dependencies, polling endpoints or backend changes.
- Step 1 Windows validation: user confirmed 87 tests and production build pass.
- Live F1 25 validation remains pending.
- Step 2 validation: TypeScript/Vite build passed. Server-rendered component
  checks passed for wheel mapping, independent damage colours, four controls,
  and missing/stale/offline masking. Browser interaction/layout tests were
  blocked by a failed Chromium download; user visual checks remain pending.

## Step 3 update — 2026-11-04

- Added bounded exact-frame `LapRecorder`; removed latest-value lap sampling
  from LiveState. Ingest and snapshot draining run under LiveState's lock.
- Stored elapsed time, distance, normalized inputs, speed, frame/session IDs,
  explicit missing samples and gap markers. Session UIDs in records are strings.
- Preserved previous-lap sectors at transitions; incorporated player history
  timings/validity. Added invalid/partial flags and quality reasons.
- Added conservative full-timeline invalidation for flashbacks/rewinds, and
  resets for session/player changes. No guessed time for skipped boundaries.
- Removed stale browser lap-cache merging; existing UI labels record quality
  and uses SVG path breaks for missing samples. Car panel remains unchanged.
- Updated the legacy lap test with real advancing frame IDs and zeroed new-lap
  splits; it now also checks that previous sector times survive the boundary.
- Added 19 recorder tests: exact pairing, reordering/duplicates, mismatches,
  missing/invalid samples, partial/pit laps, gaps, sectors/history, flashbacks,
  resets, bounds, age flush and LiveState integration.
- Validation: 106 backend tests passed (Python 3.12); TypeScript/Vite build
  passed. Windows and live-game checks for this step remain pending.
- Remaining: DuckDB persistence and trace APIs, distance comparison API,
  synchronized four-chart comparison UI, end-to-end capture/replay validation.

## PR feedback update — 2026-11-05: retain paused live telemetry

- Based on the uploaded KREME (5) snapshot, including persistence, comparison
  APIs, comparison UI and the all-metrics car panel. Those features preserved.
- Exposed explicit Session gamePaused flag. Freeze driving updates and recorder
  input while paused; keep receiving Session updates to detect resume.
- Added separate retainedLive values without weakening fresh-only API fields
  or inventing values for never-received data. Added per-stream/sample identity.
- Frontend retains readings/plots on pause or disconnection with accurate state
  labels. Only new advancing telemetry samples extend plots; resume starts a
  new path segment. Session/player/timeline changes reset cached live traces.
- Added six backend regression tests in tests/test_pause_retention.py.
- Validation: 156 tests passed, TypeScript/Vite build passed, simulated DOM and
  WebSocket checks passed for freeze/resume/disconnect/reset. No game installed
  here; live-game check remains with the repository owner.

## PR #1 merge integration — 2026-11-05

- Integrated persistent lap comparison and retained-live telemetry with the
  Gemini coach, benchmark APIs, and additional track outlines.
- Kept both live telemetry freshness handling and the existing coaching/lap
  comparison UI; consolidated overlapping sector-analysis styles.
- Validation: 156 backend tests passed and the frontend production build passed.
- Live-game validation remains pending.

## Live race responsiveness update — 2026-11-06

- Live WebSocket and player/session reads now omit lap sample conversion at the source; completed history stays available through history APIs. Previously every 30 Hz update walked all stored samples before removing them.
- Moved blocking storage, comparison and coach routes into FastAPI workers. Serialized optional circuit-engine access and singleton initialization for concurrent requests. Saved laps remain intact; no database migration or deletion.
- Live map now loads only the current circuit from static JSON, independently updates from motion packets, retains circuit identity across delayed session packets, and adds colored cars, YOU marker, recent trail and start/finish label.
- Fixed chart sampling at fixed game time on the starting grid and after flashbacks. Repeated samples and explicit paused/stale feeds do not extend traces.
- Audited every Player values source with changing synthetic packets and the recorded race. Corrected joules-to-MJ display, compound names and unavailable suggested gear. Retained readings have per-source LIVE/LAST RECEIVED/UNAVAILABLE labels.
- Validation: 163 backend tests; 3 frontend sampling tests; TypeScript/Vite build; browser replay verified map, values and rendered traces. Recorded-capture snapshot average improved from about 24 ms to 0.43 ms (snapshot computation only, not end-to-end game latency).
- Restart the existing backend and refresh the dashboard to load these changes. No fresh live-game latency measurement was performed.

## Restored dashboard edits — 2026-11-06
- Recovered the compact race layout, larger map, right-side car health, lap comparison layout, glowing AI button and dismissible analysis overlay from saved edit records.
- Restored turn cards and stacking fixes, independent damage ranges, and tyre health (100 minus wear).
- Restored sector clocks, previous-lap/upcoming-sector selection, deterministic pace grades, repeated-timestamp handling and constant-input observations. Missing recordings remain explicit; Gemini cannot replace missing evidence with generic driving instructions.
- Verification: 176 backend tests, 4 frontend tests and the production build passed. Runtime restart remains necessary to load backend code.
