import CarStatusPanel from "./components/CarStatusPanel";
import LapComparePanel from "./components/LapComparePanel";
import { useEffect, useMemo, useRef, useState } from "react";

type ConnectionState = "connecting" | "live" | "reconnecting";
type MaybeNumber = number | null | undefined;

interface Stats {
  connected?: boolean;
  packetsPerSecond?: MaybeNumber;
  packetsReceived?: MaybeNumber;
  packetsAccepted?: MaybeNumber;
  packetsRejected?: MaybeNumber;
  frameGaps?: MaybeNumber;
  lastPacketAgeSeconds?: MaybeNumber;
}

interface Session {
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

interface Player {
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

interface Car {
  index?: MaybeNumber;
  worldX?: MaybeNumber;
  worldZ?: MaybeNumber;
  heading?: MaybeNumber;
  name?: string | null;
  driverNumber?: string | number | null;
  position?: MaybeNumber;
  isPlayer?: boolean;
}

interface TelemetryEvent {
  code?: string;
  time?: MaybeNumber;
  details?: Record<string, unknown>;
}

interface LapSample {
  gapBefore?: boolean;
  elapsedTimeMs?: MaybeNumber;
  distance?: MaybeNumber;
  throttle?: MaybeNumber;
  brake?: MaybeNumber;
  speed?: MaybeNumber;
}

interface LapSummary {
  id?: string;
  invalid?: boolean;
  partial?: boolean;
  qualityReasons?: string[];
  lap?: MaybeNumber;
  lapTimeMs?: MaybeNumber;
  sector1TimeMs?: MaybeNumber;
  sector2TimeMs?: MaybeNumber;
  sector3TimeMs?: MaybeNumber;
  avgSpeedKph?: MaybeNumber;
  maxSpeedKph?: MaybeNumber;
  avgThrottle?: MaybeNumber;
  avgBrake?: MaybeNumber;
  samples?: LapSample[];
}

interface PacketFreshness {
  state: "missing" | "fresh" | "stale";
  ageSeconds: number | null;
}

interface CornerDeltaUI {
  turn: string;
  name: string;
  apex_m: number;
  sector: number;
  ideal_brake_m: number;
  ideal_apex_speed_kph: number;
  ideal_apex_gear: number;
  player_brake_on_m?: number | null;
  player_min_speed_kph: number;
  player_throttle_on_m?: number | null;
  brake_delta_m?: number | null;
  apex_speed_delta_kph: number;
  throttle_delta_m?: number | null;
  time_loss_s: number;
  diagnosis: string;
  notes: string;
}

interface CoachAnalysisResponse {
  track?: {
    track_id: number;
    track_name: string;
    track_length_m: number;
    ideal_lap_time_ms: number;
    sector1_end_m?: number;
    sector2_end_m?: number;
    corners?: Array<{
      turn: string;
      name: string;
      start_m: number;
      end_m: number;
      apex_m: number;
      sector: number;
      ideal_brake_m?: number;
      ideal_apex_speed_kph?: number;
      ideal_apex_gear?: number;
      ideal_throttle_m?: number;
      notes?: string;
    }>;
  };
  lapNum?: number | null;
  lapTimeMs?: number;
  nextSector?: number;
  currentSector?: number;
  hasApiKey: boolean;
  deltas: CornerDeltaUI[];
  allDeltas?: CornerDeltaUI[];
  advice: string;
  circuit?: any;
}

interface TelemetrySnapshot {
  liveStreamId?: string;
  gamePaused?: boolean;
  telemetrySample?: { id: string; sessionTime: number } | null;
  retainedLive?: { player?: Player; session?: Session; cars?: Car[] };
  recorder?: { epoch?: number; sessionUid?: string | null };
  freshness?: Record<string, PacketFreshness>;
  stats?: Stats;
  session?: Session;
  player?: Player;
  cars?: Car[];
  events?: Array<string | TelemetryEvent>;
  laps?: LapSummary[];
  frameCount?: MaybeNumber;
}

interface PlotPoint {
  gapBefore?: boolean;
  at: number;
  distance: number;
  speed: number;
  throttle: number;
  brake: number;
}

interface Position {
  x: number;
  z: number;
}

interface TrackOutline {
  leftEdge: Position[];
  rightEdge: Position[];
  racingLine: Position[];
  orientation: number;
}

const HISTORY_LIMIT = 360;
const MAP_HISTORY_LIMIT = 700;
const TRACK_FILES: Record<number, string> = {
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

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function displayNumber(value: MaybeNumber, digits = 0, suffix = ""): string {
  return isNumber(value) ? `${value.toFixed(digits)}${suffix}` : "—";
}

function formatTime(ms: MaybeNumber): string {
  if (!isNumber(ms) || ms <= 0) return "—";
  const minutes = Math.floor(ms / 60_000);
  const seconds = ((ms % 60_000) / 1000).toFixed(3).padStart(6, "0");
  return minutes > 0 ? `${minutes}:${seconds}` : seconds;
}

function percent(value: MaybeNumber): string {
  return isNumber(value) ? `${Math.round(value * 100)}%` : "—";
}

function socketAddress(): string {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/ws`;
}

function parseSnapshot(data: unknown): TelemetrySnapshot | null {
  if (!data || typeof data !== "object") return null;
  const object = data as Record<string, unknown>;
  const candidate = object.snapshot && typeof object.snapshot === "object"
    ? object.snapshot as TelemetrySnapshot
    : object as TelemetrySnapshot;
  if (!("player" in candidate || "session" in candidate || "connected" in candidate)) return null;
  return candidate;
}

function useTelemetry() {
  const [snapshot, setSnapshot] = useState<TelemetrySnapshot | null>(null);
  const [state, setState] = useState<ConnectionState>("connecting");
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    let retryTimer: number | undefined;
    let socket: WebSocket | undefined;
    let attempts = 0;

    const connect = () => {
      if (!active) return;
      setState(attempts === 0 ? "connecting" : "reconnecting");
      socket = new WebSocket(socketAddress());
      socket.onopen = () => {
        attempts = 0;
        if (active) setState("live");
      };
      socket.onmessage = (event) => {
        try {
          const parsed = parseSnapshot(JSON.parse(String(event.data)));
          if (parsed && active) {
            setSnapshot(parsed);
            setLastMessageAt(Date.now());
          }
        } catch {
          // Ignore non-JSON or partial frames; the next valid snapshot will refresh the UI.
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (!active) return;
        setState("reconnecting");
        const delay = Math.min(1_000 * 2 ** attempts, 10_000);
        attempts += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      active = false;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  return { snapshot, state, lastMessageAt };
}

function PanelHeading({ eyebrow, title, trailing }: { eyebrow: string; title: string; trailing?: React.ReactNode }) {
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

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}<small>{unit}</small></strong>
    </div>
  );
}

function rotateTrackPoints(points: Position[], angleDeg: number): Position[] {
  const radians = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(radians);
  const sin = Math.sin(radians);

  return points.map((point) => ({
    x: point.x * cos - point.z * sin,
    z: point.x * sin + point.z * cos,
  }));
}

function toSvgPath(points: Position[], project: (point: Position) => { x: number; y: number }, close = false): string {
  if (!points.length) return "";
  const first = project(points[0]);
  const rest = points.slice(1).map((point) => project(point));
  const path = rest.reduce((acc, point) => `${acc} L ${point.x.toFixed(1)} ${point.y.toFixed(1)}`, `M ${first.x.toFixed(1)} ${first.y.toFixed(1)}`);
  return close ? `${path} Z` : path;
}

function TrackMap({ cars, history, player, trackOutline }: { cars: Car[]; history: Position[]; player?: Player; trackOutline: TrackOutline | null }) {
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
    // If a static track outline is present, use trackPoints as the bounding box
    // so cars project cleanly on the circuit geometry without viewport distortion.
    const points = transformedWorld.trackPoints.length > 0
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
  }, [cars, history, trackOutline]);

  const liveTracePoints = transformedWorld.mappedHistory.length > 0
    ? transformedWorld.mappedHistory
    : transformedWorld.mappedCars;
  const path = bounds && liveTracePoints.length > 1
    ? liveTracePoints.map((point) => {
      const projected = bounds.project(point);
      return `${projected.x.toFixed(1)},${projected.y.toFixed(1)}`;
    }).join(" ")
    : "";
  const hasTrack = liveTracePoints.length > 5 || Boolean(trackOutline);
  const staticTrackAvailable = Boolean(trackOutline);
  const trackSurfacePath = bounds && trackOutline
    ? toSvgPath(
        [
          ...rotateTrackPoints(trackOutline.leftEdge, trackOutline.orientation),
          ...rotateTrackPoints(trackOutline.rightEdge.slice().reverse(), trackOutline.orientation),
        ],
        bounds.project,
        true,
      )
    : "";
  const trackRacingLine = bounds && trackOutline
    ? toSvgPath(rotateTrackPoints(trackOutline.racingLine, trackOutline.orientation), bounds.project, false)
    : "";

  return (
    <div className="map-wrap">
      <svg className="track-map" viewBox="0 0 1000 560" role="img" aria-label="Live track map from car world positions">
        <defs>
          <pattern id="map-grid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M 50 0 L 0 0 0 50" fill="none" stroke="currentColor" strokeOpacity=".055" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="1000" height="560" fill="url(#map-grid)" />
        {trackOutline && trackSurfacePath ? (
          <>
            <path d={trackSurfacePath} fill="rgba(44, 180, 166, 0.12)" stroke="rgba(78, 220, 193, 0.9)" strokeWidth={1.1} />
            <path d={trackRacingLine} fill="none" stroke="rgba(138, 173, 255, 0.72)" strokeWidth={1.2} strokeDasharray="4 4" />
          </>
        ) : (
          hasTrack && path && (
            <>
              <polyline points={path} className="track-shadow" />
              <polyline points={path} className="track-line" />
            </>
          )
        )}
        {cars.map((car, index) => {
          if (!bounds || !isNumber(car.worldX) || !isNumber(car.worldZ)) return null;
          const rotated = rotateTrackPoints([{ x: car.worldX, z: car.worldZ }], trackOutline?.orientation ?? 0)[0];
          const point = bounds.project(rotated);
          const isPlayer = Boolean(car.isPlayer) || (isNumber(player?.position) && car.position === player.position);
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
            <g key={`${car.index ?? index}-${car.driverNumber ?? ""}`} className={isPlayer ? "map-car player-car" : "map-car"}>
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
            <text x="500" y="350">NO STATIC MAP</text>
            <text x="500" y="375">Learned trace only · geometry unavailable</text>
          </g>
        )}
      </svg>
      <div className="map-scale">
        <span className="map-legend-dot" /> LIVE CARS
        <span className="map-legend-line" /> {staticTrackAvailable ? "POSITION TRACE" : "LEARNED TRACE"}
      </div>
    </div>
  );
}

function MiniChart({ points, mode }: { points: PlotPoint[]; mode: "speed" | "pedals" }) {
  const width = 720;
  const height = mode === "speed" ? 154 : 108;
  const padding = { top: 10, right: 12, bottom: 20, left: 36 };
  const maxY = mode === "speed"
    ? Math.max(100, Math.ceil(Math.max(...points.map((point) => point.speed), 100) * 1.05 / 50) * 50)
    : 100;
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const x = (index: number) => padding.left + (points.length <= 1 ? 0 : (index / (points.length - 1)) * innerWidth);
  const y = (value: number) => padding.top + innerHeight - Math.max(0, Math.min(value, maxY)) / maxY * innerHeight;
  const speedPath = points.map((point, index) => `${index && !point.gapBefore ? "L" : "M"}${x(index).toFixed(1)} ${y(point.speed).toFixed(1)}`).join(" ");
  const throttlePath = points.map((point, index) => `${index && !point.gapBefore ? "L" : "M"}${x(index).toFixed(1)} ${y(point.throttle * 100).toFixed(1)}`).join(" ");
  const brakePath = points.map((point, index) => `${index && !point.gapBefore ? "L" : "M"}${x(index).toFixed(1)} ${y(point.brake * 100).toFixed(1)}`).join(" ");
  const gridValues = mode === "speed" ? [0, maxY / 2, maxY] : [0, 50, 100];

  return (
    <svg className="telemetry-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={mode === "speed" ? "Rolling speed chart" : "Rolling throttle and brake chart"}>
      {gridValues.map((value) => (
        <g key={value}>
          <line x1={padding.left} x2={width - padding.right} y1={y(value)} y2={y(value)} className="chart-grid" />
          <text x={padding.left - 7} y={y(value) + 4} textAnchor="end" className="chart-axis-label">{Math.round(value)}</text>
        </g>
      ))}
      {points.length > 1 && mode === "speed" && <path d={speedPath} className="series-speed" />}
      {points.length > 1 && mode === "pedals" && (
        <>
          <path d={throttlePath} className="series-throttle" />
          <path d={brakePath} className="series-brake" />
        </>
      )}
      {points.length < 2 && <text x={width / 2} y={height / 2} textAnchor="middle" className="chart-empty">WAITING FOR LIVE SAMPLES</text>}
      <text x={padding.left} y={height - 2} className="chart-axis-label">ROLLING WINDOW</text>
      <text x={width - padding.right} y={height - 2} textAnchor="end" className="chart-axis-label">NOW</text>
    </svg>
  );
}

interface CoachMiniMapProps {
  trackOutline: TrackOutline | null;
  circuit?: any;
  trackBenchmark?: CoachAnalysisResponse["track"];
  nextSector: number;
  deltas?: CornerDeltaUI[];
  allDeltas?: CornerDeltaUI[];
  advice?: string;
}

function CoachMiniMap({ trackOutline, circuit, trackBenchmark, nextSector, deltas = [], allDeltas = [], advice = "" }: CoachMiniMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<{
    turn: string;
    name: string;
    needsImprovement: boolean;
    timeLoss: number;
    delta?: CornerDeltaUI;
    x: number;
    y: number;
  } | null>(null);

  const rawRacingLine: Position[] = useMemo(() => {
    if (trackOutline?.racingLine && trackOutline.racingLine.length > 0) {
      return trackOutline.racingLine;
    }
    const f1Line = circuit?.lines?.formula1?.racing_line;
    if (Array.isArray(f1Line) && f1Line.length > 0) {
      return f1Line.map((pt: any) =>
        Array.isArray(pt) ? { x: Number(pt[0]), z: Number(pt[1]) } : { x: Number(pt.x), z: Number(pt.z) }
      );
    }
    return [];
  }, [trackOutline, circuit]);

  const rawLeftEdge: Position[] = useMemo(() => {
    if (trackOutline?.leftEdge && trackOutline.leftEdge.length > 0) return trackOutline.leftEdge;
    if (Array.isArray(circuit?.left_edge) && circuit.left_edge.length > 0) {
      return circuit.left_edge.map((pt: any) =>
        Array.isArray(pt) ? { x: Number(pt[0]), z: Number(pt[1]) } : { x: Number(pt.x), z: Number(pt.z) }
      );
    }
    return [];
  }, [trackOutline, circuit]);

  const rawRightEdge: Position[] = useMemo(() => {
    if (trackOutline?.rightEdge && trackOutline.rightEdge.length > 0) return trackOutline.rightEdge;
    if (Array.isArray(circuit?.right_edge) && circuit.right_edge.length > 0) {
      return circuit.right_edge.map((pt: any) =>
        Array.isArray(pt) ? { x: Number(pt[0]), z: Number(pt[1]) } : { x: Number(pt.x), z: Number(pt.z) }
      );
    }
    return [];
  }, [trackOutline, circuit]);

  const orientation = Number(trackOutline?.orientation ?? circuit?.orientation ?? 0);

  const rotatedRacingLine = useMemo(
    () => (rawRacingLine.length > 0 ? rotateTrackPoints(rawRacingLine, orientation) : []),
    [rawRacingLine, orientation]
  );
  const rotatedLeftEdge = useMemo(
    () => (rawLeftEdge.length > 0 ? rotateTrackPoints(rawLeftEdge, orientation) : []),
    [rawLeftEdge, orientation]
  );
  const rotatedRightEdge = useMemo(
    () => (rawRightEdge.length > 0 ? rotateTrackPoints(rawRightEdge, orientation) : []),
    [rawRightEdge, orientation]
  );

  const bounds = useMemo(() => {
    const points =
      rotatedLeftEdge.length > 0 && rotatedRightEdge.length > 0
        ? [...rotatedLeftEdge, ...rotatedRightEdge]
        : rotatedRacingLine;
    if (!points.length) return null;

    const xs = points.map((p) => p.x);
    const zs = points.map((p) => p.z);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minZ = Math.min(...zs);
    const maxZ = Math.max(...zs);
    const spanX = Math.max(maxX - minX, 20);
    const spanZ = Math.max(maxZ - minZ, 20);
    const padX = spanX * 0.12;
    const padZ = spanZ * 0.12;
    const width = 860;
    const height = 260;
    const scale = Math.min((width - 60) / (spanX + padX * 2), (height - 50) / (spanZ + padZ * 2));
    const offsetX = (width - (spanX + padX * 2) * scale) / 2;
    const offsetY = (height - (spanZ + padZ * 2) * scale) / 2;

    const project = (point: Position) => ({
      x: offsetX + (point.x - minX + padX) * scale,
      y: offsetY + (point.z - minZ + padZ) * scale,
    });

    return { project, width, height };
  }, [rotatedLeftEdge, rotatedRightEdge, rotatedRacingLine]);

  const trackLength = Number(trackBenchmark?.track_length_m || circuit?.game_track_length_m || 5000);

  // Focus sector corners with cross-referenced pace and telemetry check
  const targetCorners = useMemo(() => {
    const benchCorners = (trackBenchmark?.corners ?? []).filter((c) => c.sector === nextSector);
    const sourceList = benchCorners.length > 0 ? benchCorners : deltas;

    return sourceList.map((corner: any) => {
      const turnStr = String(corner.turn || "");
      const matchingDelta = (deltas ?? []).find((d) => {
        const dTurn = String(d.turn || "");
        if (dTurn === turnStr) return true;
        const rangeMatch = dTurn.match(/(\d+)\s*[-–]\s*(\d+)/);
        if (rangeMatch) {
          const start = parseInt(rangeMatch[1], 10);
          const end = parseInt(rangeMatch[2], 10);
          const cur = parseInt(turnStr, 10);
          return cur >= start && cur <= end;
        }
        return false;
      }) || (allDeltas ?? []).find((d) => String(d.turn) === turnStr);

      let needsImprovement = false;
      let timeLoss = matchingDelta ? Number(matchingDelta.time_loss_s || 0) : 0;

      if (matchingDelta) {
        const diag = (matchingDelta.diagnosis || "").toLowerCase();
        const hasDeficitDiag = Boolean(diag && !diag.includes("clean") && !diag.includes("optimal"));
        const hasBrakeDelta = matchingDelta.brake_delta_m !== undefined && matchingDelta.brake_delta_m !== null && Math.abs(matchingDelta.brake_delta_m) >= 10;
        const hasApexDelta = matchingDelta.apex_speed_delta_kph !== undefined && matchingDelta.apex_speed_delta_kph <= -8;
        const hasThrottleDelta = matchingDelta.throttle_delta_m !== undefined && matchingDelta.throttle_delta_m !== null && matchingDelta.throttle_delta_m >= 10;

        if (timeLoss > 0.03 || hasDeficitDiag || hasBrakeDelta || hasApexDelta || hasThrottleDelta) {
          needsImprovement = true;
        }
      }

      if (advice) {
        const adviceLines = advice.split("\n");
        for (const line of adviceLines) {
          const lineLower = line.toLowerCase();
          const turnMatch = lineLower.match(/turns?\s*(\d+)(?:\s*[-–]\s*(\d+))?/i);
          if (turnMatch) {
            const t1 = parseInt(turnMatch[1], 10);
            const t2 = turnMatch[2] ? parseInt(turnMatch[2], 10) : t1;
            const curTurn = parseInt(turnStr, 10);
            if (curTurn >= t1 && curTurn <= t2) {
              if (!lineLower.includes("on pace") && (
                lineLower.includes("brake") || lineLower.includes("push") || lineLower.includes("target") ||
                lineLower.includes("shift") || lineLower.includes("lift") || lineLower.includes("throttle") ||
                lineLower.includes("deeper") || lineLower.includes("earlier") || lineLower.includes("drop") ||
                lineLower.includes("bleed") || lineLower.includes("loss") || lineLower.includes("overslow")
              )) {
                needsImprovement = true;
                if (timeLoss === 0) timeLoss = 0.15;
              }
            }
          }
        }
      }

      return {
        turn: turnStr,
        name: corner.name && corner.name !== `Turn ${turnStr}` ? corner.name : "",
        start_m: corner.start_m ?? Math.max(0, (corner.apex_m || 100) - 45),
        end_m: corner.end_m ?? ((corner.apex_m || 100) + 45),
        apex_m: corner.apex_m || 100,
        sector: corner.sector || nextSector,
        delta: matchingDelta,
        needsImprovement,
        timeLoss,
      };
    });
  }, [trackBenchmark, nextSector, deltas, allDeltas, advice]);

  // Non-target sector corners (for subtle muted circuit reference)
  const otherCorners = useMemo(() => {
    return (trackBenchmark?.corners ?? []).filter((c) => c.sector !== nextSector);
  }, [trackBenchmark, nextSector]);

  if (!bounds || rotatedRacingLine.length < 5) {
    return null;
  }

  const surfacePath =
    rotatedLeftEdge.length > 0 && rotatedRightEdge.length > 0
      ? toSvgPath([...rotatedLeftEdge, ...rotatedRightEdge.slice().reverse()], bounds.project, true)
      : "";
  const fullRacingLinePath = toSvgPath(rotatedRacingLine, bounds.project, false);

  const handleMouseEnter = (corner: any, e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const relX = e.clientX - rect.left;
    const relY = e.clientY - rect.top;

    setHovered({
      turn: corner.turn,
      name: corner.name,
      needsImprovement: Boolean(corner.needsImprovement),
      timeLoss: Number(corner.timeLoss || 0),
      delta: corner.delta,
      x: Math.min(Math.max(relX, 120), rect.width - 120),
      y: Math.max(relY - 14, 12),
    });
  };

  const handleMouseLeave = () => {
    setHovered(null);
  };

  return (
    <div className="coach-minimap-card" ref={containerRef}>
      <div className="coach-minimap-header">
        <div className="coach-minimap-title">
          <span className="minimap-tag">CIRCUIT MAP</span>
          <span>SECTOR {nextSector} CORNER PACE ANALYSIS</span>
        </div>
        <div className="coach-minimap-legend">
          <span className="legend-item"><i className="dot-red" /> Improvement Needed</span>
          <span className="legend-item"><i className="dot-green" /> On Pace</span>
          <span className="legend-item"><i className="dot-muted" /> Full Circuit</span>
        </div>
      </div>

      <div className="coach-minimap-svg-wrap">
        <svg
          viewBox={`0 0 ${bounds.width} ${bounds.height}`}
          className="coach-minimap-svg"
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Faint track ribbon */}
          {surfacePath && (
            <path
              d={surfacePath}
              fill="rgba(255, 255, 255, 0.03)"
              stroke="rgba(255, 255, 255, 0.07)"
              strokeWidth={1}
            />
          )}

          {/* Full circuit racing line (muted) */}
          <path
            d={fullRacingLinePath}
            fill="none"
            stroke="rgba(148, 163, 184, 0.28)"
            strokeWidth={2.4}
            strokeDasharray="3 3"
          />

          {/* Subtle dots for other turns across the circuit */}
          {otherCorners.map((oc) => {
            const N = rotatedRacingLine.length;
            let idx = Math.round((oc.apex_m / trackLength) * (N - 1));
            idx = Math.max(0, Math.min(N - 1, idx));
            const pt = bounds.project(rotatedRacingLine[idx]);
            return (
              <g key={`other-turn-${oc.turn}`} className="other-turn-mark" opacity={0.35}>
                <circle cx={pt.x} cy={pt.y} r={2.5} fill="rgba(148, 163, 184, 0.8)" />
              </g>
            );
          })}

          {/* Highlighted corner paths for the NEXT sector ONLY */}
          {targetCorners.map((tc) => {
            const N = rotatedRacingLine.length;
            let sIdx = Math.floor((tc.start_m / trackLength) * (N - 1));
            let eIdx = Math.ceil((tc.end_m / trackLength) * (N - 1));
            sIdx = Math.max(0, Math.min(N - 1, sIdx));
            eIdx = Math.max(0, Math.min(N - 1, eIdx));
            if (Math.abs(eIdx - sIdx) < 4) {
              sIdx = Math.max(0, sIdx - 2);
              eIdx = Math.min(N - 1, eIdx + 2);
            }
            const slice = sIdx <= eIdx
              ? rotatedRacingLine.slice(sIdx, eIdx + 1)
              : [...rotatedRacingLine.slice(sIdx), ...rotatedRacingLine.slice(0, eIdx + 1)];
            const cornerD = toSvgPath(slice, bounds.project, false);

            const color = tc.needsImprovement ? "#ef4444" : "#10b981";

            return (
              <path
                key={`highlight-path-${tc.turn}`}
                d={cornerD}
                fill="none"
                stroke={color}
                strokeWidth={5}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="coach-corner-segment"
                onMouseEnter={(e) => handleMouseEnter(tc, e)}
                onMouseLeave={handleMouseLeave}
              />
            );
          })}

          {/* Apex markers and Turn badges for NEXT sector corners */}
          {targetCorners.map((tc) => {
            const N = rotatedRacingLine.length;
            let apexIdx = Math.round((tc.apex_m / trackLength) * (N - 1));
            apexIdx = Math.max(0, Math.min(N - 1, apexIdx));
            const pt = bounds.project(rotatedRacingLine[apexIdx]);

            const color = tc.needsImprovement ? "#ef4444" : "#10b981";

            return (
              <g
                key={`badge-${tc.turn}`}
                className="coach-turn-pin"
                transform={`translate(${pt.x}, ${pt.y})`}
                onMouseEnter={(e) => handleMouseEnter(tc, e)}
                onMouseLeave={handleMouseLeave}
                style={{ cursor: "pointer" }}
              >
                <circle r={11} fill="#0d131d" stroke={color} strokeWidth={2.4} />
                <text
                  y={3.5}
                  textAnchor="middle"
                  fill="#ffffff"
                  fontSize="9.5"
                  fontWeight="800"
                  fontFamily="'DM Mono', monospace, sans-serif"
                  pointerEvents="none"
                >
                  {tc.turn}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Hover Tooltip */}
        {hovered && (
          <div
            className="coach-minimap-tooltip"
            style={{
              left: `${hovered.x}px`,
              top: `${hovered.y}px`,
              transform: "translate(-50%, -100%)",
            }}
          >
            <div className="tooltip-top-row">
              <span className="tooltip-turn-title">Turn {hovered.turn}</span>
              {hovered.name ? <span className="tooltip-turn-name">{hovered.name}</span> : null}
              <span className={`tooltip-badge ${hovered.needsImprovement ? "badge-red" : "badge-green"}`}>
                {hovered.needsImprovement ? `+${hovered.timeLoss.toFixed(2)}s DEFICIT` : "ON PACE"}
              </span>
            </div>
            {hovered.delta?.diagnosis && (
              <div className="tooltip-diagnosis-text">{hovered.delta.diagnosis}</div>
            )}
            {hovered.delta && (
              <div className="tooltip-metrics-row">
                <span>Ghost Target: <b>{hovered.delta.ideal_apex_speed_kph} km/h (G{hovered.delta.ideal_apex_gear})</b></span>
                <span>Your Apex: <b>{hovered.delta.player_min_speed_kph} km/h</b></span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function parseCornerAdvice(rawAdvice: string): Array<{ turnTag: string; advice: string; isTurn: boolean }> {
  if (!rawAdvice) return [];
  const lines = rawAdvice.split("\n").map((l) => l.trim()).filter(Boolean);

  const items: Array<{ turnTag: string; advice: string; isTurn: boolean }> = [];
  let currentTag: string | null = null;
  let currentParts: string[] = [];

  const flush = () => {
    if (currentTag) {
      const text = currentParts.filter(Boolean).join(" ").trim().replace(/^[#*•\s-]+/, "");
      // Completely discard empty advice strings
      if (text) {
        items.push({ turnTag: currentTag, advice: text, isTurn: true });
      }
    }
    currentTag = null;
    currentParts = [];
  };

  for (const rawLine of lines) {
    let line = rawLine.trim();
    if (!line) continue;
    // Strip bolding and leading/trailing markdown hashes
    line = line.replace(/\*\*/g, "").replace(/__/g, "");
    const lineClean = line.replace(/^[#\s]+/, "").replace(/[#\s]+$/, "").trim();
    if (!lineClean) continue;

    // Discard generic section headers, empty notes, and markdown markers
    if (/^(?:sector\s*\d+\s*(?:summary|fixes)?|summary|corner-by-corner\s*fixes|fixes|notes?)\b/i.test(lineClean)) {
      continue;
    }

    // Match Turn with or without colon: "Turn 15 (Name): advice" or "Turn 15 (Name)" or "T15: advice"
    const turnMatch = lineClean.match(/^(?:[-*•\s]*)(Turns?\s+[\d–-]+(?:\s*\([^)]+\))?)\s*(?::\s*(.*))?$/i);
    if (turnMatch) {
      flush();
      currentTag = turnMatch[1].trim();
      const afterColon = (turnMatch[2] || "").trim();
      if (afterColon) {
        currentParts.push(afterColon);
      }
      continue;
    }

    if (currentTag) {
      // Sub-bullet under current turn
      const subMatch = lineClean.match(/^(?:[-*•\s]*)([^:]+):\s*(.*)$/);
      if (subMatch && ["braking", "braking/entry", "entry", "apex speed", "apex speed & gear", "apex speed and gear", "apex", "exit throttle", "throttle", "exit", "gear", "line"].includes(subMatch[1].toLowerCase().trim())) {
        currentParts.push(subMatch[2].trim());
      } else {
        currentParts.push(lineClean.replace(/^[-*•#\s]+/, ""));
      }
    } else {
      // General engineer note (NOT a turn)
      const cleanedGeneral = lineClean.replace(/^[-*•#\s]+/, "").trim();
      if (cleanedGeneral.length > 5 && !/^(?:note|fixes|summary)/i.test(cleanedGeneral)) {
        items.push({
          turnTag: "ENGINEER TIP",
          advice: cleanedGeneral,
          isTurn: false,
        });
      }
    }
  }

  flush();
  return items;
}

function App() {
  const { snapshot, state, lastMessageAt } = useTelemetry();
  const [plot, setPlot] = useState<PlotPoint[]>([]);
  const [mapHistory, setMapHistory] = useState<Position[]>([]);
  const [trackCatalog, setTrackCatalog] = useState<Record<number, TrackOutline>>({});
  const [trackOutline, setTrackOutline] = useState<TrackOutline | null>(null);
  const [lightTheme, setLightTheme] = useState(false);
  const [selectedLap, setSelectedLap] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"live" | "laps">("live");
  const [coachOpen, setCoachOpen] = useState(false);
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachData, setCoachData] = useState<CoachAnalysisResponse | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [keySaveMsg, setKeySaveMsg] = useState("");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [now, setNow] = useState(Date.now());
  const lastSample = useRef<string>("");
  const lastGameTime = useRef<number | null>(null);
  const traceGap = useRef(false);
  const socketConnected = state === "live" && lastMessageAt !== null && now - lastMessageAt < 2_000;

  useEffect(() => {
    fetch("/api/coach/status")
      .then((r) => r.json())
      .then((d) => setHasApiKey(Boolean(d.hasApiKey)))
      .catch(() => {});
  }, []);

  const saveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    try {
      const res = await fetch("/api/coach/key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: apiKeyInput.trim() }),
      });
      if (res.ok) {
        setHasApiKey(true);
        setKeySaveMsg("Saved! Rerun analysis to get Gemini insights.");
        setApiKeyInput("");
        setTimeout(() => setKeySaveMsg(""), 4000);
      }
    } catch (e) {
      setKeySaveMsg("Failed to save key");
    }
  };
  const stats = snapshot?.stats;
  const telemetryFresh = snapshot?.freshness?.telemetry?.state === "fresh";
  const paused = socketConnected && snapshot?.gamePaused === true && snapshot?.freshness?.session?.state === "fresh";
  const frozen = !socketConnected || paused || !telemetryFresh;
  const feedLabel = !socketConnected ? "DISCONNECTED" : paused ? "PAUSED" : !telemetryFresh ? (snapshot?.telemetrySample ? "STALE" : "WAITING FOR UDP") : "LIVE DATA";
  const shown = frozen ? snapshot?.retainedLive ?? snapshot : snapshot;
  const player = shown?.player;
  const session = shown?.session;

  const runCoachAnalysis = async () => {
    setCoachLoading(true);
    setCoachOpen(true);
    try {
      const res = await fetch("/api/coach/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trackId: session?.trackId,
          lapNum: isNumber(player?.lapNum) && player.lapNum > 1 ? player.lapNum - 1 : undefined,
        }),
      });
      const data = await res.json();
      setCoachData(data);
      if (typeof data.hasApiKey === "boolean") setHasApiKey(data.hasApiKey);
    } catch (e) {
      console.error(e);
    } finally {
      setCoachLoading(false);
    }
  };
    const displayDeltas = useMemo(() => {
    if (coachData?.deltas && coachData.deltas.length > 0) {
      return coachData.deltas;
    }
    const sec = coachData?.nextSector ?? 1;
    const corners = (coachData?.track?.corners ?? []).filter((c) => c.sector === sec);
    return corners.map((c): CornerDeltaUI => ({
      turn: String(c.turn),
      name: c.name || `Turn ${c.turn}`,
      apex_m: c.apex_m,
      sector: c.sector,
      ideal_brake_m: c.ideal_brake_m ?? Math.max(0, c.apex_m - 80),
      ideal_apex_speed_kph: c.ideal_apex_speed_kph ?? 120,
      ideal_apex_gear: c.ideal_apex_gear ?? 3,
      player_min_speed_kph: 0,
      apex_speed_delta_kph: 0,
      time_loss_s: 0,
      diagnosis: c.notes || "Ideal Ghost Target",
      notes: c.notes || "",
      player_brake_on_m: null,
      player_throttle_on_m: null,
      brake_delta_m: null,
      throttle_delta_m: null,
    }));
  }, [coachData]);

  const cars = Array.isArray(shown?.cars) ? shown.cars : [];
  const lapHistory = Array.isArray(snapshot?.laps) ? snapshot.laps : [];

  useEffect(() => {
    setSelectedLap(null);
    setPlot([]);
    setMapHistory([]);
    lastSample.current = "";
    lastGameTime.current = null;
    traceGap.current = false;
    window.sessionStorage.removeItem("krem-lap-history");
  }, [snapshot?.liveStreamId, snapshot?.recorder?.epoch, snapshot?.recorder?.sessionUid]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;

    const preloadTracks = async () => {
      const nextCatalog: Record<number, TrackOutline> = {};
      const entries = Object.entries(TRACK_FILES) as [string, string][];

      for (const [trackIdString, fileName] of entries) {
        try {
          const trackId = Number(trackIdString);
          // Try database API endpoint first, fallback to static JSON asset if offline/unseeded
          let data: {
            left_edge?: [number, number][];
            right_edge?: [number, number][];
            lines?: { formula1?: { racing_line?: [number, number][] } };
            orientation?: number;
          } | null = null;

          const dbRes = await fetch(`/api/circuits/${trackId}`);
          if (dbRes.ok) {
            data = await dbRes.json();
          } else {
            const staticRes = await fetch(`/track_data/${fileName}`);
            if (staticRes.ok) {
              data = await staticRes.json();
            }
          }

          if (!data) continue;

          const leftEdge = (data.left_edge ?? []).map(([x, z]) => ({ x, z }));
          const rightEdge = (data.right_edge ?? []).map(([x, z]) => ({ x, z }));
          const racingLine = (data.lines?.formula1?.racing_line ?? []).map(([x, z]) => ({ x, z }));

          nextCatalog[trackId] = {
            leftEdge,
            rightEdge,
            racingLine,
            orientation: Number(data.orientation ?? 0),
          };
        } catch {
          // Ignore any track file that fails to load; the session will keep showing the live trace fallback.
        }
      }

      if (active) {
        setTrackCatalog(nextCatalog);
      }
    };

    preloadTracks();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const trackId = session?.trackId;
    if (trackId === undefined || trackId === null || trackId < 0) {
      setTrackOutline(null);
      return;
    }
    setTrackOutline(trackCatalog[trackId] ?? null);
  }, [session?.trackId, trackCatalog]);

  useEffect(() => {
    if (frozen) { traceGap.current = true; return; }
    if (!player || !snapshot?.telemetrySample) return;
    const { id: marker, sessionTime } = snapshot.telemetrySample;
    if (marker === lastSample.current) return;
    lastSample.current = marker;
    // WebSocket refreshes and repeated paused frames are not driving samples.
    if (lastGameTime.current !== null && sessionTime <= lastGameTime.current) return;
    lastGameTime.current = sessionTime;

    if (isNumber(player.speed) && isNumber(player.throttle) && isNumber(player.brake)) {
      const point: PlotPoint = {
        at: Date.now(),
        gapBefore: traceGap.current,
        distance: isNumber(player.lapDist) ? player.lapDist : 0,
        speed: Math.max(0, player.speed ?? 0),
        throttle: Math.max(0, Math.min(1, player.throttle ?? 0)),
        brake: Math.max(0, Math.min(1, player.brake ?? 0)),
      };
      setPlot((current) => [...current.slice(-(HISTORY_LIMIT - 1)), point]);
      traceGap.current = false;
    }

    const playerCar = cars.find((car) => car.isPlayer)
      ?? (isNumber(player.position) ? cars.find((car) => car.position === player.position) : undefined);
    if (playerCar && isNumber(playerCar.worldX) && isNumber(playerCar.worldZ)) {
      setMapHistory((current) => [
        ...current.slice(-(MAP_HISTORY_LIMIT - 1)),
        { x: playerCar.worldX!, z: playerCar.worldZ! },
      ]);
    }
  }, [snapshot, player, cars, frozen]);

  const latestEvent = snapshot?.events?.at(-1);
  const eventText = typeof latestEvent === "string"
    ? latestEvent
    : latestEvent?.code
      ? `${latestEvent.code}${isNumber(latestEvent.time) ? ` · ${latestEvent.time.toFixed(1)}s` : ""}`
      : undefined;
  const connected = socketConnected && !frozen && stats?.connected === true;
  const currentSector = isNumber(player?.sector) ? Math.min(3, Math.max(1, player.sector + 1)) : null;
  const distance = isNumber(player?.lapDist) ? player.lapDist : null;
  const latestLap = lapHistory.length > 0 ? lapHistory[lapHistory.length - 1] : null;
  useEffect(() => {
    if (lapHistory.length === 0) return;
    const latestLapNumber = Number(latestLap?.lap ?? -1);
    if (selectedLap === null || !lapHistory.some((lap) => Number(lap.lap ?? -1) === selectedLap)) {
      setSelectedLap(latestLapNumber > 0 ? latestLapNumber : null);
    }
  }, [lapHistory, latestLap, selectedLap]);

  return (
    <main className={lightTheme ? "dashboard theme-light" : "dashboard"}>
      <header className="topbar">
        <a className="brand" href="#" aria-label="KREM dashboard home">
          <span className="brand-mark"><i /><i /><i /></span>
          <span>KREM<span className="brand-sub">TELEMETRY</span></span>
        </a>
        <div className="topbar-center">
          <span className="live-indicator" />
          <span>{session?.trackName || "WAITING FOR SESSION"}</span>
          {isNumber(player?.position) && <span className="position-pill">P{player.position}</span>}
        </div>
        <div className="topbar-actions">
          <button className="theme-toggle" onClick={() => setLightTheme((value) => !value)} aria-label="Toggle color theme">
            {lightTheme ? "☾" : "☼"}
          </button>
          <div className={`connection ${connected ? "is-live" : ""}`}>
            <span className="connection-dot" />
            <span>{feedLabel}</span>
          </div>
        </div>
      </header>

      <div className="status-strip">
        <div className="status-item"><span className="status-label">FEED</span><strong className={connected ? "text-green" : "text-amber"}>{feedLabel}</strong></div>
        <div className="status-item"><span className="status-label">PACKETS / SEC</span><strong>{displayNumber(stats?.packetsPerSecond)}</strong></div>
        <div className="status-item"><span className="status-label">FRAME GAPS</span><strong className={(stats?.frameGaps ?? 0) > 0 ? "text-amber" : ""}>{displayNumber(stats?.frameGaps)}</strong></div>
        <div className="status-item status-wide"><span className="status-label">FORMAT</span><strong>F1 25 · 2025</strong></div>
        <div className="status-tabs" aria-label="Dashboard views">
          <button className={activeTab === "live" ? "status-tab active" : "status-tab"} onClick={() => setActiveTab("live")}>Live</button>
          <button className={activeTab === "laps" ? "status-tab active" : "status-tab"} onClick={() => setActiveTab("laps")}>Lap compare</button>
        </div>
        <div className="status-event"><span className="event-pulse" />{eventText || "READY FOR RACE CONTROL EVENTS"}</div>
      </div>

      {!connected && (
        <div className="connection-banner" role="status">
          <span className="banner-icon">!</span>
          <div>
            <strong>{paused ? "Game paused — readings and traces frozen" : snapshot?.telemetrySample ? "Live feed unavailable — showing last received readings" : "Waiting for F1 25 telemetry"}</strong>
            <span>{paused ? "Inspect the existing traces at any point. Updates continue when the game resumes."
              : snapshot?.telemetrySample ? "Retained values are not live. No new graph samples are added until telemetry resumes."
              : "Configure F1 25 to send UDP telemetry using format 2025 to port 20777."}</span>
          </div>
        </div>
      )}

      {activeTab === "live" ? (
        <section className="dashboard-grid">
          <article className="panel panel-map">
            <PanelHeading eyebrow="01 / TRACK POSITION" title={session?.trackName || "Live track map"} trailing={<span className="panel-chip">{cars.length ? `${cars.length} CARS` : "NO CARS"}</span>} />
            <div className="map-meta">
              <span>{displayNumber(session?.trackLength)} <small>M TRACK</small></span>
              <span>{distance === null ? "—" : `${Math.max(0, distance).toFixed(0)} m`} <small>LAP DISTANCE</small></span>
              <span>{displayNumber(player?.speed)} <small>KM/H</small></span>
            </div>
            <TrackMap cars={cars} history={mapHistory} player={player} trackOutline={trackOutline} />
            <div className="panel-foot"><span><i className="legend-live" />PLAYER POSITION</span><span>WORLD X / Z</span></div>
          </article>

          <article className="panel panel-timing">
            <PanelHeading eyebrow="02 / LAP ANALYSIS" title="Sectors & timing" trailing={isNumber(player?.lapNum) ? <span className="lap-badge">LAP {player.lapNum}</span> : undefined} />
            <div className="timing-main">
              <div className="timer-block"><span className="eyebrow">CURRENT LAP</span><strong>{formatTime(player?.lapTime)}</strong><span className="timer-status">{player?.invalid ? "INVALID LAP" : currentSector ? `IN SECTOR ${currentSector}` : "WAITING FOR LAP"}</span></div>
              <div className="position-large"><span>POSITION</span><strong>{isNumber(player?.position) ? `P${player.position}` : "—"}</strong></div>
            </div>
            <div className="sector-track" aria-label="Three sector timing progress">
              {[1, 2, 3].map((sector) => (
                <div key={sector} className={`sector-segment ${currentSector === sector ? "sector-current" : currentSector && currentSector > sector ? "sector-complete" : ""}`}>
                  <span>S{sector}</span>
                  <strong>{formatTime(sector === 1 ? player?.sector1TimeMs : sector === 2 ? player?.sector2TimeMs : player?.sector3TimeMs)}</strong>
                  {sector < 3 && <i className="sector-divider" />}
                </div>
              ))}
            </div>
            <div className="timing-details">
              <div><span>LAP DISTANCE</span><strong>{distance === null ? "—" : `${Math.max(0, distance).toFixed(0)} m`}</strong></div>
              <div><span>RACE LAPS</span><strong>{isNumber(session?.totalLaps) ? `${isNumber(player?.lapNum) ? player.lapNum : "—"} / ${session.totalLaps}` : "—"}</strong></div>
              <div><span>LAP INVALID</span><strong className={player?.invalid == null ? "" : player.invalid ? "text-red" : "text-green"}>{player?.invalid == null ? "—" : player.invalid ? "YES" : "NO"}</strong></div>
            </div>
            <div className="timing-session">
              <div><span>TRACK</span><strong>{session?.trackName || "—"}</strong></div>
              <div><span>WEATHER</span><strong>{session?.weather ?? "—"}</strong></div>
              <div><span>TRACK TEMP</span><strong>{displayNumber(session?.trackTemp, 0, "°")}</strong></div>
              <div><span>AIR TEMP</span><strong>{displayNumber(session?.airTemp, 0, "°")}</strong></div>
            </div>
          </article>

          <article className="panel panel-charts">
            <PanelHeading eyebrow="03 / DRIVER INPUT" title="Telemetry traces" trailing={<span className="window-label">{frozen ? feedLabel : "ROLLING"} · {plot.length} SAMPLES</span>} />
            <div className="chart-legend">
              <span><i className="legend-speed" />SPEED <b>{displayNumber(player?.speed)} KM/H</b></span>
              <span><i className="legend-throttle" />THROTTLE <b>{percent(player?.throttle)}</b></span>
              <span><i className="legend-brake" />BRAKE <b>{percent(player?.brake)}</b></span>
            </div>
            <div className="chart-block">
              <div className="chart-title"><strong>SPEED</strong><span>KM/H</span></div>
              <MiniChart points={plot} mode="speed" />
            </div>
            <div className="chart-block chart-block-pedals">
              <div className="chart-title"><strong>PEDALS</strong><span>%</span></div>
              <MiniChart points={plot} mode="pedals" />
            </div>
            <div className="panel-foot"><span>DISTANCE {distance === null ? "—" : `${distance.toFixed(0)} M`}</span><span>LIVE TRACE · NO REFERENCE LAP</span></div>
          </article>

          <article className="panel panel-car-health">
            <PanelHeading eyebrow="03 / CHASSIS" title="Car health" trailing={<span className="panel-chip">TYRES · WINGS</span>} />
            <CarStatusPanel player={player} freshness={snapshot?.freshness} online={socketConnected} retained={frozen} paused={paused} />
          </article>

          <article className="panel panel-values">
            <PanelHeading eyebrow="04 / CAR TELEMETRY" title="Player values" trailing={<span className="gear-readout">{displayNumber(player?.gear)}</span>} />
            <div className="values-grid">
              <Stat label="SPEED" value={displayNumber(player?.speed)} unit="KM/H" />
              <Stat label="ENGINE RPM" value={isNumber(player?.rpm) ? player.rpm.toLocaleString() : "—"} />
              <Stat label="THROTTLE" value={percent(player?.throttle)} />
              <Stat label="BRAKE" value={percent(player?.brake)} />
              <Stat label="STEERING" value={displayNumber(player?.steer, 2)} />
              <Stat label="SUGGESTED GEAR" value={displayNumber(player?.suggestedGear)} />
              <Stat label="LATERAL G" value={displayNumber(player?.gLat, 2)} />
              <Stat label="LONGITUDINAL G" value={displayNumber(player?.gLong, 2)} />
              <Stat label="DRS" value={player?.drs == null ? "—" : player.drs ? "OPEN" : "CLOSED"} />
              <Stat label="DRS AVAILABLE" value={player?.drsAllowed == null ? "—" : player.drsAllowed ? "YES" : "NO"} />
              <Stat label="ERS STORE" value={displayNumber(player?.ersStore, 2)} unit="MJ" />
              <Stat label="ERS MODE" value={displayNumber(player?.ersMode)} />
              <Stat label="FUEL" value={displayNumber(player?.fuel, 1)} unit="KG" />
              <Stat label="FUEL LAPS" value={displayNumber(player?.fuelLaps, 1)} />
              <Stat label="TYRE COMPOUND" value={player?.tyreCompound == null ? "—" : String(player.tyreCompound)} />
              <Stat label="TYRE AGE" value={displayNumber(player?.tyreAge)} unit="LAPS" />
            </div>
            <div className="values-footer">
              <div className="driving-state"><span className="state-dot" /><span>{isNumber(player?.brake) && isNumber(player?.throttle) ? (player.brake ?? 0) >= 0.02 ? "BRAKING" : (player.throttle ?? 0) >= 0.98 ? "FULL THROTTLE" : (player.throttle ?? 0) > 0.02 ? "ACCELERATING" : "COASTING" : "AWAITING TELEMETRY"}</span></div>
              <div className="coach-action">
                <button
                  className="coach-button active-coach"
                  onClick={runCoachAnalysis}
                  disabled={coachLoading}
                  title="Run live AI telemetry analysis against the Ideal Ghost benchmark"
                >
                  <span className="coach-spark">✦</span> {coachLoading ? "ANALYSING TELEMETRY..." : "GEMINI AI COACH"}
                  <span className="coach-tag">IDEAL GHOST</span>
                </button>
                <span className="coach-note">{hasApiKey ? "● GEMINI 3.5 CONNECTED" : "○ TELEMETRY MODE · SET GEMINI KEY FOR LIVE RADIO"}</span>
              </div>
            </div>
          </article>
        </section>
      ) : (
        <LapComparePanel />
      )}

      <footer className="footer">
        <span>KREM <i>·</i> LIVE TELEMETRY</span>
        <span>PACKETS {displayNumber(stats?.packetsReceived)} <i>·</i> ACCEPTED {displayNumber(stats?.packetsAccepted)} <i>·</i> REJECTED {displayNumber(stats?.packetsRejected)}</span>
        <span>{lastMessageAt ? `UPDATED ${new Date(lastMessageAt).toLocaleTimeString()}` : "WAITING FOR DATA"}</span>
      </footer>

      {coachOpen && (
        <div className="coach-modal-backdrop" onClick={() => setCoachOpen(false)}>
          <div className="coach-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="coach-modal-header">
              <div>
                <span className="coach-eyebrow">✦ AI RACE ENGINEER</span>
                <h2>Ideal Ghost Telemetry Coach · {coachData?.track?.track_name || session?.trackName || "Circuit"}</h2>
                {coachData?.nextSector && (
                  <div className="coach-sector-pill">
                    FOCUS: <strong>SECTOR {coachData.nextSector}</strong> (BASED ON LAP {coachData.lapNum ?? "PREVIOUS"})
                  </div>
                )}
              </div>
              <button className="coach-close-btn" onClick={() => setCoachOpen(false)}>✕</button>
            </div>

            <div className="coach-modal-body">
              {!hasApiKey && (
                <div className="coach-key-banner">
                  <div className="coach-key-desc">
                    <strong>Enter Google Gemini API Key:</strong>
                    <span>Enables live race engineer advice powered by Gemini 3.5 Flash.</span>
                  </div>
                  <div className="coach-key-inputs">
                    <input
                      type="password"
                      placeholder="AIzaSy..."
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                    />
                    <button onClick={saveApiKey}>Connect API Key</button>
                  </div>
                  {keySaveMsg && <div className="key-msg">{keySaveMsg}</div>}
                </div>
              )}

              {coachLoading ? (
                <div className="coach-spinner-box">
                  <span className="coach-spinner" />
                  <p>Comparing your telemetry against the Ideal Ghost benchmark...</p>
                </div>
              ) : coachData ? (
                <div className="coach-results">
                  <div className="coach-report-box">
                    <div className="briefing-header">
                      <h3>RACE ENGINEER RADIO · SECTOR {coachData.nextSector ?? 1} TARGET</h3>
                      <span className="last-lap-tag">LAST COMPLETED LAP {coachData.lapNum ? `(#${coachData.lapNum})` : ""}</span>
                    </div>
                    <div className="coach-corner-advice-container">
                      {parseCornerAdvice(coachData.advice).map((item, idx) => (
                        <div key={idx} className={`coach-corner-advice-row ${item.isTurn ? "is-turn" : "is-tip"}`}>
                          <span className={`coach-corner-pill ${item.isTurn ? "pill-turn" : "pill-tip"}`}>{item.turnTag}:</span>
                          <span className="coach-corner-advice-body">{item.advice}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Tile format comparing Ghost Benchmark vs Player - always before Circuit Map */}
                  {displayDeltas.length > 0 && (
                    <div className="coach-deltas-section">
                      <h3>SECTOR {coachData.nextSector ?? 1} CORNER DELTAS VS IDEAL GHOST</h3>
                      <div className="deltas-grid">
                        {displayDeltas.slice(0, 8).map((delta) => {
                          const isLoss = delta.time_loss_s > 0.05;
                          return (
                            <div key={delta.turn} className={`delta-card ${isLoss ? "loss-high" : ""}`}>
                              <div className="delta-card-top">
                                <span className="delta-turn">T{delta.turn} {delta.name}</span>
                                <span className={`delta-loss-badge ${isLoss ? "badge-red" : "badge-green"}`}>
                                  {delta.time_loss_s > 0 ? `+${delta.time_loss_s.toFixed(2)}s` : "ON PACE"}
                                </span>
                              </div>
                              <div className="delta-diag">{delta.diagnosis || "Clean execution on ideal line"}</div>
                              <div className="delta-stats">
                                <div><span>Ghost Apex:</span> <b>{delta.ideal_apex_speed_kph} km/h (G{delta.ideal_apex_gear})</b></div>
                                {delta.player_min_speed_kph > 0 ? (
                                  <div><span>Your Apex:</span> <b>{delta.player_min_speed_kph} km/h</b></div>
                                ) : null}
                                {isNumber(delta.brake_delta_m) ? (
                                  <div><span>Braking:</span> <b>{delta.brake_delta_m! > 0 ? `${Math.round(delta.brake_delta_m!)}m early` : `${Math.abs(Math.round(delta.brake_delta_m!))}m late`}</b></div>
                                ) : delta.ideal_brake_m > 0 ? (
                                  <div><span>Ghost Brake:</span> <b>{Math.round(delta.ideal_brake_m)}m before apex</b></div>
                                ) : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Circuit Map at the bottom */}
                  <CoachMiniMap
                    trackOutline={trackOutline}
                    circuit={coachData.circuit}
                    trackBenchmark={coachData.track}
                    nextSector={coachData.nextSector ?? 1}
                    deltas={coachData.deltas}
                    allDeltas={coachData.allDeltas}
                    advice={coachData.advice}
                  />
                </div>
              ) : (
                <p>Click "Run Coach" to evaluate your telemetry.</p>
              )}
            </div>
          </div>
        </div>
      )}

    </main>
  );
}

export default App;
