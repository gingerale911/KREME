
import { useEffect, useRef, useState } from "react";
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


const trackNames: Record<number, string> = {0:"Melbourne",2:"Shanghai",3:"Bahrain",4:"Barcelona",5:"Monaco",6:"Montreal",7:"Silverstone",9:"Hungaroring",10:"Spa",11:"Monza",12:"Singapore",13:"Suzuka",14:"Abu Dhabi",15:"Austin",16:"São Paulo",17:"Austria",19:"Mexico",20:"Baku",26:"Zandvoort",27:"Imola",29:"Jeddah",30:"Miami",31:"Las Vegas",32:"Lusail"};

export default function LapComparePanel() {
  const [sessions, setSessions] = useState<StoredSession[]>([]);
  const [laps, setLaps] = useState<StoredLap[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [referenceId, setReferenceId] = useState("");
  const [comparisonId, setComparisonId] = useState("");
  const [result, setResult] = useState<LapComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const request = useRef(0);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    getStoredSessions().then(data => {
      if (!active) return;
      setSessions(data);
      setSessionId(current => data.some(s => s.sessionId === current) ? current : data[0]?.sessionId ?? "");
    }).catch(e => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    let active = true;
    request.current++; setComparing(false); setResult(null); setLaps([]); setError("");
    setReferenceId(""); setComparisonId("");
    if (!sessionId) return;
    setLoading(true);
    getSessionLaps(sessionId).then(data => {
      if (!active) return;
      setLaps(data); setReferenceId(data[0]?.lapId ?? ""); setComparisonId(data[1]?.lapId ?? "");
    }).catch(e => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; request.current++; };
  }, [sessionId, refresh]);
  const selectLap = (id: string, reference: boolean) => {
    request.current++; setComparing(false); setResult(null); setError("");
    if (reference) setReferenceId(id); else setComparisonId(id);
  };
  const compare = async () => {
    const token = ++request.current;
    setComparing(true); setError(""); setResult(null);
    try {
      const response = await getLapComparison(referenceId, comparisonId);
      if (token === request.current) setResult(response);
    } catch (e) { if (token === request.current) setError(e instanceof Error ? e.message : "Comparison failed"); }
    finally { if (token === request.current) setComparing(false); }
  };
  const reference = laps.find(l => l.lapId === referenceId);
  const comparison = laps.find(l => l.lapId === comparisonId);
  return <section className="comparison-workspace">
    <header className="comparison-header"><div><span className="eyebrow">LAP ANALYSIS</span><h2>Compare two laps</h2><p>Choose a reference, then see where your comparison lap gains or loses time.</p></div><button onClick={() => setRefresh(v => v + 1)} disabled={loading}>Refresh laps</button></header>
    <div className="compare-controls">
      <label>Session<select value={sessionId} disabled={loading} onChange={e => setSessionId(e.target.value)}><option value="" disabled>Select session</option>{sessions.map(s => <option key={s.sessionId} value={s.sessionId}>{trackNames[s.trackId ?? -1] ?? `Track ${s.trackId ?? "—"}`} · {s.startedAt ? new Date(s.startedAt).toLocaleString() : s.sessionId.slice(-8)} · {s.lapCount} laps</option>)}</select></label>
      {[true, false].map(isReference => <label key={String(isReference)}>{isReference ? "Reference lap" : "Comparison lap"}<select value={isReference ? referenceId : comparisonId} disabled={loading || !laps.length} onChange={e => selectLap(e.target.value, isReference)}><option value="" disabled>Select lap</option>{laps.map(l => <option key={l.lapId} value={l.lapId}>Lap {l.lapNumber} · {formatLapTime(l.lapTimeMs)}{l.invalid ? " · invalid" : l.partial ? " · partial" : ""}</option>)}</select></label>)}
      <button className="persistent-compare-button" onClick={compare} disabled={loading || comparing || !referenceId || !comparisonId || referenceId === comparisonId}>{comparing ? "Comparing…" : "Compare laps"}</button>
    </div>
    {error && <p className="persistent-error" role="alert">{error}</p>}
    {loading && <p role="status" className="persistent-message">Loading laps…</p>}
    {reference && comparison && <div className="compare-summary">
      <div><span>REFERENCE · LAP {reference.lapNumber}</span><strong>{formatLapTime(reference.lapTimeMs)}</strong><small>{reference.invalid ? "Invalid lap" : reference.partial ? "Partial recording" : "Valid lap"}</small></div>
      <div><span>COMPARISON · LAP {comparison.lapNumber}</span><strong>{formatLapTime(comparison.lapTimeMs)}</strong><small>{comparison.invalid ? "Invalid lap" : comparison.partial ? "Partial recording" : "Valid lap"}</small></div>
      <div><span>TIME DIFFERENCE</span><strong className={result && result.totalTimeDeltaMs < 0 ? "text-green" : "text-amber"}>{result ? `${result.totalTimeDeltaMs > 0 ? "+" : ""}${(result.totalTimeDeltaMs / 1000).toFixed(3)}s` : "—"}</strong><small>Negative = comparison faster</small></div>
      {[1,2,3].map(n => {
        const key = `sector${n}TimeMs` as "sector1TimeMs" | "sector2TimeMs" | "sector3TimeMs";
        const a = reference[key], b = comparison[key];
        return <div key={n}><span>SECTOR {n}</span><strong className={a && b && b <= a ? "text-green" : "text-amber"}>{a && b ? formatDelta(b-a) : "—"}</strong><small>{formatLapTime(a)} → {formatLapTime(b)}</small></div>;
      })}
    </div>}
    {result ? <><ComparisonGraphs result={result} /><details className="comparison-quality"><summary>Recording quality</summary><p>{result.validDeltaPoints} of {result.gridPoints} distance points have comparable timing. Gaps remain visible in the charts.</p><p>{[...(reference?.qualityReasons ?? []), ...(comparison?.qualityReasons ?? [])].join(" · ") || "No recording quality flags."}</p></details></> : !loading && <div className="compare-empty"><strong>{sessions.length === 0 ? "No recorded sessions yet" : laps.length < 2 ? "Two completed laps are needed" : "Ready to compare"}</strong><p>{laps.length < 2 ? "Complete two laps in the same session, then refresh." : "Select two different laps and choose Compare laps."}</p></div>}
  </section>;
}
