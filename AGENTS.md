# KREM — F1 25 Telemetry Dashboard

> **AGENTS.md** — Living document. Updated after every code change.

## Project Identity
- **Name:** KREM
- **Purpose:** Standalone real-time telemetry dashboard focused on F1 25
- **Current stack:** Python asyncio/FastAPI backend · NumPy decoder · React + TypeScript + Vite frontend · WebSocket
- **Planned AI provider:** Gemini API via Google AI Studio; coaching is not implemented yet
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
| M3 | Lap segmenter, resampler, DuckDB, reference store | ⬜ Not Started |
| M4 | Panel 2 sectors/colours | 🔨 Live lap/sector display; reference-based colours pending |
| M5 | Panel 3 graphs, Panel 4 values/classifier | 🔨 Live rolling charts and values; reference/classifier work pending |
| M6 | AI coach + eval harness (Gemini / Google AI Studio) | ⬜ Not Started |
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
