import { useEffect, useMemo, useState } from "react";
import { TRACK_FILES, isNumber, rotateTrackPoints, toSvgPath, type Position, type TrackOutline } from "./DashboardShared";

export interface CoachCorner {
  turn: string;
  name: string;
  start_m?: number;
  end_m?: number;
  apex_m?: number;
  sector?: number;
  pace_status?: string;
  player_min_speed_kph: number | null;
  player_exit_speed_kph?: number | null;
  ideal_apex_speed_kph: number;
  ideal_exit_speed_kph?: number;
  exit_speed_delta_kph?: number;
  speed_buffer_kph?: number;
  status: string;
  advice: string;
  sample_count: number;
}

export interface CoachAnalysisResponse {
  lapNum: number;
  nextSector: number;
  hasApiKey: boolean;
  lapInvalid: boolean;
  lapPartial: boolean;
  targetSource: string;
  track?: {
    track_id?: number;
    track_name?: string;
    track_length_m?: number;
  };
  corners: CoachCorner[];
}

const label = (value?: string | null) => (value ?? "").replaceAll("_", " ").toUpperCase();
const speedText = (kph: number | null | undefined) => (isNumber(kph) ? `${kph.toFixed(0)} km/h` : "—");
const deltaText = (delta: number | null | undefined) => {
  if (!isNumber(delta)) return "—";
  const rounded = Math.round(delta);
  return `${rounded > 0 ? "+" : ""}${rounded} km/h`;
};

function cornerAccent(status: string): string {
  if (status === "on_pace") return "#31d486";
  if (status === "below_target" || status === "slow") return "#f2b94b";
  return "#9ba6b7";
}

function CoachMiniMap({
  trackOutline,
  trackLength,
  corners,
  activeCorner,
}: {
  trackOutline: TrackOutline | null | undefined;
  trackLength?: number;
  corners: CoachCorner[];
  activeCorner: CoachCorner | null;
}) {
  const mapGeometry = useMemo(() => {
    if (!trackOutline) return null;
    const orient = trackOutline.orientation ?? 0;
    const leftEdge = rotateTrackPoints(trackOutline.leftEdge, orient);
    const rightEdge = rotateTrackPoints(trackOutline.rightEdge, orient);
    const rawLine =
      trackOutline.racingLine.length >= 2
        ? trackOutline.racingLine
        : trackOutline.leftEdge;
    const centerLine = rotateTrackPoints(rawLine, orient);
    const boundsPoints = [...leftEdge, ...rightEdge, ...centerLine];
    if (!boundsPoints.length) return null;

    const xs = boundsPoints.map((p) => p.x);
    const zs = boundsPoints.map((p) => p.z);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minZ = Math.min(...zs);
    const maxZ = Math.max(...zs);
    const spanX = Math.max(maxX - minX, 20);
    const spanZ = Math.max(maxZ - minZ, 20);
    const padX = spanX * 0.12;
    const padZ = spanZ * 0.12;
    const width = 460;
    const height = 320;
    const scale = Math.min(
      (width - 44) / (spanX + padX * 2),
      (height - 44) / (spanZ + padZ * 2),
    );
    const offsetX = (width - (spanX + padX * 2) * scale) / 2;
    const offsetY = (height - (spanZ + padZ * 2) * scale) / 2;
    const project = (point: Position) => ({
      x: offsetX + (point.x - minX + padX) * scale,
      y: offsetY + (point.z - minZ + padZ) * scale,
    });

    const surfacePath =
      leftEdge.length && rightEdge.length
        ? toSvgPath([...leftEdge, ...rightEdge.slice().reverse()], project, true)
        : "";
    const racingPath = centerLine.length >= 2 ? toSvgPath(centerLine, project, false) : "";
    const sfLeft = leftEdge.length ? project(leftEdge[0]) : null;
    const sfRight = rightEdge.length ? project(rightEdge[0]) : null;

    // Build cumulative arc lengths along centerLine so lap distances map cleanly onto the circuit.
    const cumArc: number[] = [0];
    for (let i = 1; i < centerLine.length; i += 1) {
      const dx = centerLine[i].x - centerLine[i - 1].x;
      const dz = centerLine[i].z - centerLine[i - 1].z;
      cumArc.push(cumArc[i - 1] + Math.hypot(dx, dz));
    }
    const totalArc = cumArc[cumArc.length - 1] || 1;
    const resolvedLength = isNumber(trackLength) && trackLength > 0 ? trackLength : totalArc;

    const pointAtDist = (distM: number): Position | null => {
      if (centerLine.length < 2) return null;
      const wrapped = ((distM % resolvedLength) + resolvedLength) % resolvedLength;
      const targetArc = (wrapped / resolvedLength) * totalArc;
      for (let i = 1; i < cumArc.length; i += 1) {
        if (cumArc[i] >= targetArc || i === cumArc.length - 1) {
          const segLen = cumArc[i] - cumArc[i - 1] || 1;
          const frac = Math.max(0, Math.min(1, (targetArc - cumArc[i - 1]) / segLen));
          return {
            x: centerLine[i - 1].x + (centerLine[i].x - centerLine[i - 1].x) * frac,
            z: centerLine[i - 1].z + (centerLine[i].z - centerLine[i - 1].z) * frac,
          };
        }
      }
      return centerLine[0];
    };

    const segmentPath = (startM: number, endM: number): string => {
      if (centerLine.length < 2) return "";
      const startPt = pointAtDist(startM);
      const endPt = pointAtDist(endM);
      if (!startPt || !endPt) return "";
      const lo = Math.min(startM, endM);
      const hi = Math.max(startM, endM);
      const pts: Position[] = [startPt];
      for (let i = 0; i < centerLine.length; i += 1) {
        const distAtIdx = (cumArc[i] / totalArc) * resolvedLength;
        if (distAtIdx > lo && distAtIdx < hi) pts.push(centerLine[i]);
      }
      pts.push(endPt);
      return toSvgPath(pts, project, false);
    };

    return { project, surfacePath, racingPath, sfLeft, sfRight, pointAtDist, segmentPath };
  }, [trackOutline, trackLength]);

  if (!mapGeometry) {
    return (
      <div className="coach-minimap-empty">
        <p>Mini map unavailable for this circuit.</p>
      </div>
    );
  }

  const cornerMarkers = corners
    .map((c) => {
      const markerDist = c.end_m ?? c.apex_m ?? c.start_m;
      if (!isNumber(markerDist)) return null;
      const worldPt = mapGeometry.pointAtDist(markerDist);
      if (!worldPt) return null;
      const pt = mapGeometry.project(worldPt);
      return { corner: c, pt };
    })
    .filter((m): m is { corner: CoachCorner; pt: { x: number; y: number } } => m !== null);

  const activeStart = activeCorner ? (activeCorner.start_m ?? activeCorner.apex_m ?? activeCorner.end_m) : undefined;
  const activeEnd = activeCorner ? (activeCorner.end_m ?? activeCorner.apex_m ?? activeCorner.start_m) : undefined;
  const activeSegment =
    activeCorner && isNumber(activeStart) && isNumber(activeEnd)
      ? mapGeometry.segmentPath(activeStart, activeEnd)
      : "";
  const activeMarker = activeCorner
    ? cornerMarkers.find((m) => m.corner.turn === activeCorner.turn && m.corner.name === activeCorner.name) ?? null
    : null;
  const activeColor = activeCorner ? cornerAccent(activeCorner.status) : "#a855f7";

  return (
    <div className="coach-minimap-wrap">
      <svg
        className="coach-minimap-svg"
        viewBox="0 0 460 320"
        role="img"
        aria-label={activeCorner ? `Circuit map highlighting Turn ${activeCorner.turn}` : "Circuit mini map"}
      >
        {mapGeometry.surfacePath && <path d={mapGeometry.surfacePath} className="circuit-halo" />}
        {mapGeometry.surfacePath && <path d={mapGeometry.surfacePath} className="circuit-surface" />}
        {mapGeometry.racingPath && <path d={mapGeometry.racingPath} className="circuit-racing-line" />}
        {mapGeometry.sfLeft && mapGeometry.sfRight && (
          <line
            x1={mapGeometry.sfLeft.x}
            y1={mapGeometry.sfLeft.y}
            x2={mapGeometry.sfRight.x}
            y2={mapGeometry.sfRight.y}
            className="coach-minimap-sf"
          />
        )}

        {cornerMarkers.map(({ corner, pt }) => {
          const isActive =
            activeCorner?.turn === corner.turn && activeCorner?.name === corner.name;
          return (
            <circle
              key={`marker-${corner.turn}-${corner.name}`}
              cx={pt.x}
              cy={pt.y}
              r={isActive ? 6.5 : 4}
              fill={cornerAccent(corner.status)}
              fillOpacity={isActive ? 1 : 0.72}
              stroke="#0d121a"
              strokeWidth={1.5}
            />
          );
        })}

        {activeSegment && (
          <>
            <path
              d={activeSegment}
              fill="none"
              stroke={activeColor}
              strokeOpacity={0.35}
              strokeWidth={14}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d={activeSegment}
              fill="none"
              stroke={activeColor}
              strokeWidth={5.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </>
        )}

        {activeMarker && (() => {
          const badgeX = Math.max(28, Math.min(410, activeMarker.pt.x + 12));
          const badgeY = Math.max(24, Math.min(296, activeMarker.pt.y - 12));
          return (
            <g className="coach-minimap-highlight">
              <circle
                cx={activeMarker.pt.x}
                cy={activeMarker.pt.y}
                r={12}
                fill="none"
                stroke={activeColor}
                strokeWidth={2.5}
                className="coach-minimap-pulse"
              />
              <circle
                cx={activeMarker.pt.x}
                cy={activeMarker.pt.y}
                r={5.5}
                fill="#ffffff"
                stroke={activeColor}
                strokeWidth={2.5}
              />
              <rect
                x={badgeX - 4}
                y={badgeY - 14}
                width={Math.max(34, 18 + activeMarker.corner.turn.length * 8)}
                height={20}
                rx={5}
                fill="#11161e"
                stroke={activeColor}
                strokeWidth={1.5}
              />
              <text
                x={badgeX + 4}
                y={badgeY}
                fill="#ffffff"
                fontSize="11"
                fontWeight="700"
                fontFamily="DM Mono, monospace"
              >
                T{activeMarker.corner.turn}
              </text>
            </g>
          );
        })()}
      </svg>

      <div className="coach-minimap-caption">
        {activeCorner ? (
          <>
            <strong>T{activeCorner.turn} · {activeCorner.name}</strong>
            <span>
              {isNumber(activeCorner.start_m) && isNumber(activeCorner.end_m)
                ? `${activeCorner.start_m.toFixed(0)}–${activeCorner.end_m.toFixed(0)} m · `
                : ""}
              Exit {speedText(activeCorner.player_exit_speed_kph ?? activeCorner.player_min_speed_kph)} vs{" "}
              {speedText(activeCorner.ideal_exit_speed_kph ?? activeCorner.ideal_apex_speed_kph)}
            </span>
          </>
        ) : (
          <span>Hover or select a corner tile to highlight it on the map.</span>
        )}
      </div>
    </div>
  );
}

export default function CoachCards({
  data,
  loading,
  error,
  trackOutline,
}: {
  data: CoachAnalysisResponse | null;
  loading: boolean;
  error: string;
  trackOutline?: TrackOutline | null;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [fallbackOutline, setFallbackOutline] = useState<TrackOutline | null>(null);

  const trackId = data?.track?.track_id;
  useEffect(() => {
    if (trackOutline || trackId == null) {
      setFallbackOutline(null);
      return;
    }
    const fileName = TRACK_FILES[trackId];
    if (!fileName) return;

    const controller = new AbortController();
    fetch(`/track_data/${fileName}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        if (controller.signal.aborted) return;
        setFallbackOutline({
          leftEdge: (d.left_edge ?? []).map(([x, z]: number[]) => ({ x, z })),
          rightEdge: (d.right_edge ?? []).map(([x, z]: number[]) => ({ x, z })),
          racingLine: (d.lines?.formula1?.racing_line ?? []).map(([x, z]: number[]) => ({ x, z })),
          orientation: Number(d.orientation ?? 0),
          sfLine: d.sf_line,
        });
      })
      .catch(() => { });
    return () => controller.abort();
  }, [trackOutline, trackId]);

  if (loading) return <p className="coach-empty" role="status">Reading previous-lap corner exit speeds…</p>;
  if (error) return <p className="coach-error" role="alert">{error}</p>;
  if (!data) return null;

  const resolvedOutline = trackOutline ?? fallbackOutline;
  const activeKey = hovered ?? expanded;
  const activeCorner =
    data.corners.find((c) => `${c.turn}-${c.name}` === activeKey) ?? null;

  return (
    <>
      <div className="coach-provenance">
        LAP {data.lapNum} · SECTOR {data.nextSector} · EXIT SPEED (50 KM/H BUFFER)
        <span>Hover a turn to highlight on map</span>
      </div>
      <div className="coach-layout">
        <div className="corner-cards">
          {data.corners.map((c) => {
            const cardKey = `${c.turn}-${c.name}`;
            const isOpen = expanded === cardKey;
            const isActive = activeKey === cardKey;
            const exitSpeed = c.player_exit_speed_kph ?? c.player_min_speed_kph;
            const targetSpeed = c.ideal_exit_speed_kph ?? c.ideal_apex_speed_kph;
            const bufferKph = c.speed_buffer_kph ?? 50;
            const badgeText =
              c.status === "insufficient_data"
                ? "INSUFFICIENT DATA"
                : c.pace_status === "slow" || c.status === "below_target"
                  ? "SLOW (>50 KM/H)"
                  : "ON PACE";

            return (
              <article
                key={cardKey}
                className={`corner-card corner-${c.status}`}
                data-open={isOpen}
                data-active={isActive}
                onMouseEnter={() => setHovered(cardKey)}
                onMouseLeave={() => setHovered((prev) => (prev === cardKey ? null : prev))}
                onFocus={() => setHovered(cardKey)}
                onBlur={() => setHovered((prev) => (prev === cardKey ? null : prev))}
              >
                <button aria-expanded={isOpen} onClick={() => setExpanded(isOpen ? null : cardKey)}>
                  <strong>T{c.turn} <span>{c.name}</span></strong>
                  <b>{badgeText} · {c.status === "insufficient_data" ? "NO DATA" : `${speedText(exitSpeed)} / ${speedText(targetSpeed)}`}</b>
                  {c.advice && <p className="corner-preview">{c.advice}</p>}
                </button>
                <div className="corner-detail">
                  <strong>T{c.turn} · {c.name}</strong>
                  <p>{c.advice}</p>
                  {c.status !== "insufficient_data" && isNumber(exitSpeed) && (
                    <dl>
                      <div>
                        <dt>Exit speed · {label(c.pace_status ?? c.status)}</dt>
                        <dd>{speedText(exitSpeed)}</dd>
                      </div>
                      <div>
                        <dt>Target exit speed</dt>
                        <dd>{speedText(targetSpeed)}</dd>
                      </div>
                      <div>
                        <dt>Delta ({bufferKph.toFixed(0)} km/h buffer)</dt>
                        <dd>{deltaText(c.exit_speed_delta_kph)}</dd>
                      </div>
                      {isNumber(c.end_m) && (
                        <div>
                          <dt>Corner exit point</dt>
                          <dd>{c.end_m.toFixed(0)} m</dd>
                        </div>
                      )}
                    </dl>
                  )}
                  <small>Exit speed checked at corner exit with a {bufferKph.toFixed(0)} km/h buffer. {data.targetSource}.</small>
                </div>
              </article>
            );
          })}
          {!data.corners.length && <p className="coach-empty">No corner targets for this sector.</p>}
        </div>

        <aside className="coach-minimap-panel" aria-label="Circuit corner locator">
          <div className="coach-minimap-header">
            <span>CIRCUIT MAP</span>
            <b>{activeCorner ? `T${activeCorner.turn}` : `SECTOR ${data.nextSector}`}</b>
          </div>
          <CoachMiniMap
            trackOutline={resolvedOutline}
            trackLength={data.track?.track_length_m}
            corners={data.corners}
            activeCorner={activeCorner}
          />
        </aside>
      </div>
    </>
  );
}
