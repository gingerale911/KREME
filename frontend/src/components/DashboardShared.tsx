import React, { useMemo } from "react";

export type MaybeNumber = number | null | undefined;

export interface Position {
  x: number;
  z: number;
}

export interface PlotPoint {
  gapBefore?: boolean;
  at: number;
  distance: number;
  speed: number;
  throttle: number;
  brake: number;
}

export interface TrackOutline {
  leftEdge: Position[];
  rightEdge: Position[];
  racingLine: Position[];
  orientation: number;
  sfLine?: { pos: [number, number]; heading?: number };
}

export interface Session {
  uid?: MaybeNumber;
  trackId?: MaybeNumber;
  trackName?: string | null;
  trackLength?: MaybeNumber;
  weather?: string | number | null;
  trackTemp?: MaybeNumber;
  airTemp?: MaybeNumber;
  totalLaps?: MaybeNumber;
  sector2Start?: MaybeNumber;
  sector3Start?: MaybeNumber;
}

export interface Player {
  speed?: MaybeNumber;
  throttle?: MaybeNumber;
  brake?: MaybeNumber;
  steer?: MaybeNumber;
  gear?: MaybeNumber;
  rpm?: MaybeNumber;
  drs?: MaybeNumber;
  drsAllowed?: MaybeNumber;
  ersStore?: MaybeNumber;
  ersMode?: MaybeNumber;
  fuel?: MaybeNumber;
  fuelLaps?: MaybeNumber;
  lapDist?: MaybeNumber;
  lapTime?: MaybeNumber;
  lapNum?: MaybeNumber;
  sector?: MaybeNumber;
  position?: MaybeNumber;
  invalid?: boolean | number | null;
  pitStatus?: MaybeNumber;
  gLat?: MaybeNumber;
  gLong?: MaybeNumber;
  tyreCompound?: string | number | null;
  tyreAge?: MaybeNumber;
  suggestedGear?: MaybeNumber;
  sector1TimeMs?: MaybeNumber;
  sector2TimeMs?: MaybeNumber;
  sector3TimeMs?: MaybeNumber;
  driverNumber?: MaybeNumber;
  tyres?: {
    wheelOrder?: string[];
    actualCompound?: MaybeNumber;
    actualCompoundName?: string | null;
    visualCompound?: MaybeNumber;
    visualCompoundName?: string | null;
    ageLaps?: MaybeNumber;
    surfaceTempC?: Array<MaybeNumber>;
    innerTempC?: Array<MaybeNumber>;
    pressurePsi?: Array<MaybeNumber>;
    brakeTempC?: Array<MaybeNumber>;
    wearPct?: Array<MaybeNumber>;
    damagePct?: Array<MaybeNumber>;
  };
  damage?: {
    frontLeftWingDamage?: MaybeNumber;
    frontRightWingDamage?: MaybeNumber;
    rearWingDamage?: MaybeNumber;
    floorDamage?: MaybeNumber;
    diffuserDamage?: MaybeNumber;
    sidepodDamage?: MaybeNumber;
  };
}

export interface Car {
  index?: MaybeNumber;
  worldX?: MaybeNumber;
  worldZ?: MaybeNumber;
  heading?: MaybeNumber;
  name?: string | null;
  driverNumber?: string | number | null;
  position?: MaybeNumber;
  isPlayer?: boolean;
}

export interface LapSample {
  gapBefore?: boolean;
  elapsedTimeMs?: MaybeNumber;
  distance?: MaybeNumber;
  lapDistance?: MaybeNumber;
  throttle?: MaybeNumber;
  brake?: MaybeNumber;
  speed?: MaybeNumber;
  steer?: MaybeNumber;
  steering?: MaybeNumber;
  gear?: MaybeNumber;
  rpm?: MaybeNumber;
  engineRPM?: MaybeNumber;
  drs?: MaybeNumber;
  suggestedGear?: MaybeNumber;
  gLat?: MaybeNumber;
  gLong?: MaybeNumber;
  sessionTime?: MaybeNumber;
}

export interface LapSummary {
  id?: string;
  sessionUid?: string;
  lap?: MaybeNumber;
  trackId?: MaybeNumber;
  trackLength?: MaybeNumber;
  lapTimeMs?: MaybeNumber;
  sector1TimeMs?: MaybeNumber;
  sector2TimeMs?: MaybeNumber;
  sector3TimeMs?: MaybeNumber;
  invalid?: boolean;
  partial?: boolean;
  inProgress?: boolean;
  qualityReasons?: string[];
  sampleCount?: number;
  avgSpeedKph?: MaybeNumber;
  maxSpeedKph?: MaybeNumber;
  avgThrottle?: MaybeNumber;
  avgBrake?: MaybeNumber;
  samples?: LapSample[];
}

export const TRACK_FILES: Record<number, string> = {
  0: "f1-25_melbourne.json",
  2: "f1-25_shanghai.json",
  3: "f1-25_sakhir.json",
  4: "f1-25_catalunya.json",
  5: "f1-25_monaco.json",
  6: "f1-25_montreal.json",
  7: "f1-25_silverstone.json",
  9: "f1-25_hungaroring.json",
  10: "f1-25_spa.json",
  11: "f1-25_monza.json",
  12: "f1-25_singapore.json",
  13: "f1-25_suzuka.json",
  14: "f1-25_abu-dhabi.json",
  15: "f1-25_texas.json",
  16: "f1-25_brazil.json",
  17: "f1-25_red-bull-ring.json",
  19: "f1-25_mexico.json",
  20: "f1-25_baku.json",
  26: "f1-25_zandvoort.json",
  27: "f1-25_imola.json",
  29: "f1-25_jeddah.json",
  30: "f1-25_miami.json",
  31: "f1-25_las-vegas.json",
  32: "f1-25_losail.json",
};

export const TRACK_NAMES: Record<number, string> = {
  0: "Melbourne",
  2: "Shanghai",
  3: "Bahrain",
  4: "Barcelona",
  5: "Monaco",
  6: "Montreal",
  7: "Silverstone",
  9: "Hungaroring",
  10: "Spa-Francorchamps",
  11: "Monza",
  12: "Singapore",
  13: "Suzuka",
  14: "Abu Dhabi",
  15: "Austin (COTA)",
  16: "São Paulo (Interlagos)",
  17: "Red Bull Ring",
  19: "Mexico City",
  20: "Baku City",
  26: "Zandvoort",
  27: "Imola",
  29: "Jeddah Corniche",
  30: "Miami",
  31: "Las Vegas",
  32: "Lusail (Qatar)",
};

export function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function displayNumber(value: MaybeNumber, digits = 0, suffix = ""): string {
  return isNumber(value) ? `${value.toFixed(digits)}${suffix}` : "—";
}

export function formatTime(ms: MaybeNumber): string {
  if (!isNumber(ms) || ms <= 0) return "—";
  const minutes = Math.floor(ms / 60_000);
  const seconds = ((ms % 60_000) / 1000).toFixed(3).padStart(6, "0");
  return minutes > 0 ? `${minutes}:${seconds}` : seconds;
}

export function percent(value: MaybeNumber): string {
  return isNumber(value) ? `${Math.round(value * 100)}%` : "—";
}

export function rotateTrackPoints(points: Position[], angleDeg: number): Position[] {
  const radians = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);

  return points.map((point) => ({
    x: point.x * cos - point.z * sin,
    z: point.x * sin + point.z * cos,
  }));
}

export function toSvgPath(
  points: Position[],
  project: (point: Position) => { x: number; y: number },
  close = false,
): string {
  if (!points.length) return "";
  const first = project(points[0]);
  const rest = points.slice(1).map((point) => project(point));
  const path = rest.reduce(
    (acc, point) => `${acc} L ${point.x.toFixed(1)} ${point.y.toFixed(1)}`,
    `M ${first.x.toFixed(1)} ${first.y.toFixed(1)}`,
  );
  return close ? `${path} Z` : path;
}

export function PanelHeading({
  eyebrow,
  title,
  trailing,
}: {
  eyebrow: string;
  title: string;
  trailing?: React.ReactNode;
}) {
  return (
    <div className="panel-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
      </div>
      {trailing && <div className="panel-trailing">{trailing}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  unit,
}: {
  label: string;
  value: string;
  unit?: string;
}) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>
        {value}
        <small>{unit}</small>
      </strong>
    </div>
  );
}

export function TrackMap({
  cars,
  history,
  player,
  trackOutline,
}: {
  cars: Car[];
  history: Position[];
  player?: Player;
  trackOutline: TrackOutline | null;
}) {
  const transformedWorld = useMemo(() => {
    const orient = trackOutline?.orientation ?? 0;
    const rotatePoint = (point: Position) => rotateTrackPoints([point], orient)[0];
    const mappedHistory = history.map((point) => rotatePoint(point));
    const mappedCars = cars
      .filter((car) => isNumber(car.worldX) && isNumber(car.worldZ))
      .map((car) => rotatePoint({ x: car.worldX!, z: car.worldZ! }));
    const trackPoints = trackOutline
      ? [
          ...rotateTrackPoints(trackOutline.leftEdge, orient),
          ...rotateTrackPoints(trackOutline.rightEdge, orient),
        ]
      : [];
    return { mappedHistory, mappedCars, trackPoints };
  }, [cars, history, trackOutline]);

  const bounds = useMemo(() => {
    const points =
      transformedWorld.trackPoints.length > 0
        ? transformedWorld.trackPoints
        : [
            ...transformedWorld.mappedHistory,
            ...transformedWorld.mappedCars,
          ];
    if (!points.length) return null;
    const xs = points.map((point) => point.x);
    const zs = points.map((point) => point.z);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minZ = Math.min(...zs);
    const maxZ = Math.max(...zs);
    const spanX = Math.max(maxX - minX, 20);
    const spanZ = Math.max(maxZ - minZ, 20);
    const padX = spanX * 0.12;
    const padZ = spanZ * 0.12;
    const width = 1000;
    const height = 560;
    const scale = Math.min((width - 100) / (spanX + padX * 2), (height - 90) / (spanZ + padZ * 2));
    const offsetX = (width - (spanX + padX * 2) * scale) / 2;
    const offsetY = (height - (spanZ + padZ * 2) * scale) / 2;
    const project = (point: Position) => ({
      x: offsetX + (point.x - minX + padX) * scale,
      y: offsetY + (point.z - minZ + padZ) * scale,
    });
    return { project };
  }, [transformedWorld]);

  const liveTracePoints =
    transformedWorld.mappedHistory.length > 0
      ? transformedWorld.mappedHistory
      : transformedWorld.mappedCars;
  const path =
    bounds && liveTracePoints.length > 1
      ? liveTracePoints
          .map((point) => {
            const projected = bounds.project(point);
            return `${projected.x.toFixed(1)},${projected.y.toFixed(1)}`;
          })
          .join(" ")
      : "";
  const hasTrack = liveTracePoints.length > 5 || Boolean(trackOutline);
  const staticTrackAvailable = Boolean(trackOutline);
  const trackSurfacePath =
    bounds && trackOutline
      ? toSvgPath(
          [
            ...rotateTrackPoints(trackOutline.leftEdge, trackOutline.orientation),
            ...rotateTrackPoints(trackOutline.rightEdge.slice().reverse(), trackOutline.orientation),
          ],
          bounds.project,
          true,
        )
      : "";
  const trackRacingLine =
    bounds && trackOutline
      ? toSvgPath(
          rotateTrackPoints(trackOutline.racingLine, trackOutline.orientation),
          bounds.project,
          false,
        )
      : "";
  const sfLeft =
    bounds && trackOutline?.leftEdge?.length
      ? bounds.project(rotateTrackPoints([trackOutline.leftEdge[0]], trackOutline.orientation)[0])
      : null;
  const sfRight =
    bounds && trackOutline?.rightEdge?.length
      ? bounds.project(rotateTrackPoints([trackOutline.rightEdge[0]], trackOutline.orientation)[0])
      : null;

  return (
    <div className="map-wrap">
      <svg
        className="track-map"
        viewBox="0 0 1000 560"
        role="img"
        aria-label="Live track map from car world positions"
      >
        <defs>
          <pattern id="map-grid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path
              d="M 50 0 L 0 0 0 50"
              fill="none"
              stroke="currentColor"
              strokeOpacity=".055"
              strokeWidth="1"
            />
          </pattern>
        </defs>
        <rect width="1000" height="560" fill="url(#map-grid)" />
        {trackOutline && trackSurfacePath ? (
          <>
            <path d={trackSurfacePath} className="circuit-halo" />
            <path d={trackSurfacePath} className="circuit-surface" />
            <path d={trackRacingLine} className="circuit-racing-line" />
            {sfLeft && sfRight && (
              <g className="map-start">
                <line x1={sfLeft.x} y1={sfLeft.y} x2={sfRight.x} y2={sfRight.y} className="sf-line" />
                <rect
                  x={(sfLeft.x + sfRight.x) / 2 - 13}
                  y={(sfLeft.y + sfRight.y) / 2 - 7}
                  width="26"
                  height="14"
                  rx="3"
                  className="sf-badge"
                />
                <text
                  x={(sfLeft.x + sfRight.x) / 2}
                  y={(sfLeft.y + sfRight.y) / 2 + 3.5}
                  textAnchor="middle"
                  className="sf-badge-text"
                >
                  S/F
                </text>
              </g>
            )}
          </>
        ) : (
          hasTrack &&
          path && (
            <>
              <polyline points={path} className="track-shadow" />
              <polyline points={path} className="track-line" />
            </>
          )
        )}
        {bounds && liveTracePoints.length > 1 && (
          <polyline
            points={(trackOutline ? liveTracePoints.slice(-90) : liveTracePoints)
              .map((point) => {
                const projected = bounds.project(point);
                return `${projected.x.toFixed(1)},${projected.y.toFixed(1)}`;
              })
              .join(" ")}
            className="player-trail"
          />
        )}
        {cars.map((car, index) => {
          if (!bounds || !isNumber(car.worldX) || !isNumber(car.worldZ)) return null;
          const rotated = rotateTrackPoints(
            [{ x: car.worldX, z: car.worldZ }],
            trackOutline?.orientation ?? 0,
          )[0];
          const point = bounds.project(rotated);
          const isPlayer =
            Boolean(car.isPlayer) || (isNumber(player?.position) && car.position === player.position);
          const heading = isNumber(car.heading) ? car.heading : 0;
          const forwardX = Math.sin(heading);
          const forwardZ = Math.cos(heading);
          const rotForward = rotateTrackPoints(
            [{ x: forwardX, z: forwardZ }],
            trackOutline?.orientation ?? 0,
          )[0];
          const magnitude = Math.hypot(rotForward.x, rotForward.z) || 1;
          const arrowScale = isPlayer ? 17 : 10;
          const tip = {
            x: point.x + (rotForward.x / magnitude) * arrowScale,
            y: point.y + (rotForward.z / magnitude) * arrowScale,
          };
          return (
            <g
              key={`${car.index ?? index}-${car.driverNumber ?? ""}`}
              className={isPlayer ? "map-car player-car" : "map-car"}
            >
              <circle cx={point.x} cy={point.y} r={isPlayer ? 12 : 7} className="car-dot" />
              {isPlayer && (
                <>
                  <circle cx={point.x} cy={point.y} r="20" className="player-ring" />
                  <line x1={point.x} y1={point.y} x2={tip.x} y2={tip.y} className="car-heading" />
                </>
              )}
              <text x={point.x + 14} y={point.y - 12} className="car-label">
                {car.driverNumber ?? car.name?.slice(0, 3) ?? `#${car.index ?? index}`}
              </text>
            </g>
          );
        })}
        {!hasTrack && (
          <g className="map-placeholder">
            <circle cx="500" cy="265" r="44" />
            <path d="M 500 221 L 500 199 M 478 265 L 455 265 M 522 265 L 545 265" />
            <text x="500" y="350">
              NO STATIC MAP
            </text>
            <text x="500" y="375">
              Learned trace only · geometry unavailable
            </text>
          </g>
        )}
      </svg>
      <div className="map-scale">
        <span className="map-legend-dot" /> LIVE CARS
        <span className="map-legend-line" />{" "}
        {staticTrackAvailable ? "POSITION TRACE" : "LEARNED TRACE"}
      </div>
    </div>
  );
}

export function MiniChart({
  points,
  mode,
}: {
  points: PlotPoint[];
  mode: "speed" | "pedals";
}) {
  const width = 720;
  const height = mode === "speed" ? 154 : 108;
  const padding = { top: 10, right: 12, bottom: 20, left: 36 };
  const maxY =
    mode === "speed"
      ? Math.max(100, Math.ceil((Math.max(...points.map((point) => point.speed), 100) * 1.05) / 50) * 50)
      : 100;
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const x = (index: number) =>
    padding.left + (points.length <= 1 ? 0 : (index / (points.length - 1)) * innerWidth);
  const y = (value: number) =>
    padding.top + innerHeight - (Math.max(0, Math.min(value, maxY)) / maxY) * innerHeight;
  const speedPath = points
    .map(
      (point, index) =>
        `${index > 0 && !point.gapBefore ? "L" : "M"}${x(index).toFixed(1)} ${y(point.speed).toFixed(1)}`,
    )
    .join(" ");
  const throttlePath = points
    .map(
      (point, index) =>
        `${index > 0 && !point.gapBefore ? "L" : "M"}${x(index).toFixed(1)} ${y(point.throttle * 100).toFixed(1)}`,
    )
    .join(" ");
  const brakePath = points
    .map(
      (point, index) =>
        `${index > 0 && !point.gapBefore ? "L" : "M"}${x(index).toFixed(1)} ${y(point.brake * 100).toFixed(1)}`,
    )
    .join(" ");
  const gridValues = mode === "speed" ? [0, maxY / 2, maxY] : [0, 50, 100];

  return (
    <svg
      className="telemetry-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={mode === "speed" ? "Rolling speed chart" : "Rolling throttle and brake chart"}
    >
      {gridValues.map((value) => (
        <g key={value}>
          <line
            x1={padding.left}
            x2={width - padding.right}
            y1={y(value)}
            y2={y(value)}
            className="chart-grid"
          />
          <text x={padding.left - 7} y={y(value) + 4} textAnchor="end" className="chart-axis-label">
            {Math.round(value)}
          </text>
        </g>
      ))}
      {points.length > 1 && mode === "speed" && <path d={speedPath} className="series-speed" />}
      {points.length > 1 && mode === "pedals" && (
        <>
          <path d={throttlePath} className="series-throttle" />
          <path d={brakePath} className="series-brake" />
        </>
      )}
      {points.length < 2 && (
        <text x={width / 2} y={height / 2} textAnchor="middle" className="chart-empty">
          WAITING FOR SAMPLES
        </text>
      )}
      <text x={padding.left} y={height - 2} className="chart-axis-label">
        ROLLING WINDOW
      </text>
      <text x={width - padding.right} y={height - 2} textAnchor="end" className="chart-axis-label">
        NOW
      </text>
    </svg>
  );
}
