# F1 25 Telemetry Dashboard — Build Plan (UDP format "2025", base game)

**Status:** final plan, ready to build · **Date:** 3 Nov 2026
**Scope:** F1 25 base game, UDP format **2025**. *Not* the "2026 Season Pack" UDP format (details in §2.1).

Legend used throughout:
- ✅ **Verified** — read from a source I opened this session (source IDs in §15), or computed by a script I ran (Appendix A).
- 🔬 **Verify by capture** — cannot be settled from documents; Milestone M0 has a concrete test for each (§12).
- 🛠 **Design choice** — my decision, not a fact about the game. Tunable values are marked as such.

---

## 0. Executive summary

| Question | Answer |
|---|---|
| Can it be built? | Yes, all four panels. Twelve items are limited or impossible — see §11. |
| Stack | Python 3.12 backend (asyncio UDP → numpy decode → DuckDB) · React + TypeScript frontend (Canvas 2D for the map, uPlot for graphs) · WebSocket to the browser. 🛠 |
| Big-data engine needed? | **No.** Worst-case UDP load is **0.38 MB/s (~355 packets/s, 1.37 GB/hour raw)** — computed in §4.2. Kafka/Flink/Spark would add failure modes and no capability. |
| "Expected" values from an API? | **No usable API exists** (§7.1). Expected values are computed from your own recorded laps. |
| Track maps | Shfonic Dash Tracks (CC BY 4.0). ✅ Covers **14 of the 27** track IDs in the 2025 format. 13 need a fallback (§3.3). |
| AI coach | 8 parallel domain agents + 1 synthesizer. All numbers are computed **deterministically**; LLMs only interpret them (§10). |
| Hard prerequisite | In-game UDP Format must be set to the **2025** format. The app detects the wrong format from the header and says so. |

---

## 1. What I could and could not verify (read this first)

1. **I could not open the official EA specification file itself.** The EA forum post (v9.0 for the Season Pack; v6.0 for base F1 25) shows only a summary; the spec is an attachment my tools cannot fetch.
2. **What I used instead:** a public transcription of the F1 25 spec (`MacManley/f1-25-udp`) whose README reproduces every struct, field comment, appendix and FAQ. I then **proved it complete** by rebuilding all 16 packet layouts from it and comparing byte sizes with EA's published sizes — **all 16 match** (Appendix A). Sizes also match an independent Rust crate's constants (`f1-game-library-models-25`).
3. **What the size check does NOT prove:** that fields are in the right *order* inside a struct. One community report says `m_driverStatus` and `m_gridPosition` in LapData are swapped relative to the document. That is test **V2** in §12; the parser must not go live until M0 passes.
4. **Before coding, download the official spec attachment** from the EA post and diff it against §2.3 (30 minutes, listed as M0 task 1).

---

## 2. UDP facts (all ✅ unless marked)

### 2.1 Format selection — the "not the 2026 expansion" requirement
- F1 25 base format: `m_packetFormat = 2025`, `m_gameYear = 25`, **max 22 cars**.
- The 2026 Season Pack format: `m_packetFormat = 2026`, **24 cars**, a new packet id 16 (Car Telemetry 2), DRS/Active-Aero zones inside the Session packet, quantised g-forces, uint16 team/driver ids, Madrid (track id 42), different packet sizes (e.g. LapData 1399 vs 1285).
- EA states a player who never played F1 25 before gets the **Season Pack UDP by default**, and existing players must switch manually. So the app **must** guard on the header.
- **Guard rule (🛠):** accept a datagram only if `m_packetFormat == 2025 && m_gameYear == 25` **and** its length equals the published size for its `m_packetId` (table below). Otherwise drop it and show a banner: *"Game is sending UDP format X. Set UDP Format to 2025 in the game's UDP settings."*
- Default UDP port: **20777** (✅ appears in the spec XML example, KRF1 app, and the Rust crate example). The XML example in the spec also shows `ip="127.0.0.1"`; broadcast mode exists. The in-game menu is authoritative (the XML example in the F1 25 doc contains a stale `format="205"` value).

### 2.2 Wire rules
- **Little-endian, packed, no padding.** Wheel arrays are ordered **0 = RL, 1 = RR, 2 = FL, 3 = FR**.
- Vehicle index is fixed for a whole session. Arrays have 22 slots; a slot has valid data if its `m_resultStatus` in LapData is not `0 = invalid` / `1 = inactive`.
- Packets sent "at rate specified in menus" (Motion, LapData, CarTelemetry, CarStatus, MotionEx) are all sent together on the same frame. Others can arrive on any frame.
- **Restricted data:** in multiplayer, other players' fuel/ERS/damage/tyre-wear fields are zeroed unless they set "Your Telemetry" to Public; other players' car setups are blank. You always see your own.

### 2.3 Header (29 bytes) — `PacketHeader`
`m_packetFormat u16 · m_gameYear u8 · m_gameMajorVersion u8 · m_gameMinorVersion u8 · m_packetVersion u8 · m_packetId u8 · m_sessionUID u64 · m_sessionTime f32 · m_frameIdentifier u32 · m_overallFrameIdentifier u32 · m_playerCarIndex u8 · m_secondaryPlayerCarIndex u8 (255 = none)`

`m_overallFrameIdentifier` does not go backwards after a flashback; `m_frameIdentifier` can.

### 2.4 Packets we consume

| ID | Packet | Size (B) | Rate (spec) | Used for |
|---|---|---|---|---|
| 0 | Motion | 1349 | menu rate | positions, heading, g-force |
| 1 | Session | 753 | 2 / s | track, sector boundaries, units, weather, marshal zones |
| 2 | LapData | 1285 | menu rate | lap/sector time, lap distance, pit status, validity |
| 3 | Event | 45 | on event | session start/end, flashback, SC, penalties |
| 4 | Participants | 1284 | every 5 s | names, numbers, team, livery colours |
| 5 | CarSetups | 1133 | 2 / s | player setup (others blank online) |
| 6 | CarTelemetry | 1352 | menu rate | speed, throttle, brake, gear, rpm, temps, surface |
| 7 | CarStatus | 1239 | menu rate | ERS, fuel, compound, DRS allowed, assists |
| 10 | CarDamage | 1041 | "10 / s" in spec; FAQ example shows 2 / s → 🔬 V3 | tyre wear, damage |
| 11 | SessionHistory | 1460 | 20 / s, cycling cars | authoritative lap + sector times, bests |
| 12 | TyreSets | 231 | 20 / s, cycling cars | tyre set wear / life |
| 13 | MotionEx | 273 | menu rate | **player only**: slip, forces, camber |
| 14 | TimeTrial | 101 | 1 / s (TT only) | PB / rival sector times |
| 8, 9, 15 | FinalClassification / LobbyInfo / LapPositions | 1042 / 954 / 1131 | — | not used in v1 |

### 2.5 Exact field names the app parses

**CarMotionData** (×22): `m_worldPositionX/Y/Z f32` (metres; **Y is up**), `m_worldVelocityX/Y/Z f32`, `m_worldForwardDirX/Y/Z i16` and `m_worldRightDirX/Y/Z i16` (divide by 32767.0), `m_gForceLateral/Longitudinal/Vertical f32`, `m_yaw/m_pitch/m_roll f32`.

**Session:** `m_weather u8 · m_trackTemperature i8 · m_airTemperature i8 · m_totalLaps u8 · m_trackLength u16 · m_sessionType u8 · m_trackId i8 · m_formula u8 · m_sessionTimeLeft u16 · m_isSpectating u8 · m_spectatorCarIndex u8 · m_numMarshalZones u8 · m_marshalZones[21]{m_zoneStart f32, m_zoneFlag i8} · m_safetyCarStatus u8 · m_networkGame u8 · m_numWeatherForecastSamples u8 · m_weatherForecastSamples[64] · m_gearboxAssist u8 · m_speedUnitsLeadPlayer u8 · m_temperatureUnitsLeadPlayer u8 · m_gameMode u8 · m_ruleSet u8 · m_sector2LapDistanceStart f32 · m_sector3LapDistanceStart f32` (+ the remaining settings fields exactly as listed in S2; Appendix A shows they complete the 753-byte layout).

**LapData** (×22, 57 B each, plus 2 trailing bytes `m_timeTrialPBCarIdx`, `m_timeTrialRivalCarIdx`):
`m_lastLapTimeInMS u32 · m_currentLapTimeInMS u32 · m_sector1TimeMSPart u16 · m_sector1TimeMinutesPart u8 · m_sector2TimeMSPart u16 · m_sector2TimeMinutesPart u8 · m_deltaToCarInFrontMSPart u16 · m_deltaToCarInFrontMinutesPart u8 · m_deltaToRaceLeaderMSPart u16 · m_deltaToRaceLeaderMinutesPart u8 · m_lapDistance f32 · m_totalDistance f32 · m_safetyCarDelta f32 · m_carPosition u8 · m_currentLapNum u8 · m_pitStatus u8 · m_numPitStops u8 · m_sector u8 (0/1/2) · m_currentLapInvalid u8 · m_penalties u8 · m_totalWarnings u8 · m_cornerCuttingWarnings u8 · m_numUnservedDriveThroughPens u8 · m_numUnservedStopGoPens u8 · m_gridPosition u8 · m_driverStatus u8 · m_resultStatus u8 · m_pitLaneTimerActive u8 · m_pitLaneTimeInLaneInMS u16 · m_pitStopTimerInMS u16 · m_pitStopShouldServePen u8 · m_speedTrapFastestSpeed f32 · m_speedTrapFastestLap u8`
- A sector time = `MinutesPart × 60000 + MSPart` ms. LapData carries **only S1 and S2**; **S3 comes from SessionHistory** (or `currentLap − S1 − S2` live).
- `m_lapDistance` can be negative before the line is first crossed.
- `m_driverStatus`: 0 garage, 1 flying lap, 2 in-lap, 3 out-lap, 4 on track. `m_pitStatus`: 0 none, 1 pitting, 2 in pit area.

**CarTelemetryData** (×22) + trailer: `m_speed u16 (km/h) · m_throttle f32 (0–1) · m_steer f32 (−1…1) · m_brake f32 (0–1) · m_clutch u8 · m_gear i8 (R=−1, N=0) · m_engineRPM u16 · m_drs u8 · m_revLightsPercent u8 · m_revLightsBitValue u16 · m_brakesTemperature[4] u16 · m_tyresSurfaceTemperature[4] u8 · m_tyresInnerTemperature[4] u8 · m_engineTemperature u16 · m_tyresPressure[4] f32 (PSI) · m_surfaceType[4] u8`; trailer `m_mfdPanelIndex, m_mfdPanelIndexSecondaryPlayer, m_suggestedGear i8`.

**CarStatusData** (×22): `m_tractionControl · m_antiLockBrakes · m_fuelMix · m_frontBrakeBias · m_pitLimiterStatus · m_fuelInTank f32 · m_fuelCapacity f32 · m_fuelRemainingLaps f32 · m_maxRPM u16 · m_idleRPM u16 · m_maxGears · m_drsAllowed · m_drsActivationDistance u16 · m_actualTyreCompound · m_visualTyreCompound · m_tyresAgeLaps · m_vehicleFiaFlags i8 · m_enginePowerICE f32 · m_enginePowerMGUK f32 · m_ersStoreEnergy f32 · m_ersDeployMode · m_ersHarvestedThisLapMGUK f32 · m_ersHarvestedThisLapMGUH f32 · m_ersDeployedThisLap f32 · m_networkPaused`

**CarDamageData** (×22): `m_tyresWear[4] f32 (%) · m_tyresDamage[4] · m_brakesDamage[4] · m_tyreBlisters[4] · m_frontLeftWingDamage · m_frontRightWingDamage · m_rearWingDamage · m_floorDamage · m_diffuserDamage · m_sidepodDamage · m_drsFault · m_ersFault · m_gearBoxDamage · m_engineDamage · m_engineMGUHWear · m_engineESWear · m_engineCEWear · m_engineICEWear · m_engineMGUKWear · m_engineTCWear · m_engineBlown · m_engineSeized`

**SessionHistory** (one car per packet): `m_carIdx · m_numLaps · m_numTyreStints · m_bestLapTimeLapNum · m_bestSector1LapNum · m_bestSector2LapNum · m_bestSector3LapNum · m_lapHistoryData[100]{m_lapTimeInMS u32, m_sector1TimeInMS u16, m_sector1TimeMinutes u8, m_sector2TimeInMS u16, (minutes u8 — mis-labelled `m_sector1TimeMinutes` in the document, a typo), m_sector3TimeInMS u16, m_sector3TimeMinutes u8, m_lapValidBitFlags u8 (0x01 lap, 0x02 S1, 0x04 S2, 0x08 S3 valid)} · m_tyreStintsHistoryData[8]{m_endLap, m_tyreActualCompound, m_tyreVisualCompound}`

**MotionEx** (player only): `m_wheelSpeed[4] · m_wheelSlipRatio[4] · m_wheelSlipAngle[4] · m_wheelLatForce[4] · m_wheelLongForce[4] · m_wheelVertForce[4] · m_suspensionPosition/Velocity/Acceleration[4] · m_localVelocityX/Y/Z · m_angularVelocityX/Y/Z · m_frontWheelsAngle · m_frontAeroHeight · m_rearAeroHeight · m_chassisYaw · m_chassisPitch · m_wheelCamber[4] · m_wheelCamberGain[4]` and others.

**TyreSets:** `m_carIdx · m_tyreSetData[20]{m_actualTyreCompound, m_visualTyreCompound, m_wear, m_available, m_recommendedSession, m_lifeSpan, m_usableLife, m_lapDeltaTime i16, m_fitted} · m_fittedIdx`

**Participants:** `m_numActiveCars · m_participants[22]{m_aiControlled, m_driverId, m_networkId, m_teamId, m_myTeam, m_raceNumber, m_nationality, m_name[32], m_yourTelemetry, m_showOnlineNames, m_techLevel u16, m_platform, m_numColours, m_liveryColours[4]{red,green,blue}}`

**Event** string codes used: `SSTA, SEND, FLBK, SCAR, COLL, PENA, DRSE, DRSD, LGOT, FTLP, SPTP, OVTK, RDFL, CHQF`.

### 2.6 Enumerations needed (✅)
- **Track IDs (2025 format):** 0 Melbourne, 2 Shanghai, 3 Sakhir, 4 Catalunya, 5 Monaco, 6 Montreal, 7 Silverstone, 9 Hungaroring, 10 Spa, 11 Monza, 12 Singapore, 13 Suzuka, 14 Abu Dhabi, 15 Texas, 16 Brazil, 17 Austria, 19 Mexico, 20 Baku, 26 Zandvoort, 27 Imola, 29 Jeddah, 30 Miami, 31 Las Vegas, 32 Losail, 39 Silverstone (Rev), 40 Austria (Rev), 41 Zandvoort (Rev).
- **`m_formula`:** 0 F1 Modern, 1 F1 Classic, 2 F2, 3 F1 Generic, 4 Beta, 6 Esports, 8 F1 World, 9 F1 Elimination.
- **Surface types:** 0 Tarmac, 1 Rumble strip, 2 Concrete, 3 Rock, 4 Gravel, 5 Mud, 6 Sand, 7 Grass, 8 Water, 9 Cobblestone, 10 Metal, 11 Ridged.
- **Tyre compounds (F1 Modern, actual):** 16 C5, 17 C4, 18 C3, 19 C2, 20 C1, 21 C0, 7 inter, 8 wet. **Visual:** 16 soft, 17 medium, 18 hard, 7 inter, 8 wet.
- **ERS deploy mode:** 0 none, 1 medium, 2 hotlap, 3 overtake. **Traction control:** 0 off, 1 medium, 2 full. **Safety car:** 0 none, 1 full, 2 virtual, 3 formation lap. **FIA flag:** −1 unknown, 0 none, 1 green, 2 blue, 3 yellow.

---

## 3. Track data facts (✅ from the Shfonic README and `track-format.md`)

### 3.1 File format
One JSON per track, `<game>_<track>.json` (e.g. `f1-25_silverstone.json`; the JSON's own `game` field is `f1_25`). Coordinates are **world metres, X/Z horizontal, Y up**; polylines are `[[x, z], …]`.

| Key | Use in our app |
|---|---|
| `left_edge`, `right_edge` | track surface polygon |
| `pit_lane` | pit lane polyline (may be empty) |
| `sf_line {pos, heading}` | start/finish marker |
| `sectors [{index, pos, lap_dist_m}]` | cross-check of UDP sector distances |
| `sections [{turn, name, type, start_m, end_m, apex_m, severity, overtake, members}]` | corner labels, per-corner analysis; spans wrap when `start_m > end_m`; spans may overlap; types `corner/straight/chicane/complex/other` |
| `lines.<class>.racing_line` | ~400-point racing line, averaged over several laps; classes for F1 25 are `formula1`, `formula1_2026`, `f2` |
| `game_track_length_m` | sanity check vs Session `m_trackLength` |
| `orientation` | cosmetic rotation (degrees) |

### 3.2 Known accuracy limits (✅ stated by the author)
Maps are recorded **by hand on visual judgement, "not to any official specification"**; expect edges that drift, corner spans slightly off, disputable turn numbers. `gears` is **never recorded** (always `null` unless hand-filled). DRS zones are **not** in the format.

### 3.3 Coverage against the 2025 track-ID list

| ID | Track | Map available? |
|---|---|---|
| 0 | Melbourne | ✅ |
| 2 | Shanghai | ✅ |
| 3 | Sakhir | ✅ |
| 7 | Silverstone | ✅ |
| 9 | Hungaroring | ✅ |
| 10 | Spa | ✅ |
| 11 | Monza | ✅ |
| 12 | Singapore | ✅ |
| 13 | Suzuka | ✅ |
| 14 | Abu Dhabi | ✅ |
| 17 | Austria | ✅ (repo name "Red Bull Ring"; match to be confirmed by length check, V15) |
| 20 | Baku | ✅ |
| 26 | Zandvoort | ✅ |
| 27 | Imola | ✅ |
| 4, 5, 6, 15, 16, 19, 29, 30, 31, 32 | Catalunya, Monaco, Montreal, Texas, Brazil, Mexico, Jeddah, Miami, Las Vegas, Losail | ❌ no map |
| 39, 40, 41 | Silverstone / Austria / Zandvoort **Reverse** | ❌ no map |
| 42 | Madrid | Map exists, but id 42 only exists in the **2026** format → unreachable in 2025 mode |

**14 of 27 covered; 13 not.** Fallback (🛠): the **learned track** — record the player's `m_worldPositionX/Z` against `m_lapDistance` over one valid flying lap, draw it as a plain line labelled *"learned line — no edges"*. I will not invent edges. Sector markers still work (from Session). Corner labels are auto-detected from curvature + speed minima and labelled by distance, not turn number.

Build-time matching is by the JSON's `track` field + length check (not filename), because I could not list the repo directory (GitHub robots block) and so cannot assert exact slugs.

---

## 4. Architecture

### 4.1 Components (🛠)
```
F1 25 ──UDP :20777──▶ ingest (asyncio DatagramProtocol)
                        ├─ raw recorder → captures/*.f1udp   (length-prefixed, monotonic ts; replay + tests)
                        ├─ guard (format 2025, size per id) → decoder (numpy packed dtypes, zero-copy)
                        ├─ frame assembler (group ids 0,2,6,7,13 by m_overallFrameIdentifier)
                        ├─ live state (latest per packet, ring buffers)
                        ├─ lap segmenter → 1 m resampler → DuckDB / Parquet
                        ├─ analytics (sector colours, delta, state classifier, section metrics)
                        └─ FastAPI/uvicorn: WebSocket (UI frames @30 Hz + events) · REST · SSE (coach)
Browser (React+TS): [1 Map] [2 Sectors] [3 Graphs] [4 Values + AI Coach overlay]
```
Replay mode feeds the same pipeline from a `.f1udp` file, so the whole app is testable without the game.

### 4.2 Why no big-data engine (arithmetic in Appendix B; inputs are the spec's sizes and rates)
| Quantity | Value |
|---|---|
| Packets / s (60 Hz menu rate, all packets) | ≈ 355 |
| Bytes / s | ≈ 379 KB (**0.38 MB/s**) |
| Raw capture / hour | ≈ **1.37 GB** |
| Player-only columnar store (40 × float32 @ 60 Hz) | ≈ **35 MB / hour** uncompressed |
| All 22 cars, same columns | ≈ 760 MB / hour uncompressed |
| One 1 m-resampled reference lap (≤7000 m × 24 ch × 4 B) | ≈ 672 KB |

One Python process handles this. **DuckDB** (embedded, columnar, window functions for resampling, Parquet export) is the store. If you ever want multi-user/cloud, swap in TimescaleDB — an existing open-source F1 25 project (Telemetry Scan) already runs that way (TimescaleDB + Grafana + a Python parser).

**Storage policy (🛠):** player car at full rate; other cars at 10 Hz for position + LapData only; other cars' CarTelemetry stored only if "AI benchmark" is enabled (§7.3).

### 4.3 Concurrency (🛠)
- Event loop: receive → guard → decode → update live state. No disk I/O in the loop (raw recorder uses a queue + writer thread).
- Worker thread/process: lap finalisation, resampling, DuckDB writes, section metrics.
- UI frames throttled to 30 Hz; map interpolates between samples client-side.
- Loss handling: gaps in `m_overallFrameIdentifier` are counted and shown in a status badge; gaps ≤ 3 frames are linearly interpolated, longer gaps break the lap trace (lap not eligible as a reference).

---

## 5. Ingest rules in detail (🛠 built on ✅ facts)

1. **Session identity:** new `m_sessionUID` → new session row. `SSTA`/`SEND` events delimit sessions.
2. **Player car:** `header.m_playerCarIndex`; if Session `m_isSpectating = 1`, follow `m_spectatorCarIndex`. Split-screen: ignore `m_secondaryPlayerCarIndex` (v1 shows primary only).
3. **Frame join:** CarTelemetry, LapData, CarStatus, Motion, MotionEx share a frame → join on `m_overallFrameIdentifier`.
4. **Lap segmentation:** a lap boundary is `m_currentLapNum` incrementing for the player car. The completed lap is **finalised only when** SessionHistory for `m_carIdx = player` shows that lap (authoritative `m_lapTimeInMS`, sector times, `m_lapValidBitFlags`).
5. **Resampling:** within a lap, drop samples where `m_lapDistance` is not strictly increasing; interpolate every channel onto a **1 m grid** (`np.interp`), along with elapsed time `t(d) = m_currentLapTimeInMS / 1000`.
6. **Reference eligibility** (🛠): lap valid (`m_lapValidBitFlags & 0x01`), no pit status ≠ 0 during lap, `m_driverStatus` = 1 (flying), `m_safetyCarStatus` = 0 throughout, no `FLBK` event during lap, no frame gaps > 3, `m_pitStatus` = 0.
7. **Units for display:** data stays in km/h and °C (✅ as sent); UI converts using `m_speedUnitsLeadPlayer` / `m_temperatureUnitsLeadPlayer`.

---

## 6. Data model (DuckDB) 🛠

```sql
CREATE TABLE sessions(session_uid UBIGINT PRIMARY KEY, started TIMESTAMP, track_id TINYINT, track_length_m USMALLINT,
  formula UTINYINT, session_type UTINYINT, game_mode UTINYINT, weather UTINYINT, track_temp TINYINT, air_temp TINYINT,
  packet_format USMALLINT, game_major UTINYINT, game_minor UTINYINT);

CREATE TABLE laps(lap_id UBIGINT PRIMARY KEY, session_uid UBIGINT, car_idx UTINYINT, lap_num UTINYINT,
  lap_time_ms UINTEGER, s1_ms UINTEGER, s2_ms UINTEGER, s3_ms UINTEGER, valid_flags UTINYINT,
  tyre_actual UTINYINT, tyre_visual UTINYINT, tyre_age_laps UTINYINT, fuel_start FLOAT,
  weather UTINYINT, track_temp TINYINT, eligible_as_ref BOOLEAN, is_player BOOLEAN);

-- 1 m grid, player laps (and optionally AI laps)
CREATE TABLE lap_samples(lap_id UBIGINT, d_m USMALLINT, t_s FLOAT, speed FLOAT, throttle FLOAT, brake FLOAT, steer FLOAT,
  gear TINYINT, rpm USMALLINT, drs UTINYINT, x FLOAT, z FLOAT, g_lat FLOAT, g_long FLOAT,
  ers_store FLOAT, ers_deployed FLOAT, ers_harv_k FLOAT, ers_harv_h FLOAT,
  slip_ratio_rl FLOAT, slip_ratio_rr FLOAT, slip_ratio_fl FLOAT, slip_ratio_fr FLOAT,
  slip_ang_rl FLOAT, slip_ang_rr FLOAT, slip_ang_fl FLOAT, slip_ang_fr FLOAT,
  surf_rl UTINYINT, surf_rr UTINYINT, surf_fl UTINYINT, surf_fr UTINYINT, PRIMARY KEY(lap_id, d_m));

-- lap-level aggregates of slow channels (wheel order RL, RR, FL, FR)
CREATE TABLE lap_slow(lap_id UBIGINT PRIMARY KEY,
  wear_rl FLOAT, wear_rr FLOAT, wear_fl FLOAT, wear_fr FLOAT,
  tyre_dmg_rl FLOAT, tyre_dmg_rr FLOAT, tyre_dmg_fl FLOAT, tyre_dmg_fr FLOAT,
  tyre_surf_avg_rl FLOAT, tyre_surf_avg_rr FLOAT, tyre_surf_avg_fl FLOAT, tyre_surf_avg_fr FLOAT,
  tyre_inner_avg_rl FLOAT, tyre_inner_avg_rr FLOAT, tyre_inner_avg_fl FLOAT, tyre_inner_avg_fr FLOAT,
  tyre_press_avg_rl FLOAT, tyre_press_avg_rr FLOAT, tyre_press_avg_fl FLOAT, tyre_press_avg_fr FLOAT,
  brake_temp_max_rl FLOAT, brake_temp_max_rr FLOAT, brake_temp_max_fl FLOAT, brake_temp_max_fr FLOAT,
  blisters_rl FLOAT, blisters_rr FLOAT, blisters_fl FLOAT, blisters_fr FLOAT,
  dmg_fl_wing UTINYINT, dmg_fr_wing UTINYINT, dmg_rear_wing UTINYINT, dmg_floor UTINYINT, dmg_diffuser UTINYINT, dmg_sidepod UTINYINT,
  drs_fault UTINYINT, ers_fault UTINYINT, gearbox_dmg UTINYINT, engine_dmg UTINYINT);

CREATE TABLE section_metrics(lap_id UBIGINT, seg_id USMALLINT, t_in_s FLOAT, t_out_s FLOAT, v_in FLOAT, v_min FLOAT, v_out FLOAT,
  brake_on_m FLOAT, brake_peak FLOAT, brake_off_m FLOAT, trail_m FLOAT, throttle_on_m FLOAT, full_thr_m FLOAT, coast_m FLOAT,
  gear_apex TINYINT, steer_peak FLOAT, slip_ang_peak FLOAT, offtrack_m FLOAT, PRIMARY KEY(lap_id, seg_id));

CREATE TABLE coach_runs(run_id UBIGINT PRIMARY KEY, ts TIMESTAMP, session_uid UBIGINT, lap_id UBIGINT, ref_lap_id UBIGINT,
  next_sector UTINYINT, inputs_json JSON, synth_json JSON);
CREATE TABLE coach_domain_outputs(run_id UBIGINT, domain VARCHAR, model VARCHAR, output_json JSON, latency_ms UINTEGER, valid BOOLEAN);
```
Raw `.f1udp` captures are never deleted automatically (they are the regression corpus).

---

## 7. "Expected" values — the reference store

### 7.1 Decision: compute locally (no API)
I searched for an API that supplies reference telemetry for F1 25 and found **none**:
- **OpenF1 / FastF1** serve *real* F1 telemetry. Real cars ≠ game physics, so they are not valid targets for game laps. Not used.
- **F1Laps** hosts community F1 25 leaderboards "with telemetry", but I found **no public API** documentation. Not used.
- The game's own UDP gives **PB/rival sector times only** in Time Trial (`PacketTimeTrialData`), no traces.

So "expected" = **your own recorded laps**, plus an optional AI benchmark.

### 7.2 Reference types (🛠 final)
1. **PB reference (default):** your fastest *eligible* lap for key `(track_id, formula, actual compound)`, preferring the same weather bucket (dry = `m_weather` 0–2, wet = 3–5). Fallback order: drop compound → drop weather → none.
2. **Theoretical best (potential):** per-segment minimum time over all eligible laps in the key. Used **only for time targets** (it is not a physically continuous trace, so never drawn as one).
3. **Cold start:** with no eligible lap the "Expected" and "Δ" columns show "—" and the coach button is disabled with the reason shown.

### 7.3 AI benchmark (optional, off by default) 🔬 V6
Offline, CarTelemetry arrives for all 22 cars, so the fastest eligible AI lap can serve as a reference. Caveat: AI laps happen in traffic and depend on AI level. Time-Trial ghost telemetry availability is 🔬 V7 — not assumed.

### 7.4 Segment partition (makes loss attribution add up)
Build a **partition** of `[0, m_trackLength)` from Shfonic `sections` (corners, chicanes, straights), splitting overlaps at midpoints and filling gaps with unnamed `gap` segments; `complex` entries are labels over their members and are not segments. Because segments partition the lap, **Σ segment Δ = lap Δ** exactly. Learned-track fallback uses auto-detected corners instead.

---

## 8. Panel specifications

### Panel 1 — Top-left: live 2D track map
- **Static layer** (offscreen canvas, redrawn on resize): `left_edge`/`right_edge` surface, `pit_lane`, `sf_line`, corner labels (`turn`, placed at `apex_m` projected onto the racing line), sector boundary ticks.
- **Sector boundaries on the map:** arc length along `racing_line`, **scaled so its total = Session `m_trackLength`** (🔬 V13 checks the ratio), then positioned at `m_sector2LapDistanceStart` / `m_sector3LapDistanceStart`. Cross-checked against the file's `sectors[].lap_dist_m`; mismatch > 25 m (🛠 tunable) → offset/scale applied and logged.
- **Dynamic layer:** each active car at `(m_worldPositionX, m_worldPositionZ)`. Colour = `m_liveryColours[0]` (if `m_numColours > 0`) else team colour; label = `m_raceNumber`. **Player:** larger marker with a ring and a heading arrow from `m_worldForwardDirX/Z ÷ 32767`. Cars with `m_pitStatus ≠ 0` drawn hollow. Cars with `m_resultStatus` 0/1 hidden.
- **Yellow-flag overlay:** `m_marshalZones[i].m_zoneStart` (fraction of lap) + `m_zoneFlag = 3` shades that stretch; per-car `m_vehicleFiaFlags` shown as a ring.
- **Smoothness:** the browser interpolates between the last two samples by `m_sessionTime` and extrapolates up to 100 ms (🛠) using `m_worldVelocityX/Z`.
- **Coordinate calibration (mandatory, 🔬 V5):** the repo says X/Z are "world metres", but I could not confirm it is the identical frame to the UDP `m_worldPositionX/Z`. At session start, collect ~300 player positions and test the **8 axis variants** (swap X/Z × sign flips) against `racing_line` by nearest-point median residual; pick the lowest; if the best residual > 15 m (🛠 tunable) show badge "map mismatch" and switch to the learned-line fallback. No assumption is baked in.
- **Class selection (🛠):** `m_formula` 0 → `lines.formula1`, 2 → `lines.f2`; any other formula → learned line. Validated by the same residual test.
- **Names:** `m_name` is used when present; online it may be absent depending on players' telemetry settings (✅ reported by KRF1), so fallback = team + `m_raceNumber`.

### Panel 2 — Bottom-left: sectors, colours and timing
Three sector blocks. Boundaries from Session (`m_sector2LapDistanceStart`, `m_sector3LapDistanceStart`; S1 starts at 0).

| Element | Source |
|---|---|
| Running current-lap time | `m_currentLapTimeInMS` |
| Current sector | `m_sector` (0/1/2) |
| S1 / S2 completed time | `m_sector1TimeMinutesPart×60000 + m_sector1TimeMSPart` (same for S2) |
| S3 live | `m_currentLapTimeInMS − S1 − S2` |
| Completed lap's sector times (authoritative) | SessionHistory `m_lapHistoryData[lap].m_sectorNTimeInMS (+ minutes)` |
| Validity per sector | `m_lapValidBitFlags` bits 0x02 / 0x04 / 0x08; live lap `m_currentLapInvalid` |

**Colours (assigned when a sector completes; 🛠 mapping of your purple/green/red):**
- **Purple** = time ≤ the best valid time for that sector by **any car** in the session. Computed as the minimum, over all cars, of `m_lapHistoryData[m_bestSectorNLapNum − 1].m_sectorNTimeInMS` from each car's SessionHistory (each car refreshes at least ~1/s in a 20-car field per EA's text; indexing is 🔬 V14).
- **Green** = personal best for that sector (not purple).
- **Red** = slower than personal best. (F1 TV uses yellow here; red is what you asked for.)
- **Grey** = not reached / invalid sector.
- A sector in progress is neutral with a live Δ vs your PB sector pace, so colours never flicker mid-sector.

**Also shown:** last lap, best lap, live Δ to reference (`t_user(d) − t_ref(d)`, see §7), lap number, `m_currentLapInvalid` banner, `m_penalties`, `m_deltaToCarInFront…` (for traffic context). In Time Trial, `PacketTimeTrialData.m_personalBestDataSet` sector times are also shown.

> **Not available:** official mini-sectors. EA's community manager stated there were no plans to add them (as of that reply). Panel 2 therefore uses exactly **3 official sectors**. The Δ-per-segment strip in Panel 3 is our own analysis, visibly labelled as such, and **not** coloured as timing.

### Panel 3 — Top-right: live graphs
X axis = **lap distance (m)**, 0…`m_trackLength`, shared cursor and zoom across charts. uPlot, 30 Hz redraw.

| Chart | Series | Scale |
|---|---|---|
| A Speed | `m_speed` (live, solid) vs reference (dashed) | y from 0 to `ceil(1.05 × ref max / 50) × 50`, fixed per lap so the trace doesn't jitter (🛠) |
| B Pedals | `m_throttle` ×100 (green) and `m_brake` ×100 (red), live vs reference | fixed 0–100 % |
| C Delta & gear | cumulative Δ time (s); gear steps and `m_steer` toggle | symmetric auto-range |
| D "Normalised overlay" (tab) | throttle, brake and speed all scaled 0–100 % on one axis (speed ÷ ref max) | 0–100 % |

**Markings (🛠 from ✅ data):** sector lines (Session distances); corner bands from Shfonic `sections` (`start_m`–`end_m`, label `turn`, tick at `apex_m`); derived brake zones (`m_brake ≥ ε`), coast spans, DRS-on spans (`m_drs = 1`), pit entry/exit if recorded. Live trace draws progressively to the cursor; previous lap fades.
A second mode shows a rolling 10 s (🛠) time window for debugging.

### Panel 4 — Bottom-right: values, expected vs ours, Δ, AI coach

**Driving-state classifier** (60 Hz; thresholds are 🛠 tunable defaults, ε = 0.02, full = 0.98):

| State | Rule |
|---|---|
| FULL THROTTLE | `throttle ≥ 0.98` and `brake < ε` |
| ACCEL (partial) | `ε ≤ throttle < 0.98` and `brake < ε` |
| BRAKING | `brake ≥ ε` and `throttle < ε` |
| TRAIL / OVERLAP | `brake ≥ ε` and `throttle ≥ ε` |
| **COASTING** | `throttle < ε` and `brake < ε` (and `m_speed` above a standstill threshold) |
| LOCK-UP flag | braking and `m_wheelSlipRatio[i]` below a negative threshold — **threshold must be calibrated from capture** (spec gives no range) 🔬 V12 |
| WHEELSPIN flag | `throttle ≥ ε` and `m_wheelSlipRatio[i]` above a positive threshold (same calibration) |
| OFF-TRACK | any `m_surfaceType[i]` ∈ {4 gravel, 5 mud, 6 sand, 7 grass}; kerb = {1 rumble, 11 ridged} |

**Value table** — each row: *Now · Expected (reference at same `m_lapDistance`) · Δ*

| Row | Source fields | Expected from |
|---|---|---|
| Speed | `m_speed` | reference speed(d) |
| Throttle / Brake | `m_throttle`, `m_brake` | reference(d) |
| Gear / RPM | `m_gear`, `m_engineRPM` (limit `m_maxRPM`) | reference(d) |
| Steering | `m_steer` | reference(d) |
| G-force | `m_gForceLateral`, `m_gForceLongitudinal` | reference(d) |
| DRS | `m_drs`, `m_drsAllowed`, `m_drsActivationDistance` | reference(d) |
| ERS | `m_ersStoreEnergy`, `m_ersDeployMode`, `m_ersDeployedThisLap`, `m_ersHarvestedThisLapMGUK/MGUH` | reference lap at same d |
| Fuel | `m_fuelInTank`, `m_fuelRemainingLaps` | n/a (trend) |
| Tyres | `m_tyresWear[4]`, `m_tyresSurfaceTemperature[4]`, `m_tyresInnerTemperature[4]`, `m_tyresPressure[4]`, `m_tyreBlisters[4]`, `m_tyresAgeLaps`, compound | reference lap's lap-averages |
| Brakes | `m_brakesTemperature[4]`, `m_brakesDamage[4]` | reference lap's maxima |
| Slip (player only) | `m_wheelSlipRatio[4]`, `m_wheelSlipAngle[4]` | reference(d) |
| Lap Δ (s) | `t_user(d) − t_ref(d)` | — |

Δ colouring: ahead/behind with hysteresis so numbers don't flicker.

**Unit display:** speed/temperature units follow the game's `m_speedUnitsLeadPlayer`/`m_temperatureUnitsLeadPlayer`.

**AI Coach button:** enabled when ≥ 1 eligible reference lap exists and ≥ 1 completed lap this session. Opens an overlay (§10).

---

## 9. Layout, visual design and performance budget (🛠)

- **Layout:** 2 × 2 CSS grid, panels resizable; Panel 4's coach overlay is a modal drawer over Panel 4 only so the map and graphs stay visible while it streams.
- **Colours:** sector purple `#A855F7`, green `#22C55E`, red `#EF4444`, neutral/grey `#6B7280`; throttle green, brake red, speed white/blue; reference traces always dashed.
- **Theme:** dark by default (in-car lighting), light theme via CSS variables.
- **Map rendering:** static layer cached; dynamic layer ≤ 22 markers, redrawn each animation frame.
- **Budgets (targets, to be measured in M1/M5 — not claims):** decode + state update < 1 ms per datagram on a mid-range laptop; UI stays at 30 fps with 4 panels; WebSocket payload per UI frame < 8 KB.
- **Settings screen:** UDP port, classifier thresholds (ε, full-throttle), reference mode (PB / AI benchmark), units, coach models, API key.
- **Status bar:** UDP format badge, packets/s, frame-gap count, session type, reference lap in use.

---

## 10. AI Coach

### 10.1 Principle
**LLMs never compute. They interpret numbers I computed.** Every time, speed, distance and Δ in the prompt comes from DuckDB; every number in the answer is checked against the prompt (§10.5).

### 10.2 Trigger and scope
On click: snapshot = last completed lap, reference lap, current partial lap. **Upcoming sector** = `m_sector + 1` (S3 → next lap's S1). The question answered: *"Why did I lose time in this sector on the last lap, and at which turns?"*

### 10.3 Deterministic feature pass (no LLM)
1. Cumulative delta curve Δ(d) = `t_last(d) − t_ref(d)`.
2. For each segment inside the upcoming sector: `Δ_segment = Δ(end) − Δ(start)`; rank by loss. Mark a segment **"inherited"** when its entry-speed deficit is the dominant cause (the loss started upstream), so blame isn't misplaced.
3. Per-segment metrics (table `section_metrics`): `v_in, v_min, v_out, brake_on_m, brake_peak, brake_off_m, trail_m, throttle_on_m, full_thr_m, coast_m, gear_apex, steer_peak, slip_ang_peak, offtrack_m`.
4. Lap-level: tyre wear/temp/pressure trends over the last N laps, ERS deploy/harvest totals, damage values, fuel, weather/track temp.

### 10.4 Domain agents (parallel; each sees only its slice)
| # | Domain | Evidence fields |
|---|---|---|
| 1 | Braking | brake points, peak, release, trail, lock-up flags, `m_brakesTemperature` |
| 2 | Throttle & traction | pick-up distance, full-throttle metres, wheelspin flags, `m_tractionControl` |
| 3 | Corner speed & line | `v_min`, steer, `m_wheelSlipAngle`, lateral G, off-track metres, deviation from Shfonic racing line (flagged as approximate, §3.2) |
| 4 | Tyres | wear per wheel, surface/inner temp, pressure, blisters, age, compound |
| 5 | Gears & engine | gear at apex vs reference, shift points, RPM vs `m_maxRPM`, `m_engineTemperature` |
| 6 | ERS & DRS | deploy mode, store, harvest/deploy vs reference, DRS usage |
| 7 | Damage & aero (conditional) | runs only if any damage field > 0 or `m_drsFault`/`m_ersFault` |
| 8 | Conditions & fuel (conditional) | runs only if weather / track temp / fuel load differ from the reference lap beyond a threshold (🛠) |

**Output schema (enforced + validated):**
```json
{"domain":"braking","verdict":"losing|neutral|gaining|insufficient_data","confidence":0.0,
 "findings":[{"seg_id":12,"turn":"4","evidence":{"metric":"brake_on_m","yours":0,"reference":0,"unit":"m"},
              "est_time_cost_s":0.0,"advice":"…"}],
 "data_gaps":["…"]}
```
A **synthesizer** call merges domain outputs into a per-turn ranked list plus a 3-item "next lap focus". Its time allocations must sum to ≤ the deterministic `Δ_segment`.

### 10.5 Guardrails
- Prompt contains only numbers I supply; instruction: *"Use only supplied values; if evidence is missing, return insufficient_data."*
- **Numeric guard:** parse every number in the output; any not within tolerance of the input set → the finding is dropped and logged.
- **Cap:** `est_time_cost_s` per finding ≤ that segment's measured Δ; Σ per segment ≤ Δ_segment.
- Per-call timeout 30 s (🛠), one retry, partial results shown as cards stream in (SSE). A failed domain shows "unavailable", never blocks the rest.
- API key server-side only; payload is numeric summaries, not raw telemetry.

- **Provider:** Gemini API via Google AI Studio. Keep the API key server-side (for example, `GEMINI_API_KEY`); never expose it to the browser or store it in source control.
- Model IDs, pricing, SDK behavior, and routing are deliberately deferred to M6 and must be checked against current Google AI Studio documentation before implementation.
- Keep the coaching adapter isolated so model IDs can be changed without changing deterministic feature extraction or output validation.
- Target latency ≤ 15 s end-to-end (🛠 goal, not a measurement).

---

## 11. What cannot be implemented (or only in reduced form)

| # | Feature | Why | What we do instead |
|---|---|---|---|
| 1 | Official mini-sector timing/colours | EA said no plans to add mini-sectors | 3 official sectors; own Δ-per-segment strip (not styled as timing) |
| 2 | DRS zone markers from data | The 2025 format has no DRS-zone fields (they exist only in the 2026 format) | Derive from `m_drs` transitions and `m_drsActivationDistance`; zones appear after first observation |
| 3 | Map edges for 13 of 27 track IDs; Madrid in 2025 mode | No community map / id 42 is 2026-only | Learned line without edges; contribute maps back to Shfonic (CC BY 4.0, PRs accepted) |
| 4 | "Perfect" track edges on mapped tracks | Maps are hand-recorded by visual judgement | Residual check + corner spans reconciled to the measured speed minimum ±window |
| 5 | Recommended gear per corner from track data | Shfonic `gears` is never recorded | Gear comparison vs **your own** reference lap; `m_suggestedGear` only as player hint |
| 6 | Reference traces from an external API | None exists for game physics | Own PB + theoretical best; optional AI benchmark |
| 7 | Rival telemetry/setups online | Restricted unless players choose Public; setups blank | Offline AI only; online shows what the game allows |
| 8 | Slip, forces, camber for other cars | MotionEx is player-only | Domain agents 1–3 for player only |
| 9 | Per-corner tyre wear | `m_tyresWear` is a percentage per wheel at a fixed, coarse rate | Lap-over-lap trend only; no per-corner wear claims |
| 10 | Lap-time model of tyre degradation | Not in UDP | Coach correlates, states it is correlation |
| 11 | Data while replaying/paused | Packet table: Motion is sent only while the player is in control | Banner "no data"; lap marked ineligible |
| 12 | Guaranteed delivery | UDP is lossy | Frame-gap counter; short-gap interpolation; lap excluded if long gap |

---

## 12. Verification matrix

### Done in this session
| ID | Check | Result |
|---|---|---|
| D1 | Rebuild all 16 packet layouts, compare to EA's sizes | **16/16 match** (Appendix A) |
| D2 | Cross-check sizes vs independent Rust crate constants | match |
| D3 | 2025 vs 2026 format differences identified | listed in §2.1 |
| D4 | LLM provider decision | Google AI Studio Gemini API; model IDs and pricing deferred to M6 |

### Milestone M0 — capture-based tests (≈ 1 session in game; each has a pass rule)
| ID | Unknown | Test | Pass rule |
|---|---|---|---|
| V0 | Official spec equals transcription | Diff attachment vs §2.5 | no differences |
| V1 | UDP format selection works | Start capture | `m_packetFormat == 2025` on every packet |
| V2 | LapData field order (`m_gridPosition` vs `m_driverStatus`) | Start a race, read all 22 cars | gridPosition = unique 1…22; driverStatus ∈ 0…4 |
| V3 | CarDamage rate (spec says 10/s; FAQ example 2/s) | Measure inter-arrival | record Hz; design uses measured value |
| V4 | LapData sector fields on lap start | Log S1/S2 values across a lap boundary | know whether they hold or reset; code to match |
| V5 | Shfonic X/Z frame vs UDP X/Z | §8 residual test on 14 maps | best variant found, median residual ≤ 15 m |
| V6 | Motion array has all 22 cars | Count non-zero positions in a 20-car race | 20+ non-zero |
| V7 | Time Trial ghost telemetry present | TT session, indexes `m_timeTrialPBCarIdx`/`RivalCarIdx` | yes/no recorded |
| V8 | Online names availability | One online lobby | fallback verified |
| V9 | Send-rate options in menu | Read menu | record options |
| V10 | `m_lapDistance` at start/finish | Log across line | wrap and negative values understood |
| V11 | Wheel order | Brake hard, see which `m_brakesTemperature[i]` rise first on a front-biased car / or compare with MotionEx | matches RL,RR,FL,FR |
| V12 | Slip ratio/angle ranges; ERS and fuel units | Log a lap with lock-up and wheelspin; compare ERS store to the MFD | thresholds and units set from data |
| V13 | Racing-line length vs `m_trackLength` and `game_track_length_m` | compute | within 1 % (🛠) |
| V14 | `m_bestSectorNLapNum` indexing (1-based?) | compare against lap history | rule recorded |
| V15 | Austria ↔ "Red Bull Ring" match | length compare | within 1 % |

**Gate:** parser goes live only after V1, V2, V4, V5 pass.

---

## 13. Decision log (every "when in doubt" compromise)

| Doubt | Compromise |
|---|---|
| Official spec file unreachable | Transcription + byte-size proof; M0 task V0 |
| Need big-data engine? | No; DuckDB + Parquet; numbers in §4.2 |
| Which "expected"? | PB lap (traces) + theoretical best (times only) |
| No API for references | Local; AI benchmark optional |
| Your red vs F1's yellow | Red, as requested |
| No mini-sectors in UDP | 3 sectors; own strip labelled as analysis |
| Missing tracks | Learned line, no invented edges |
| DRS zones absent in 2025 format | Learn from `m_drs` |
| LLM hallucination risk | Deterministic numbers, schema, numeric guard, caps |
| LLM provider | Gemini API via Google AI Studio; verify model IDs, pricing, and limits during M6 |
| Split-screen / spectator | Primary player only; spectator car followed |
| 60 Hz vs lower rate | Recommend the highest rate offered by the menu (V9) |

---

## 14. Milestones

| M | Deliverable | Exit test |
|---|---|---|
| M0 | Capture tool + V0–V15 | gate above passed |
| M1 | Ingest, guard, decode, recorder, replay | replay of capture reproduces identical decoded stream (hash) |
| M2 | Panel 1 map + calibration + learned-line fallback | residual test on 14 maps; 30 fps with 22 cars |
| M3 | Lap segmenter, resampler, DuckDB, reference store | ref lap built from capture; Σ segment Δ = lap Δ |
| M4 | Panel 2 sectors/colours | purple/green/red match in-game timing screen on 3 laps |
| M5 | Panel 3 graphs, Panel 4 values/classifier | visual diff against recorded lap |
| M6 | AI coach + eval harness | numeric-guard pass rate and manual review on 10 recorded laps |
| M7 | Packaging, settings, attribution screen | clean install on a second machine |
| M8 (stretch) | Track-edge estimation from car-position envelope for unmapped tracks | not promised |

Test strategy: struct-size test (Appendix A) in CI; golden-file tests on recorded captures; replay-speed ×4 soak test; fuzz test (truncated/garbage datagrams must never crash the loop).

---

## 15. Sources
- **S1** EA SPORTS F1 25 UDP Specification (EA forums post, versions 6.0 / 9.0) — summary only reachable.
- **S2** `MacManley/f1-25-udp` README — full transcription of the F1 25 spec (structs, appendices, FAQ).
- **S3** `MacManley/f1-26-udp` README — 2026 format differences.
- **S4** Shfonic Dash Tracks `README.md` and `track-format.md` (CC BY 4.0).
- **S5** docs.rs `f1-game-library-models-25` 0.5.0 — independent size constants and header layout.
- **S6** EA forum UDP-spec discussion — LapData field-order report; "no plans for mini sectors".
- **S7** `andj1210/F1GameSessionDisplay` (KRF1) — port 20777; online-name limitation.
- **S8** `alisezisli/Telemetry-Scan` — TimescaleDB + Grafana architecture precedent; packet sizes observed in the wild match the spec.
- **S9** Google AI Studio Gemini API docs — verify model availability, pricing, and limits during M6.
- **S10** OpenF1 / FastF1 — real-F1 data only. **S11** F1Laps — community leaderboard, no public API found.

**Attribution to display in the app (required by licence):**
> Track maps from **Shfonic Dash Track Maps** (https://github.com/shfonic/ShfonicDashTracks) © Richard Hawes and contributors, licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

F1® 25 is an official product of the FIA Formula One World Championship™; this tool is unaffiliated.

---

## Appendix A — Struct-size verification script and output

```python
"""Rebuild F1 25 (UDP format 2025) packet layouts from the transcribed EA spec; compare to published sizes."""
import struct
S={'u8':1,'i8':1,'u16':2,'i16':2,'u32':4,'f':4,'u64':8,'d':8}
def sz(*fields): return sum(S[t]*c for t,c in fields)
HDR = sz(('u16',1),('u8',5),('u64',1),('f',1),('u32',2),('u8',2))

motion  = HDR + 22*sz(('f',6),('i16',6),('f',6))
session = HDR + sz(
  ('u8',1),('i8',2),('u8',1),('u16',1),('u8',1),('i8',1),('u8',1),('u16',2),('u8',6),   # weather..numMarshalZones
  ('f',21),('i8',21),                                                                   # marshalZones[21]
  ('u8',3)) + 64*sz(('u8',3),('i8',4),('u8',1)) + sz(                                    # forecast samples[64]
  ('u8',2),('u32',3),('u8',3),('u8',11),('u32',1),('u8',1),('u8',4),('u8',3),('u8',24),
  ('u8',1),('u8',12),('f',2))
lapdata = HDR + 22*sz(('u32',2),('u16',1),('u8',1),('u16',1),('u8',1),('u16',1),('u8',1),('u16',1),('u8',1),
                      ('f',3),('u8',14),('u8',1),('u16',2),('u8',1),('f',1),('u8',1)) + 2
participants = HDR + 1 + 22*sz(('u8',7),('u8',32),('u8',2),('u16',1),('u8',2),('u8',12))
setups  = HDR + 22*sz(('u8',4),('f',4),('u8',9),('f',4),('u8',1),('f',1)) + 4
telem   = HDR + 22*sz(('u16',1),('f',2),('f',1),('u8',1),('i8',1),('u16',1),('u8',1),('u8',1),('u16',1),
                      ('u16',4),('u8',4),('u8',4),('u16',1),('f',4),('u8',4)) + 3
status  = HDR + 22*sz(('u8',5),('f',3),('u16',2),('u8',2),('u16',1),('u8',3),('i8',1),('f',3),('u8',1),('f',3),('u8',1))
status  = status  # (fields in spec order; byte-sum is order independent)
finalcl = HDR + 1 + 22*sz(('u8',7),('u32',1),('d',1),('u8',3),('u8',24))
lobby   = HDR + 1 + 22*sz(('u8',4),('u8',32),('u8',3),('u16',1),('u8',1))
damage  = HDR + 22*sz(('f',4),('u8',4),('u8',4),('u8',4),('u8',18))
hist    = HDR + sz(('u8',7)) + 100*sz(('u32',1),('u16',3),('u8',3),('u8',1)) + 8*3
tyresets= HDR + 1 + 20*sz(('u8',7),('i16',1),('u8',1)) + 1
motionex= HDR + sz(('f',4*8),('f',1),('f',9),('f',1),('f',4),('f',2),('f',2),('f',2),('f',4),('f',4))
timetrial = HDR + 3*sz(('u8',2),('u32',4),('u8',6))
lappos  = HDR + 2 + 50*22
event   = HDR + 4 + 12   # largest union member: SpeedTrap = u8+f+u8+u8+u8+f = 12

pub = dict(motion=1349,session=753,lapdata=1285,participants=1284,setups=1133,telem=1352,status=1239,
           finalcl=1042,lobby=954,damage=1041,hist=1460,tyresets=231,motionex=273,timetrial=101,lappos=1131,event=45)
mine= dict(motion=motion,session=session,lapdata=lapdata,participants=participants,setups=setups,telem=telem,
           status=status,finalcl=finalcl,lobby=lobby,damage=damage,hist=hist,tyresets=tyresets,motionex=motionex,
           timetrial=timetrial,lappos=lappos,event=event)
for k in pub: print(f"{k:13s} published={pub[k]:5d}  rebuilt={mine[k]:5d}  {'OK' if pub[k]==mine[k] else 'MISMATCH'}")
```

Output:
```
motion        published= 1349  rebuilt= 1349  OK
session       published=  753  rebuilt=  753  OK
lapdata       published= 1285  rebuilt= 1285  OK
participants  published= 1284  rebuilt= 1284  OK
setups        published= 1133  rebuilt= 1133  OK
telem         published= 1352  rebuilt= 1352  OK
status        published= 1239  rebuilt= 1239  OK
finalcl       published= 1042  rebuilt= 1042  OK
lobby         published=  954  rebuilt=  954  OK
damage        published= 1041  rebuilt= 1041  OK
hist          published= 1460  rebuilt= 1460  OK
tyresets      published=  231  rebuilt=  231  OK
motionex      published=  273  rebuilt=  273  OK
timetrial     published=  101  rebuilt=  101  OK
lappos        published= 1131  rebuilt= 1131  OK
event         published=   45  rebuilt=   45  OK
```

## Appendix B — Load, storage and cost arithmetic

```python
# Worst-case UDP load (sizes and rates from the EA spec; menu-rate packets assumed at 60 Hz)
menu = {'motion':1349,'lapdata':1285,'telemetry':1352,'status':1239,'motionex':273}
fixed = {'damage':(1041,10),'session':(753,2),'setups':(1133,2),'history':(1460,20),'tyresets':(231,20),
         'participants':(1284,0.2),'lappositions':(1131,1)}
hz = 60
b  = sum(menu.values())*hz + sum(s*f for s,f in fixed.values())
pk = len(menu)*hz + sum(f for s,f in fixed.values())
print(f"packets/s ~ {pk:.0f}")
print(f"bytes/s   ~ {b:,.0f}  = {b/1e6:.2f} MB/s  = {b*3600/1e9:.2f} GB/hour raw")
cols = 40; per_s = cols*4*hz
print(f"player-only 40 float32 cols @60Hz: {per_s*3600/1e6:.1f} MB/hour (uncompressed)")
print(f"all 22 cars same cols: {per_s*22*3600/1e6:.0f} MB/hour (uncompressed)")
print(f"1 m resampled lap, 7000 m x 24 ch x 4 B = {7000*24*4/1e3:.0f} KB")
```

Output:
```
packets/s ~ 355
bytes/s   ~ 379,270  = 0.38 MB/s  = 1.37 GB/hour raw
player-only 40 float32 cols @60Hz: 34.6 MB/hour (uncompressed)
all 22 cars same cols: 760 MB/hour (uncompressed)
1 m resampled lap, 7000 m x 24 ch x 4 B = 672 KB
```
