import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  displayNumber,
  formatTime,
  isNumber,
  percent,
  MiniChart,
  PanelHeading,
  Stat,
  TrackMap,
  TRACK_FILES,
  TRACK_NAMES,
  type Car,
  type LapSample,
  type LapSummary,
  type Player,
  type PlotPoint,
  type Position,
  type Session,
  type TrackOutline,
} from "./DashboardShared";
import CarStatusPanel from "./CarStatusPanel";
import { getStoredSessions, getSessionLaps, type StoredSession, type StoredLap } from "../api/lapComparison";

export interface TelemetryReplayPanelProps {
  liveLaps?: LapSummary[];
  currentSession?: Session;
  currentTrackOutline?: TrackOutline | null;
  livePlayer?: Player;
}

type SectorScope = "full" | "s1" | "s2" | "s3";

function findNearestSample(
  samples: LapSample[],
  targetMs: number,
): { sample: LapSample; index: number } | null {
  if (!samples || samples.length === 0) return null;
  let low = 0;
  let high = samples.length - 1;
  let best = 0;
  while (low <= high) {
    const mid = (low + high) >> 1;
    const t = samples[mid].elapsedTimeMs ?? 0;
    if (t <= targetMs) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return { sample: samples[best], index: best };
}

export default function TelemetryReplayPanel({
  liveLaps = [],
  currentSession,
  currentTrackOutline,
  livePlayer,
}: TelemetryReplayPanelProps) {
  // Source tabs: "live" (current session's recorded / in-progress laps) vs "stored" (DuckDB / SQLite database)
  const [sourceMode, setSourceMode] = useState<"current" | "database">("current");

  // Database session selection
  const [dbSessions, setDbSessions] = useState<StoredSession[]>([]);
  const [selectedDbSessionId, setSelectedDbSessionId] = useState<string>("");
  const [dbLaps, setDbLaps] = useState<StoredLap[]>([]);
  const [loadingDb, setLoadingDb] = useState(false);
  const [dbError, setDbError] = useState("");

  // In-progress lap fetched from /api/laps/current
  const [inProgressLap, setInProgressLap] = useState<LapSummary | null>(null);

  // Available laps list for replay
  const [selectedLapId, setSelectedLapId] = useState<string>("");
  const [activeLap, setActiveLap] = useState<LapSummary | null>(null);
  const [loadingTrace, setLoadingTrace] = useState(false);

  // Track outline state (if replaying another track)
  const [replayTrackOutline, setReplayTrackOutline] = useState<TrackOutline | null>(null);

  // Playback state
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [isLooping, setIsLooping] = useState<boolean>(true);
  const [sectorScope, setSectorScope] = useState<SectorScope>("full");
  const [currentTimeMs, setCurrentTimeMs] = useState<number>(0);

  // Scrubber dragging state
  const scrubberRef = useRef<HTMLDivElement>(null);
  const isDraggingScrubber = useRef(false);

  // 1. Fetch current in-progress lap on mount / tab switch
  const refreshCurrentLap = useCallback(() => {
    fetch("/api/laps/current")
      .then((res) => (res.ok ? res.json() : null))
      .then((lap) => {
        if (lap && Array.isArray(lap.samples) && lap.samples.length > 0) {
          setInProgressLap(lap);
        } else {
          setInProgressLap(null);
        }
      })
      .catch(() => setInProgressLap(null));
  }, []);

  useEffect(() => {
    refreshCurrentLap();
    const interval = window.setInterval(refreshCurrentLap, 4000);
    return () => window.clearInterval(interval);
  }, [refreshCurrentLap]);

  // Combine live recorded laps + in-progress lap
  const currentSessionLaps: LapSummary[] = useMemo(() => {
    const list = [...liveLaps];
    if (inProgressLap && !list.some((l) => l.lap === inProgressLap.lap)) {
      list.push(inProgressLap);
    }
    return list;
  }, [liveLaps, inProgressLap]);

  // Load database sessions when in database mode
  useEffect(() => {
    if (sourceMode !== "database") return;
    let active = true;
    setLoadingDb(true);
    setDbError("");
    getStoredSessions()
      .then((data) => {
        if (!active) return;
        setDbSessions(data);
        if (data.length > 0 && !data.some((s) => s.sessionId === selectedDbSessionId)) {
          setSelectedDbSessionId(data[0].sessionId);
        }
      })
      .catch((err) => {
        if (active) setDbError(err instanceof Error ? err.message : "Failed to load sessions");
      })
      .finally(() => {
        if (active) setLoadingDb(false);
      });
    return () => {
      active = false;
    };
  }, [sourceMode]);

  // Load laps for selected database session
  useEffect(() => {
    if (sourceMode !== "database" || !selectedDbSessionId) return;
    let active = true;
    setLoadingDb(true);
    getSessionLaps(selectedDbSessionId)
      .then((data) => {
        if (!active) return;
        setDbLaps(data);
        if (data.length > 0 && !data.some((l) => l.lapId === selectedLapId)) {
          setSelectedLapId(data[0].lapId);
        }
      })
      .catch((err) => {
        if (active) setDbError(err instanceof Error ? err.message : "Failed to load laps");
      })
      .finally(() => {
        if (active) setLoadingDb(false);
      });
    return () => {
      active = false;
    };
  }, [sourceMode, selectedDbSessionId]);

  // Auto-select latest lap in current mode
  useEffect(() => {
    if (sourceMode === "current") {
      if (currentSessionLaps.length > 0) {
        if (!selectedLapId || !currentSessionLaps.some((l) => (l.id || `lap-${l.lap}`) === selectedLapId)) {
          const latest = currentSessionLaps[currentSessionLaps.length - 1];
          setSelectedLapId(latest.id || `lap-${latest.lap}`);
        }
      }
    }
  }, [sourceMode, currentSessionLaps, selectedLapId]);

  // Synchronize activeLap object based on selectedLapId
  useEffect(() => {
    if (!selectedLapId) return;

    if (sourceMode === "current") {
      const match = currentSessionLaps.find((l) => (l.id || `lap-${l.lap}`) === selectedLapId);
      if (match) {
        setActiveLap(match);
        // Default to beginning of lap or current scope
        setCurrentTimeMs(0);
        setIsPlaying(false);
      }
    } else {
      // Database lap: fetch samples trace if needed
      const match = dbLaps.find((l) => l.lapId === selectedLapId);
      if (!match) return;

      setLoadingTrace(true);
      fetch(`/api/laps/${encodeURIComponent(match.lapId)}/trace`)
        .then((res) => (res.ok ? res.json() : Promise.reject()))
        .then((samples: LapSample[]) => {
          setActiveLap({
            id: match.lapId,
            lap: match.lapNumber,
            lapTimeMs: match.lapTimeMs,
            sector1TimeMs: match.sector1TimeMs,
            sector2TimeMs: match.sector2TimeMs,
            sector3TimeMs: match.sector3TimeMs,
            trackId: match.trackId,
            trackLength: match.trackLength,
            invalid: match.invalid,
            partial: match.partial,
            qualityReasons: match.qualityReasons,
            samples,
          });
          setCurrentTimeMs(0);
          setIsPlaying(false);
        })
        .catch(() => {
          // If trace fetch fails, create stub
          setActiveLap({
            id: match.lapId,
            lap: match.lapNumber,
            lapTimeMs: match.lapTimeMs,
            sector1TimeMs: match.sector1TimeMs,
            sector2TimeMs: match.sector2TimeMs,
            sector3TimeMs: match.sector3TimeMs,
            trackId: match.trackId,
            trackLength: match.trackLength,
            samples: [],
          });
        })
        .finally(() => setLoadingTrace(false));
    }
  }, [sourceMode, selectedLapId, currentSessionLaps, dbLaps]);

  // Load track outline for active lap trackId if different from live session
  useEffect(() => {
    const trackId = activeLap?.trackId ?? currentSession?.trackId;
    if (trackId == null) {
      setReplayTrackOutline(currentTrackOutline ?? null);
      return;
    }
    if (currentSession?.trackId === trackId && currentTrackOutline) {
      setReplayTrackOutline(currentTrackOutline);
      return;
    }

    const fileName = TRACK_FILES[trackId];
    if (!fileName) return;

    const controller = new AbortController();
    fetch(`/track_data/${fileName}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => {
        if (controller.signal.aborted) return;
        setReplayTrackOutline({
          leftEdge: (data.left_edge ?? []).map(([x, z]: number[]) => ({ x, z })),
          rightEdge: (data.right_edge ?? []).map(([x, z]: number[]) => ({ x, z })),
          racingLine: (data.lines?.formula1?.racing_line ?? []).map(([x, z]: number[]) => ({ x, z })),
          orientation: Number(data.orientation ?? 0),
          sfLine: data.sf_line,
        });
      })
      .catch(() => {
        setReplayTrackOutline(currentTrackOutline ?? null);
      });

    return () => controller.abort();
  }, [activeLap?.trackId, currentSession?.trackId, currentTrackOutline]);

  // Sector boundaries calculation
  const totalDurationMs = useMemo(() => {
    if (!activeLap) return 0;
    if (activeLap.lapTimeMs && activeLap.lapTimeMs > 0) return activeLap.lapTimeMs;
    const samples = activeLap.samples;
    if (samples && samples.length > 0) {
      return samples[samples.length - 1].elapsedTimeMs ?? 0;
    }
    return 90_000;
  }, [activeLap]);

  const s1TimeMs = activeLap?.sector1TimeMs ?? Math.round(totalDurationMs * 0.32);
  const s2TimeMs = activeLap?.sector2TimeMs ?? Math.round(totalDurationMs * 0.38);
  const s1EndMs = s1TimeMs;
  const s2EndMs = s1TimeMs + s2TimeMs;

  const { scopeStartMs, scopeEndMs } = useMemo(() => {
    if (sectorScope === "s1") {
      return { scopeStartMs: 0, scopeEndMs: Math.max(100, s1EndMs) };
    }
    if (sectorScope === "s2") {
      return { scopeStartMs: s1EndMs, scopeEndMs: Math.max(s1EndMs + 100, s2EndMs) };
    }
    if (sectorScope === "s3") {
      return { scopeStartMs: s2EndMs, scopeEndMs: Math.max(s2EndMs + 100, totalDurationMs) };
    }
    return { scopeStartMs: 0, scopeEndMs: Math.max(100, totalDurationMs) };
  }, [sectorScope, s1EndMs, s2EndMs, totalDurationMs]);

  // Handle sector button click (snaps playhead to sector start)
  const handleSelectSector = (scope: SectorScope) => {
    setSectorScope(scope);
    if (scope === "s1") setCurrentTimeMs(0);
    else if (scope === "s2") setCurrentTimeMs(s1EndMs);
    else if (scope === "s3") setCurrentTimeMs(s2EndMs);
    else setCurrentTimeMs(0);
  };

  // High-performance animation loop for smooth 60fps playback
  useEffect(() => {
    if (!isPlaying) return;
    let animId: number;
    let lastTime = performance.now();

    const loop = (now: number) => {
      const dt = (now - lastTime) * playbackSpeed;
      lastTime = now;

      setCurrentTimeMs((prev) => {
        const next = prev + dt;
        if (next >= scopeEndMs) {
          if (isLooping) {
            return scopeStartMs;
          } else {
            setIsPlaying(false);
            return scopeEndMs;
          }
        }
        return next;
      });

      animId = requestAnimationFrame(loop);
    };

    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, [isPlaying, playbackSpeed, isLooping, scopeStartMs, scopeEndMs]);

  // Keyboard shortcut: Space to toggle play/pause
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (e.code === "Space") {
        e.preventDefault();
        setIsPlaying((v) => !v);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Nearest sample and index at currentTimeMs
  const sampleMatch = useMemo(() => {
    if (!activeLap?.samples || activeLap.samples.length === 0) return null;
    return findNearestSample(activeLap.samples, currentTimeMs);
  }, [activeLap, currentTimeMs]);

  const activeSample = sampleMatch?.sample ?? null;
  const activeIndex = sampleMatch?.index ?? -1;

  // Determine current active sector for UI
  const currentSectorNumber = useMemo(() => {
    if (currentTimeMs < s1EndMs) return 1;
    if (currentTimeMs < s2EndMs) return 2;
    return 3;
  }, [currentTimeMs, s1EndMs, s2EndMs]);

  // Rolling plot points for MiniChart
  const rollingPlotPoints = useMemo<PlotPoint[]>(() => {
    if (!activeLap?.samples || activeLap.samples.length === 0 || activeIndex < 0) {
      return [];
    }
    const WINDOW_POINTS = 180;
    const startIndex = Math.max(0, activeIndex - WINDOW_POINTS);
    const slice = activeLap.samples.slice(startIndex, activeIndex + 1);

    return slice.map((s, idx) => ({
      at: s.elapsedTimeMs ?? 0,
      gapBefore: Boolean(s.gapBefore || (idx === 0 && startIndex > 0)),
      distance: s.distance ?? 0,
      speed: Math.max(0, s.speed ?? 0),
      throttle: Math.max(0, Math.min(1, s.throttle ?? 0)),
      brake: Math.max(0, Math.min(1, s.brake ?? 0)),
    }));
  }, [activeLap, activeIndex]);

  // Car position & orientation on track map
  const trackLength = activeLap?.trackLength ?? currentSession?.trackLength ?? 7004;
  const carPosition = useMemo<Position | null>(() => {
    const line = replayTrackOutline?.racingLine;
    if (!line || line.length < 2) return null;

    const dist = activeSample?.distance ?? 0;
    const progress = Math.max(0, Math.min(1, ((dist % trackLength) + trackLength) % trackLength / trackLength));
    const floatIdx = progress * (line.length - 1);
    const idx = Math.floor(floatIdx);
    const nextIdx = Math.min(line.length - 1, idx + 1);
    const frac = floatIdx - idx;

    const p1 = line[idx];
    const p2 = line[nextIdx];

    return {
      x: p1.x + (p2.x - p1.x) * frac,
      z: p1.z + (p2.z - p1.z) * frac,
    };
  }, [replayTrackOutline, activeSample, trackLength]);

  const carHeading = useMemo<number>(() => {
    const line = replayTrackOutline?.racingLine;
    if (!line || line.length < 2) return 0;

    const dist = activeSample?.distance ?? 0;
    const progress = Math.max(0, Math.min(1, ((dist % trackLength) + trackLength) % trackLength / trackLength));
    const floatIdx = progress * (line.length - 1);
    const idx = Math.floor(floatIdx);
    const nextIdx = Math.min(line.length - 1, idx + 1);

    const dx = line[nextIdx].x - line[idx].x;
    const dz = line[nextIdx].z - line[idx].z;
    return Math.atan2(dx, dz);
  }, [replayTrackOutline, activeSample, trackLength]);

  const replayCars: Car[] = useMemo(() => {
    if (!carPosition) return [];
    return [
      {
        index: 0,
        worldX: carPosition.x,
        worldZ: carPosition.z,
        heading: carHeading,
        name: "YOU",
        driverNumber: livePlayer?.driverNumber ?? "1",
        position: 1,
        isPlayer: true,
      },
    ];
  }, [carPosition, carHeading, livePlayer]);

  // Car trail history on the map
  const mapHistory = useMemo<Position[]>(() => {
    if (!replayTrackOutline?.racingLine || !activeLap?.samples || activeIndex < 0) return [];
    const line = replayTrackOutline.racingLine;
    const TRAIL_LEN = 45;
    const start = Math.max(0, activeIndex - TRAIL_LEN);
    const historyPoints: Position[] = [];

    for (let i = start; i <= activeIndex; i += 2) {
      const s = activeLap.samples[i];
      if (!s || s.distance == null) continue;
      const prog = Math.max(0, Math.min(1, ((s.distance % trackLength) + trackLength) % trackLength / trackLength));
      const fIdx = prog * (line.length - 1);
      const idx = Math.floor(fIdx);
      const nextIdx = Math.min(line.length - 1, idx + 1);
      const frac = fIdx - idx;
      historyPoints.push({
        x: line[idx].x + (line[nextIdx].x - line[idx].x) * frac,
        z: line[idx].z + (line[nextIdx].z - line[idx].z) * frac,
      });
    }
    return historyPoints;
  }, [replayTrackOutline, activeLap, activeIndex, trackLength]);

  // Simulated player state for 3-panel dashboard telemetry
  const playerTelemetry: Player = useMemo(() => {
    const s = activeSample;
    return {
      speed: s?.speed ?? 0,
      throttle: s?.throttle ?? 0,
      brake: s?.brake ?? 0,
      steer: s?.steer ?? s?.steering ?? 0,
      gear: s?.gear ?? (s?.speed && s.speed > 5 ? 3 : 0),
      rpm: s?.rpm ?? s?.engineRPM ?? (s?.speed ? Math.min(12500, Math.round(5000 + (s.speed / 340) * 7000)) : 4200),
      drs: s?.drs ?? 0,
      drsAllowed: s?.drs ?? 0,
      lapDist: s?.distance ?? 0,
      lapTime: currentTimeMs,
      lapNum: activeLap?.lap ?? 1,
      sector: currentSectorNumber - 1,
      position: 1,
      invalid: activeLap?.invalid ?? false,
      suggestedGear: s?.suggestedGear ?? (s?.gear ? Math.min(8, Math.max(1, s.gear + 1)) : 4),
      gLat: s?.gLat ?? (s?.steer ? Number((s.steer * 2.8).toFixed(2)) : 0.0),
      gLong: s?.gLong ?? (s?.brake && s.brake > 0.1 ? Number((-s.brake * 4.2).toFixed(2)) : s?.throttle ? Number((s.throttle * 1.5).toFixed(2)) : 0.0),
      ersStore: 3_800_000,
      ersMode: 2,
      fuel: 48.5,
      fuelLaps: 22.4,
      tyreCompound: "Soft",
      tyreAge: activeLap?.lap ?? 1,
      tyres: livePlayer?.tyres,
      damage: livePlayer?.damage,
    };
  }, [activeSample, currentTimeMs, activeLap, currentSectorNumber, livePlayer]);

  // Scrubber mouse drag / seek logic
  const handleSeekFromEvent = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!scrubberRef.current || totalDurationMs <= 0) return;
    const rect = scrubberRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetMs = ratio * totalDurationMs;
    setCurrentTimeMs(targetMs);
  };

  const handleMouseDownScrubber = (e: React.MouseEvent<HTMLDivElement>) => {
    isDraggingScrubber.current = true;
    handleSeekFromEvent(e);
  };

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDraggingScrubber.current || !scrubberRef.current || totalDurationMs <= 0) return;
      const rect = scrubberRef.current.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      setCurrentTimeMs(ratio * totalDurationMs);
    };

    const onMouseUp = () => {
      isDraggingScrubber.current = false;
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [totalDurationMs]);

  // Sector timing segments display
  const sectorSegments = useMemo(() => {
    const s1Complete = currentTimeMs >= s1EndMs;
    const s2Complete = currentTimeMs >= s2EndMs;

    return [
      {
        sector: 1,
        state: s1Complete ? "complete" : currentSectorNumber === 1 ? "current" : "upcoming",
        timeMs: s1Complete ? s1TimeMs : currentSectorNumber === 1 ? currentTimeMs : null,
        grade: "green",
      },
      {
        sector: 2,
        state: s2Complete ? "complete" : currentSectorNumber === 2 ? "current" : "upcoming",
        timeMs: s2Complete ? s2TimeMs : currentSectorNumber === 2 ? currentTimeMs - s1EndMs : null,
        grade: "yellow",
      },
      {
        sector: 3,
        state: currentTimeMs >= totalDurationMs ? "complete" : currentSectorNumber === 3 ? "current" : "upcoming",
        timeMs: currentTimeMs >= totalDurationMs ? totalDurationMs - s2EndMs : currentSectorNumber === 3 ? currentTimeMs - s2EndMs : null,
        grade: "purple",
      },
    ];
  }, [currentTimeMs, s1EndMs, s2EndMs, s1TimeMs, s2TimeMs, totalDurationMs, currentSectorNumber]);

  const activeDistance = activeSample?.distance ?? 0;
  const circuitName =
    TRACK_NAMES[activeLap?.trackId ?? currentSession?.trackId ?? -1] ||
    currentSession?.trackName ||
    "Current Circuit";

  return (
    <div className="replay-container">
      {/* =========================================================================
          REPLAY CONTROL TOOLBAR
          ========================================================================= */}
      <section className="replay-toolbar" aria-label="Race Replay Controls">
        <div className="replay-controls-row">
          {/* Source & Lap Selector */}
          <div className="replay-group">
            <span className="replay-group-label">SOURCE</span>
            <div className="replay-pill-toggle">
              <button
                className={`replay-btn ${sourceMode === "current" ? "active" : ""}`}
                onClick={() => setSourceMode("current")}
                title="Current live/recent driving session"
              >
                LIVE SESSION ({currentSessionLaps.length})
              </button>
              <button
                className={`replay-btn ${sourceMode === "database" ? "active" : ""}`}
                onClick={() => setSourceMode("database")}
                title="Persisted database sessions"
              >
                SAVED RACES ({dbSessions.length})
              </button>
            </div>

            {sourceMode === "database" && (
              <select
                className="replay-select"
                value={selectedDbSessionId}
                onChange={(e) => setSelectedDbSessionId(e.target.value)}
                disabled={loadingDb || dbSessions.length === 0}
              >
                {dbSessions.map((s) => (
                  <option key={s.sessionId} value={s.sessionId}>
                    {TRACK_NAMES[s.trackId ?? -1] || `Track ${s.trackId ?? "—"}`} · {s.startedAt ? new Date(s.startedAt).toLocaleTimeString() : s.sessionId.slice(-6)} · {s.lapCount} laps
                  </option>
                ))}
              </select>
            )}

            <label className="replay-select-wrap">
              <span className="replay-mini-label">LAP</span>
              <select
                className="replay-select lap-select"
                value={selectedLapId}
                onChange={(e) => setSelectedLapId(e.target.value)}
                disabled={loadingDb || loadingTrace}
              >
                {sourceMode === "current" ? (
                  currentSessionLaps.length === 0 ? (
                    <option value="">No recorded laps yet</option>
                  ) : (
                    currentSessionLaps.map((lap) => {
                      const id = lap.id || `lap-${lap.lap}`;
                      return (
                        <option key={id} value={id}>
                          Lap {lap.lap} · {formatTime(lap.lapTimeMs)}
                          {lap.inProgress ? " (IN PROGRESS)" : lap.invalid ? " (INVALID)" : ""}
                        </option>
                      );
                    })
                  )
                ) : dbLaps.length === 0 ? (
                  <option value="">No laps in session</option>
                ) : (
                  dbLaps.map((lap) => (
                    <option key={lap.lapId} value={lap.lapId}>
                      Lap {lap.lapNumber} · {formatTime(lap.lapTimeMs)}
                      {lap.invalid ? " (INVALID)" : ""}
                    </option>
                  ))
                )}
              </select>
            </label>
          </div>

          {/* Sector-wise & Lap-wise Scope Selector */}
          <div className="replay-group">
            <span className="replay-group-label">SECTOR REPLAY</span>
            <div className="replay-sector-pills" role="radiogroup" aria-label="Replay sector focus">
              <button
                className={`sector-pill ${sectorScope === "full" ? "active" : ""}`}
                onClick={() => handleSelectSector("full")}
              >
                FULL LAP
              </button>
              <button
                className={`sector-pill s1-pill ${sectorScope === "s1" ? "active" : ""}`}
                onClick={() => handleSelectSector("s1")}
              >
                SECTOR 1
              </button>
              <button
                className={`sector-pill s2-pill ${sectorScope === "s2" ? "active" : ""}`}
                onClick={() => handleSelectSector("s2")}
              >
                SECTOR 2
              </button>
              <button
                className={`sector-pill s3-pill ${sectorScope === "s3" ? "active" : ""}`}
                onClick={() => handleSelectSector("s3")}
              >
                SECTOR 3
              </button>
            </div>
          </div>

          {/* VCR Playback Controls */}
          <div className="replay-group replay-transport">
            <button
              className="vcr-btn"
              onClick={() => setCurrentTimeMs(scopeStartMs)}
              title="Jump to Start (⏮)"
            >
              ⏮
            </button>
            <button
              className="vcr-btn"
              onClick={() => setCurrentTimeMs((t) => Math.max(scopeStartMs, t - 1000))}
              title="Step -1s (◀)"
            >
              ◀ 1s
            </button>
            <button
              className={`vcr-btn play-btn ${isPlaying ? "is-playing" : ""}`}
              onClick={() => setIsPlaying((p) => !p)}
              title={isPlaying ? "Pause (Space)" : "Play (Space)"}
            >
              {isPlaying ? "❚❚ PAUSE" : "▶ PLAY"}
            </button>
            <button
              className="vcr-btn"
              onClick={() => setCurrentTimeMs((t) => Math.min(scopeEndMs, t + 1000))}
              title="Step +1s (▶)"
            >
              1s ▶
            </button>
            <button
              className="vcr-btn"
              onClick={() => setCurrentTimeMs(scopeEndMs)}
              title="Jump to End (⏭)"
            >
              ⏭
            </button>
            <button
              className={`vcr-btn loop-btn ${isLooping ? "active" : ""}`}
              onClick={() => setIsLooping((l) => !l)}
              title="Toggle Continuous Loop"
            >
              🔁 LOOP {isLooping ? "ON" : "OFF"}
            </button>
          </div>

          {/* Speed Multiplier Controls */}
          <div className="replay-group replay-speeds">
            <span className="replay-group-label">SPEED</span>
            <div className="speed-pills">
              {[0.25, 0.5, 1.0, 2.0].map((speed) => (
                <button
                  key={speed}
                  className={`speed-pill ${playbackSpeed === speed ? "active" : ""}`}
                  onClick={() => setPlaybackSpeed(speed)}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Multi-Sector Interactive Timeline Scrubber */}
        <div className="replay-timeline-block">
          <div className="timeline-info">
            <div className="timeline-timer">
              <span className="live-dot" />
              <strong>{formatTime(currentTimeMs)}</strong>
              <small> / {formatTime(totalDurationMs)}</small>
              <span className="timeline-scope-badge">
                {sectorScope === "full" ? "FULL LAP" : `SECTOR ${sectorScope.slice(1).toUpperCase()}`}
              </span>
            </div>
            <div className="timeline-distance">
              <span>DISTANCE</span>
              <strong>{activeDistance.toFixed(0)} m</strong>
              <small> / {trackLength.toFixed(0)} m</small>
            </div>
          </div>

          <div
            className="replay-scrubber-track"
            ref={scrubberRef}
            onMouseDown={handleMouseDownScrubber}
          >
            {/* Color-coded Sector Bands */}
            {totalDurationMs > 0 && (
              <>
                <div
                  className={`scrubber-sector-band s1-band ${sectorScope === "s1" ? "band-focused" : ""}`}
                  style={{ width: `${Math.min(100, (s1EndMs / totalDurationMs) * 100)}%` }}
                >
                  <span>S1</span>
                </div>
                <div
                  className={`scrubber-sector-band s2-band ${sectorScope === "s2" ? "band-focused" : ""}`}
                  style={{
                    left: `${(s1EndMs / totalDurationMs) * 100}%`,
                    width: `${Math.min(100 - (s1EndMs / totalDurationMs) * 100, ((s2EndMs - s1EndMs) / totalDurationMs) * 100)}%`,
                  }}
                >
                  <span>S2</span>
                </div>
                <div
                  className={`scrubber-sector-band s3-band ${sectorScope === "s3" ? "band-focused" : ""}`}
                  style={{
                    left: `${(s2EndMs / totalDurationMs) * 100}%`,
                    width: `${Math.max(0, 100 - (s2EndMs / totalDurationMs) * 100)}%`,
                  }}
                >
                  <span>S3</span>
                </div>

                {/* Delimiter Lines */}
                <div
                  className="scrubber-delimiter"
                  style={{ left: `${(s1EndMs / totalDurationMs) * 100}%` }}
                />
                <div
                  className="scrubber-delimiter"
                  style={{ left: `${(s2EndMs / totalDurationMs) * 100}%` }}
                />

                {/* Scrubber Progress Fill & Playhead Cursor */}
                <div
                  className="scrubber-progress-fill"
                  style={{ width: `${Math.min(100, (currentTimeMs / totalDurationMs) * 100)}%` }}
                />
                <div
                  className="scrubber-playhead"
                  style={{ left: `${Math.min(100, (currentTimeMs / totalDurationMs) * 100)}%` }}
                >
                  <div className="playhead-indicator" />
                </div>
              </>
            )}
          </div>
        </div>
      </section>

      {/* =========================================================================
          SYNCHRONIZED 3-PANEL DASHBOARD (IDENTICAL TO LIVE TELEMETRY)
          ========================================================================= */}
      <section className="dashboard-grid">
        {/* PANEL 1: TRACK POSITION & RACE TIMING */}
        <article className="panel panel-map">
          <PanelHeading
            eyebrow="01 / TRACK POSITION"
            title={circuitName}
            trailing={
              <span className="panel-chip replay-chip">
                {isPlaying ? "▶ PLAYING" : "⏸ PAUSED"} · {playbackSpeed}X
              </span>
            }
          />
          <div className="map-meta">
            <span>
              {displayNumber(trackLength)} <small>M TRACK</small>
            </span>
            <span>
              {activeDistance <= 0 ? "0 m" : `${activeDistance.toFixed(0)} m`} <small>LAP DISTANCE</small>
            </span>
            <span>
              {displayNumber(playerTelemetry?.speed)} <small>KM/H</small>
            </span>
          </div>

          <TrackMap
            cars={replayCars}
            history={mapHistory}
            player={playerTelemetry}
            trackOutline={replayTrackOutline}
          />

          <div className="race-timing">
            <div className="timing-main">
              <div className="timer-block">
                <span className="eyebrow">CURRENT LAP · REPLAY</span>
                <strong>{formatTime(currentTimeMs)}</strong>
                <span className="timer-status">
                  {activeLap?.invalid ? "INVALID LAP" : `IN SECTOR ${currentSectorNumber}`}
                </span>
              </div>
              <div className="position-large">
                <span>POSITION</span>
                <strong>P1</strong>
              </div>
            </div>

            <div className="sector-track" aria-label="Three sector timing progress">
              {sectorSegments.map((timing) => (
                <div
                  key={timing.sector}
                  className={`sector-segment grade-${timing.grade} ${timing.state === "current" ? "sector-current" : ""}`}
                >
                  <span>
                    S{timing.sector}{" "}
                    <small>
                      {timing.state === "current" ? "RUNNING" : timing.state === "complete" ? "COMPLETE" : "NEXT"}
                    </small>
                  </span>
                  <strong>{timing.timeMs === null ? "—" : formatTime(timing.timeMs)}</strong>
                </div>
              ))}
            </div>

            <div className="timing-legend">
              <span className="grade-purple">● Sector 3</span>
              <span className="grade-yellow">● Sector 2</span>
              <span className="grade-green">● Sector 1</span>
              <span>Replay Scrubber Active</span>
            </div>

            <div className="race-context">
              LAP {displayNumber(activeLap?.lap ?? 1)} / {displayNumber(currentSession?.totalLaps ?? 57)} · TRACK {displayNumber(currentSession?.trackTemp ?? 32)}°C · AIR {displayNumber(currentSession?.airTemp ?? 24)}°C
            </div>
          </div>
        </article>

        {/* PANEL 2: TELEMETRY TRACES */}
        <article className="panel panel-charts">
          <PanelHeading
            eyebrow="03 / DRIVER INPUT"
            title="Telemetry traces"
            trailing={
              <span className="window-label">
                REPLAY · {activeLap?.samples?.length ?? 0} SAMPLES
              </span>
            }
          />
          <div className="chart-legend">
            <span>
              <i className="legend-speed" />
              SPEED <b>{displayNumber(playerTelemetry?.speed)} KM/H</b>
            </span>
            <span>
              <i className="legend-throttle" />
              THROTTLE <b>{percent(playerTelemetry?.throttle)}</b>
            </span>
            <span>
              <i className="legend-brake" />
              BRAKE <b>{percent(playerTelemetry?.brake)}</b>
            </span>
          </div>

          <div className="chart-block">
            <div className="chart-title">
              <strong>SPEED</strong>
              <span>KM/H</span>
            </div>
            <MiniChart points={rollingPlotPoints} mode="speed" />
          </div>

          <div className="chart-block chart-block-pedals">
            <div className="chart-title">
              <strong>PEDALS</strong>
              <span>%</span>
            </div>
            <MiniChart points={rollingPlotPoints} mode="pedals" />
          </div>

          <div className="panel-foot">
            <span>DISTANCE {activeDistance <= 0 ? "0 M" : `${activeDistance.toFixed(0)} M`}</span>
            <span>REPLAY TRACE · {sectorScope === "full" ? "FULL LAP" : `FOCUSED ON SECTOR ${sectorScope.slice(1).toUpperCase()}`}</span>
          </div>
        </article>

        {/* PANEL 3: CAR TELEMETRY VALUES & HEALTH */}
        <article className="panel panel-values">
          <PanelHeading
            eyebrow="04 / CAR TELEMETRY"
            title="Player values"
            trailing={<span className="gear-readout">{displayNumber(playerTelemetry?.gear)}</span>}
          />
          <div className="values-grid">
            <Stat label="SPEED" value={displayNumber(playerTelemetry?.speed)} unit="KM/H" />
            <Stat label="ENGINE RPM" value={isNumber(playerTelemetry?.rpm) ? playerTelemetry.rpm.toLocaleString() : "—"} />
            <Stat label="THROTTLE" value={percent(playerTelemetry?.throttle)} />
            <Stat label="BRAKE" value={percent(playerTelemetry?.brake)} />
            <Stat label="STEERING" value={displayNumber(playerTelemetry?.steer, 2)} />
            <Stat label="SUGGESTED GEAR" value={isNumber(playerTelemetry?.suggestedGear) && playerTelemetry.suggestedGear > 0 ? String(playerTelemetry.suggestedGear) : "—"} />
            <Stat label="LATERAL G" value={displayNumber(playerTelemetry?.gLat, 2)} />
            <Stat label="LONGITUDINAL G" value={displayNumber(playerTelemetry?.gLong, 2)} />
            <Stat label="DRS" value={playerTelemetry?.drs ? "OPEN" : "CLOSED"} />
            <Stat label="DRS AVAILABLE" value={playerTelemetry?.drsAllowed ? "YES" : "NO"} />
            <Stat label="ERS STORE" value={displayNumber(isNumber(playerTelemetry?.ersStore) ? playerTelemetry.ersStore / 1_000_000 : null, 2)} unit="MJ" />
            <Stat label="ERS MODE" value={displayNumber(playerTelemetry?.ersMode)} />
            <Stat label="FUEL" value={displayNumber(playerTelemetry?.fuel, 1)} unit="KG" />
            <Stat label="FUEL LAPS" value={displayNumber(playerTelemetry?.fuelLaps, 1)} />
            <Stat label="TYRE COMPOUND" value={String(playerTelemetry?.tyreCompound ?? "Soft")} />
            <Stat label="TYRE AGE" value={displayNumber(playerTelemetry?.tyreAge)} unit="LAPS" />
          </div>

          <div className="values-footer">
            <div className="driving-state">
              <span className="state-dot" />
              <span>
                {isNumber(playerTelemetry?.brake) && isNumber(playerTelemetry?.throttle)
                  ? (playerTelemetry.brake ?? 0) >= 0.02
                    ? "BRAKING"
                    : (playerTelemetry.throttle ?? 0) >= 0.98
                    ? "FULL THROTTLE"
                    : (playerTelemetry.throttle ?? 0) > 0.02
                    ? "ACCELERATING"
                    : "COASTING"
                  : "AWAITING TELEMETRY"}
              </span>
            </div>
          </div>

          <div className="health-heading">
            <h3>Car health</h3>
            <span>DAMAGE OVERVIEW</span>
          </div>
          <CarStatusPanel
            player={playerTelemetry}
            online={true}
            retained={false}
            paused={false}
          />
        </article>
      </section>

      {dbError && <p className="persistent-error" role="alert">{dbError}</p>}
    </div>
  );
}
