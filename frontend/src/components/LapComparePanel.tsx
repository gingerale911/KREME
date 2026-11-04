
import { useEffect, useState } from "react";
import {
  getStoredSessions,
  getSessionLaps,
  getLapComparison,
  type StoredSession,
  type StoredLap,
  type LapComparison,
} from "../api/lapComparison";

function formatLapTime(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms) || ms <= 0) return "—";

  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(3).padStart(6, "0");

  return minutes > 0 ? `${minutes}:${seconds}` : seconds;
}

function formatDelta(ms: number): string {
  return `${ms > 0 ? "+" : ""}${ms.toFixed(1)} ms`;
}

type ChartMetric = "speed" | "throttle" | "brake" | "delta";

interface ChartPoint {
  distance: number;
  reference: number | null;
  comparison: number | null;
}

function ComparisonChart({
  title,
  unit,
  points,
  metric,
}: {
  title: string;
  unit: string;
  points: ChartPoint[];
  metric: ChartMetric;
}) {
  const width = 760;
  const height = 190;
  const pad = { top: 18, right: 18, bottom: 30, left: 54 };
  const validValues = points.flatMap((point) =>
    [point.reference, point.comparison].filter(
      (value): value is number => value !== null && Number.isFinite(value),
    ),
  );

  if (validValues.length === 0) {
    return (
      <div className="comparison-chart-card">
        <div className="comparison-chart-heading">{title}</div>
        <div className="comparison-chart-empty">NO ALIGNED TELEMETRY AVAILABLE</div>
      </div>
    );
  }

  let minY = 0;
  let maxY = metric === "throttle" || metric === "brake" ? 1 : Math.max(...validValues);
  if (metric === "delta") {
    const extent = Math.max(10, ...validValues.map((value) => Math.abs(value)));
    minY = -extent;
    maxY = extent;
  } else if (metric === "speed") {
    maxY = Math.max(50, Math.ceil(maxY / 50) * 50);
  } else {
    maxY = 1;
  }

  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const x = (distance: number) =>
    pad.left + (distance / Math.max(points[points.length - 1]?.distance ?? 1, 1)) * plotWidth;
  const y = (value: number) =>
    pad.top + ((maxY - value) / (maxY - minY)) * plotHeight;

  const makePath = (key: "reference" | "comparison") => {
    let drawing = false;
    return points
      .map((point) => {
        const value = point[key];
        if (value === null || !Number.isFinite(value)) {
          drawing = false;
          return "";
        }
        const command = drawing ? "L" : "M";
        drawing = true;
        return `${command}${x(point.distance).toFixed(1)},${y(value).toFixed(1)}`;
      })
      .filter(Boolean)
      .join(" ");
  };

  const referencePath = makePath("reference");
  const comparisonPath = makePath("comparison");
  const tickValues = metric === "throttle" || metric === "brake"
    ? [0, 0.25, 0.5, 0.75, 1]
    : metric === "delta"
      ? [minY, minY / 2, 0, maxY / 2, maxY]
      : [0, maxY / 2, maxY];

  const formatTick = (value: number) =>
    metric === "throttle" || metric === "brake"
      ? `${Math.round(value * 100)}%`
      : `${Math.round(value)}${unit}`;

  return (
    <div className="comparison-chart-card">
      <div className="comparison-chart-heading">
        <strong>{title}</strong>
        <span>{metric === "delta" ? "COMPARISON − REFERENCE" : "BY DISTANCE"}</span>
      </div>
      <svg className="comparison-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${title} comparison chart`}>
        {tickValues.map((tick) => (
          <g key={tick}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(tick)}
              y2={y(tick)}
              className={metric === "delta" && tick === 0 ? "comparison-zero-line" : "chart-grid"}
            />
            <text x={pad.left - 9} y={y(tick) + 4} textAnchor="end" className="chart-axis-label">
              {formatTick(tick)}
            </text>
          </g>
        ))}
        <line x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} className="chart-grid" />
        {referencePath && <path d={referencePath} className="comparison-line-reference" />}
        {comparisonPath && <path d={comparisonPath} className={metric === "delta" ? "comparison-line-delta" : "comparison-line-current"} />}
        <text x={pad.left} y={height - 7} className="chart-axis-label">START</text>
        <text x={width - pad.right} y={height - 7} textAnchor="end" className="chart-axis-label">
          {points[points.length - 1]?.distance.toFixed(0) ?? 0} m
        </text>
      </svg>
      <div className="comparison-chart-legend">
        {metric !== "delta" && <span><i className="legend-reference" /> Reference lap</span>}
        <span><i className={metric === "delta" ? "legend-delta" : "legend-comparison"} /> {metric === "delta" ? "Time delta" : "Comparison lap"}</span>
      </div>
    </div>
  );
}

function ComparisonGraphs({ result }: { result: LapComparison }) {
  const points: ChartPoint[] = result.data.map((point) => ({
    distance: point.distance,
    reference: null,
    comparison: null,
  }));

  const speedPoints = points.map((point, index) => ({
    ...point,
    reference: result.data[index].referenceSpeed,
    comparison: result.data[index].comparisonSpeed,
  }));
  const throttlePoints = points.map((point, index) => ({
    ...point,
    reference: result.data[index].referenceThrottle,
    comparison: result.data[index].comparisonThrottle,
  }));
  const brakePoints = points.map((point, index) => ({
    ...point,
    reference: result.data[index].referenceBrake,
    comparison: result.data[index].comparisonBrake,
  }));
  const deltaPoints = points.map((point, index) => ({
    ...point,
    reference: null,
    comparison: result.data[index].deltaMs,
  }));

  return (
    <div className="comparison-graphs">
      <ComparisonChart title="SPEED" unit=" km/h" points={speedPoints} metric="speed" />
      <ComparisonChart title="THROTTLE" unit="%" points={throttlePoints} metric="throttle" />
      <ComparisonChart title="BRAKE" unit="%" points={brakePoints} metric="brake" />
      <ComparisonChart title="TIME DELTA" unit=" ms" points={deltaPoints} metric="delta" />
    </div>
  );
}


type SectorLap = StoredLap & {
  sector1TimeMs?: number | null;
  sector2TimeMs?: number | null;
  sector3TimeMs?: number | null;
};

function SectorAnalysis({
  referenceLap,
  comparisonLap,
}: {
  referenceLap: StoredLap;
  comparisonLap: StoredLap;
}) {
  const reference = referenceLap as SectorLap;
  const comparison = comparisonLap as SectorLap;
  const sectors = [
    { name: "SECTOR 1", reference: reference.sector1TimeMs, comparison: comparison.sector1TimeMs },
    { name: "SECTOR 2", reference: reference.sector2TimeMs, comparison: comparison.sector2TimeMs },
    { name: "SECTOR 3", reference: reference.sector3TimeMs, comparison: comparison.sector3TimeMs },
  ].map((sector) => ({
    ...sector,
    delta: typeof sector.reference === "number" && typeof sector.comparison === "number"
      ? sector.comparison - sector.reference
      : null,
  }));

  const available = sectors.filter((sector) => sector.delta !== null);
  if (available.length === 0) return null;

  const biggestGain = [...available].sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0))[0];
  const biggestLoss = [...available].sort((a, b) => (b.delta ?? 0) - (a.delta ?? 0))[0];

  return (
    <section className="sector-analysis">
      <div className="sector-analysis-heading">
        <div>
          <div className="eyebrow">SECTOR BREAKDOWN</div>
          <h3>Where the time was won</h3>
        </div>
        <span className="panel-chip">COMPARISON − REFERENCE</span>
      </div>

      <div className="sector-table">
        <div className="sector-table-row sector-table-header">
          <span>SECTOR</span><span>REFERENCE</span><span>COMPARISON</span><span>DELTA</span>
        </div>
        {sectors.map((sector) => (
          <div className="sector-table-row" key={sector.name}>
            <strong>{sector.name}</strong>
            <span>{typeof sector.reference === "number" ? formatLapTime(sector.reference ?? null) : "—"}</span>
            <span>{typeof sector.comparison === "number" ? formatLapTime(sector.comparison ?? null) : "—"}</span>
            <b className={sector.delta === null ? "" : sector.delta < 0 ? "text-green" : sector.delta > 0 ? "text-amber" : ""}>
              {sector.delta === null ? "—" : formatDelta(sector.delta)}
            </b>
          </div>
        ))}
      </div>

      <div className="sector-insights">
        <div>
          <span>BIGGEST TIME GAIN</span>
          <strong>{biggestGain.delta !== null && biggestGain.delta < 0 ? biggestGain.name : "—"}</strong>
          <b className="text-green">{biggestGain.delta !== null && biggestGain.delta < 0 ? formatDelta(biggestGain.delta) : "No gain"}</b>
        </div>
        <div>
          <span>BIGGEST TIME LOSS</span>
          <strong>{biggestLoss.delta !== null && biggestLoss.delta > 0 ? biggestLoss.name : "—"}</strong>
          <b className="text-amber">{biggestLoss.delta !== null && biggestLoss.delta > 0 ? formatDelta(biggestLoss.delta) : "No loss"}</b>
        </div>
      </div>
      <p className="sector-analysis-note">Negative delta means the comparison lap was faster in that sector. Positive delta means it was slower.</p>
    </section>
  );
}

export default function LapComparePanel() {
  const [sessions, setSessions] = useState<StoredSession[]>([]);
  const [laps, setLaps] = useState<StoredLap[]>([]);

  const [sessionId, setSessionId] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [comparisonId, setComparisonId] = useState("");

  const [result, setResult] = useState<LapComparison | null>(null);

  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingLaps, setLoadingLaps] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadSessions() {
      setLoadingSessions(true);
      setError("");

      try {
        const data = await getStoredSessions();

        if (!active) return;

        setSessions(data);

        if (data.length > 0) {
          setSessionId(data[0].sessionId);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load sessions");
        }
      } finally {
        if (active) setLoadingSessions(false);
      }
    }

    loadSessions();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setLaps([]);
      setReferenceId("");
      setComparisonId("");
      setResult(null);
      return;
    }

    let active = true;

    async function loadLaps() {
      setLoadingLaps(true);
      setError("");
      setResult(null);
      setReferenceId("");
      setComparisonId("");

      try {
        const data = await getSessionLaps(sessionId);

        if (!active) return;

        setLaps(data);

        if (data.length > 0) {
          setReferenceId(data[0].lapId);

          if (data.length > 1) {
            setComparisonId(data[1].lapId);
          }
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load laps");
        }
      } finally {
        if (active) setLoadingLaps(false);
      }
    }

    loadLaps();

    return () => {
      active = false;
    };
  }, [sessionId]);

  async function handleCompare() {
    if (!referenceId || !comparisonId) return;

    if (referenceId === comparisonId) {
      setError("Choose two different laps.");
      return;
    }

    setComparing(true);
    setError("");
    setResult(null);

    try {
      const data = await getLapComparison(referenceId, comparisonId);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lap comparison failed");
    } finally {
      setComparing(false);
    }
  }

  const referenceLap = laps.find((lap) => lap.lapId === referenceId);
  const comparisonLap = laps.find((lap) => lap.lapId === comparisonId);

  return (
    <section className="lap-tab-panel">
      <div className="lap-layout lap-persistent-layout">
        <article className="panel lap-main-panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">PERSISTENT LAP ANALYSIS</div>
              <h2>Lap comparison</h2>
            </div>
            <span className="panel-chip">{laps.length} STORED LAPS</span>
          </div>

          <div className="persistent-selectors">
            <label className="persistent-field">
              <span>SESSION</span>
              <select
                value={sessionId}
                disabled={loadingSessions || sessions.length === 0}
                onChange={(event) => setSessionId(event.target.value)}
              >
                {sessions.length === 0 && <option value="">No sessions available</option>}
                {sessions.map((session) => (
                  <option key={session.sessionId} value={session.sessionId}>
                    Track {session.trackId ?? "Unknown"} · {session.lapCount} laps
                  </option>
                ))}
              </select>
            </label>

            <label className="persistent-field">
              <span>REFERENCE LAP</span>
              <select
                value={referenceId}
                disabled={loadingLaps || laps.length === 0}
                onChange={(event) => {
                  setReferenceId(event.target.value);
                  setResult(null);
                }}
              >
                {laps.map((lap) => (
                  <option key={lap.lapId} value={lap.lapId}>
                    Lap {lap.lapNumber} · {formatLapTime(lap.lapTimeMs)}
                  </option>
                ))}
              </select>
            </label>

            <label className="persistent-field">
              <span>COMPARISON LAP</span>
              <select
                value={comparisonId}
                disabled={loadingLaps || laps.length < 2}
                onChange={(event) => {
                  setComparisonId(event.target.value);
                  setResult(null);
                }}
              >
                {laps.map((lap) => (
                  <option key={lap.lapId} value={lap.lapId}>
                    Lap {lap.lapNumber} · {formatLapTime(lap.lapTimeMs)}
                  </option>
                ))}
              </select>
            </label>

            <button
              className="persistent-compare-button"
              disabled={
                comparing ||
                loadingLaps ||
                !referenceId ||
                !comparisonId ||
                referenceId === comparisonId
              }
              onClick={handleCompare}
            >
              {comparing ? "COMPARING..." : "COMPARE LAPS"}
            </button>
          </div>

          {loadingSessions && (
            <div className="persistent-message">LOADING STORED SESSIONS...</div>
          )}

          {loadingLaps && (
            <div className="persistent-message">LOADING SESSION LAPS...</div>
          )}

          {!loadingSessions && sessions.length === 0 && !error && (
            <div className="persistent-empty">
              <strong>NO PERSISTED SESSIONS</strong>
              <span>Complete and record laps in F1 25 to populate lap history.</span>
            </div>
          )}

          {!loadingLaps && sessions.length > 0 && laps.length === 0 && !error && (
            <div className="persistent-empty">
              <strong>NO COMPLETED LAPS</strong>
              <span>This session does not have any stored laps yet.</span>
            </div>
          )}

          {laps.length === 1 && (
            <div className="persistent-message">
              At least two stored laps are required for comparison.
            </div>
          )}

          {error && (
            <div className="persistent-error" role="alert">
              {error}
            </div>
          )}

          {referenceLap && comparisonLap && (
            <div className="persistent-lap-cards">
              <div className="lap-card lap-card-current">
                <span className="lap-card-label">REFERENCE</span>
                <strong>Lap {referenceLap.lapNumber}</strong>
                <div className="lap-card-row">
                  <span>TIME</span>
                  <b>{formatLapTime(referenceLap.lapTimeMs)}</b>
                </div>
                <div className="lap-card-row">
                  <span>AVG SPEED</span>
                  <b>{referenceLap.avgSpeedKph?.toFixed(1) ?? "—"} km/h</b>
                </div>
                <div className="lap-card-row">
                  <span>STATUS</span>
                  <b>{referenceLap.invalid ? "INVALID" : referenceLap.partial ? "PARTIAL" : "VALID"}</b>
                </div>
              </div>

              <div className="lap-card">
                <span className="lap-card-label">COMPARISON</span>
                <strong>Lap {comparisonLap.lapNumber}</strong>
                <div className="lap-card-row">
                  <span>TIME</span>
                  <b>{formatLapTime(comparisonLap.lapTimeMs)}</b>
                </div>
                <div className="lap-card-row">
                  <span>AVG SPEED</span>
                  <b>{comparisonLap.avgSpeedKph?.toFixed(1) ?? "—"} km/h</b>
                </div>
                <div className="lap-card-row">
                  <span>STATUS</span>
                  <b>{comparisonLap.invalid ? "INVALID" : comparisonLap.partial ? "PARTIAL" : "VALID"}</b>
                </div>
              </div>
            </div>
          )}

          {result && (
            <div className="persistent-result">
              <div>
                <span>TOTAL TIME DELTA</span>
                <strong className={result.totalTimeDeltaMs <= 0 ? "text-green" : "text-amber"}>
                  {formatDelta(result.totalTimeDeltaMs)}
                </strong>
              </div>
              <div>
                <span>COMMON TRACK</span>
                <strong>{result.commonTrackLength.toFixed(0)} m</strong>
              </div>
              <div>
                <span>VALID DELTA POINTS</span>
                <strong>{result.validDeltaPoints} / {result.gridPoints}</strong>
              </div>
            </div>
          )}

          {result && referenceLap && comparisonLap && (
            <SectorAnalysis referenceLap={referenceLap} comparisonLap={comparisonLap} />
          )}

          <div className="session-store-note">
            DATA SOURCE · DUCKDB PERSISTENT LAP STORAGE
          </div>
        </article>

        <article className="panel lap-graph-panel persistent-preview-panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">COMPARISON ENGINE</div>
              <h2>Telemetry alignment</h2>
            </div>
            <span className="panel-chip">DISTANCE ALIGNED</span>
          </div>

          {result ? (
            <>
              <div className="persistent-preview-summary">
                <div className="persistent-preview-stat">
                  <span>REFERENCE LAP TIME</span>
                  <strong>{formatLapTime(result.referenceLapTimeMs)}</strong>
                </div>
                <div className="persistent-preview-stat">
                  <span>COMPARISON LAP TIME</span>
                  <strong>{formatLapTime(result.comparisonLapTimeMs)}</strong>
                </div>
                <div className="persistent-preview-stat">
                  <span>SHARED DISTANCE GRID</span>
                  <strong>{result.gridPoints} POINTS</strong>
                </div>
                <div className="persistent-preview-stat">
                  <span>TELEMETRY SAMPLES</span>
                  <strong>{result.validDeltaPoints} ALIGNED</strong>
                </div>
              </div>
              <ComparisonGraphs result={result} />
            </>
          ) : (
            <div className="persistent-empty persistent-graph-empty">
              <strong>AWAITING LAP SELECTION</strong>
              <span>Select two stored laps and run the comparison to load distance-aligned telemetry.</span>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}
