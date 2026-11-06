import { useState } from "react";

interface Corner {
  pace_status?: string; player_min_speed_kph: number | null; ideal_apex_speed_kph: number;
  turn: string; name: string; status: string; advice: string;
  brake_status: string; throttle_status: string;
  brake_on_ms: number | null; brake_release_ms: number | null; throttle_on_ms: number | null;
  player_brake_on_m: number | null; player_throttle_on_m: number | null;
  brake_delta_m: number | null; throttle_delta_m: number | null;
  sample_count: number;
}
export interface CoachAnalysisResponse {
  lapNum: number; nextSector: number; hasApiKey: boolean;
  lapInvalid: boolean; lapPartial: boolean; targetSource: string;
  corners: Corner[];
}
const label = (value: string) => value.replaceAll("_", " ").toUpperCase();
const time = (ms: number | null) => ms == null ? "No transition recorded" : `${(ms / 1000).toFixed(3)}s`;
const distance = (m: number | null) => m == null ? "—" : `${m.toFixed(0)}m`;

export default function CoachCards({ data, loading, error }: { data: CoachAnalysisResponse | null; loading: boolean; error: string }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (loading) return <p className="coach-empty" role="status">Reading previous-lap corner inputs…</p>;
  if (error) return <p className="coach-error" role="alert">{error}</p>;
  if (!data) return null;
  return <>
    <div className="coach-provenance">LAP {data.lapNum} · SECTOR {data.nextSector} {data.lapInvalid ? "· INVALID LAP" : ""} {data.lapPartial ? "· PARTIAL RECORDING" : ""} <span>Hover, focus or tap a turn</span></div>
    <div className="corner-cards">
      {data.corners.map(c => <article key={c.turn} className={`corner-card corner-${c.status}`} data-open={expanded === c.turn}>
        <button aria-expanded={expanded === c.turn} onClick={() => setExpanded(expanded === c.turn ? null : c.turn)}>
          <strong>T{c.turn} <span>{c.name}</span></strong><b>{label(c.pace_status ?? c.status)}</b>
        </button>
        <div className="corner-detail">
          <strong>T{c.turn} · {c.name}</strong>
          <p>{c.advice}</p>
          {c.pace_status !== 'insufficient_data' && c.player_min_speed_kph != null && <p>Apex pace: {label(c.pace_status ?? "insufficient_data")} · {c.player_min_speed_kph.toFixed(0)} / {c.ideal_apex_speed_kph.toFixed(0)} km/h target. Tolerance: ±5% or 5 km/h, whichever is larger. Fast means above this configured speed target, not a proven faster corner time.</p>}
          {c.sample_count > 0 && <dl><div><dt>Brake on · {label(c.brake_status)}</dt><dd>{time(c.brake_on_ms)} · {distance(c.player_brake_on_m)}</dd></div>
            <div><dt>Brake release</dt><dd>{time(c.brake_release_ms)}</dd></div>
            <div><dt>Throttle ≥85% · {label(c.throttle_status)}</dt><dd>{time(c.throttle_on_ms)} · {distance(c.player_throttle_on_m)}</dd></div>
          </dl>}<small>Times from lap start · distances along lap. {data.targetSource}.</small>
        </div>
      </article>)}
    </div>
    {!data.corners.length && <p className="coach-empty">No corner targets for this sector.</p>}
  </>;
}
