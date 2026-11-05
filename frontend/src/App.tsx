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
  distance?: MaybeNumber;
  throttle?: MaybeNumber;
  brake?: MaybeNumber;
  speed?: MaybeNumber;
}

interface LapSummary {
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
  };
  lapNum?: number | null;
  lapTimeMs?: number;
  nextSector?: number;
  currentSector?: number;
  hasApiKey: boolean;
  deltas: CornerDeltaUI[];
  advice: string;
}

interface TelemetrySnapshot {
  stats?: Stats;
  session?: Session;
  player?: Player;
  cars?: Car[];
  events?: Array<string | TelemetryEvent>;
  laps?: LapSummary[];
  frameCount?: MaybeNumber;
}

interface PlotPoint {
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

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function safeAverage(values: Array<MaybeNumber>): number {
  const numbers = values.filter(isNumber);
  if (!numbers.length) return 0;
  return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
}

function ringStyle(value: number, danger = false): React.CSSProperties {
  const pct = clamp(value, 0, 100);
  const hue = danger ? 15 : 120 - (pct / 100) * 55;
  return {
    background: `conic-gradient(from 180deg, hsl(${hue} 100% 62%) ${pct}%, rgba(255,255,255,0.12) ${pct}% 100%)`,
  };
}

function RaceCarRig({ player }: { player?: Player }) {
  const tyres = player?.tyres ?? {};
  const tyreWear = tyres.wearPct ?? [0, 0, 0, 0];
  const tyrePressure = tyres.pressurePsi ?? [0, 0, 0, 0];
  const tyreTemp = tyres.surfaceTempC ?? [0, 0, 0, 0];
  const brakeTemp = tyres.brakeTempC ?? [0, 0, 0, 0];
  const wingDamage = {
    frontLeft: player?.damage?.frontLeftWingDamage ?? 0,
    frontRight: player?.damage?.frontRightWingDamage ?? 0,
    rear: player?.damage?.rearWingDamage ?? 0,
    floor: player?.damage?.floorDamage ?? 0,
    diffuser: player?.damage?.diffuserDamage ?? 0,
    sidepod: player?.damage?.sidepodDamage ?? 0,
  };
  const tyreHealth = clamp(100 - safeAverage(tyreWear), 0, 100);
  const wingHealth = clamp(100 - safeAverage(Object.values(wingDamage)), 0, 100);
  const tyreHeat = Math.max(safeAverage(tyreTemp), safeAverage(brakeTemp));
  const pressureAverage = safeAverage(tyrePressure);
  const wheelMeters = [
    { label: "FL", value: clamp(100 - (tyreWear[2] ?? 0), 0, 100), color: "#60f6a3" },
    { label: "FR", value: clamp(100 - (tyreWear[3] ?? 0), 0, 100), color: "#60f6a3" },
    { label: "RL", value: clamp(100 - (tyreWear[0] ?? 0), 0, 100), color: "#60f6a3" },
    { label: "RR", value: clamp(100 - (tyreWear[1] ?? 0), 0, 100), color: "#60f6a3" },
  ];

  return (
    <div className="car-health-card">
      <div className="car-header-strip">
        <span className="car-number">NUM {player?.driverNumber ?? 0}</span>
        <span className="car-status-pill">{wingHealth > 80 && tyreHealth > 70 ? "SYSTEM OK" : "CHECK"}</span>
      </div>
      <div className="car-rig-wrapper">
        {wheelMeters.map((wheel, index) => (
          <div key={`wheel-${wheel.label}`} className={`wheel-meter wheel-${index + 1}`}>
            <div className="ring" style={ringStyle(wheel.value, false)}>
              <span>{Math.round(wheel.value)}%</span>
            </div>
            <small>{wheel.label}</small>
          </div>
        ))}
        <svg className="race-car-svg" viewBox="0 0 720 260" role="img" aria-label="Race car health diagram">
          <defs>
            <linearGradient id="carBodyGlow" x1="0%" x2="100%" y1="0%" y2="0%">
              <stop offset="0%" stopColor="rgba(96, 246, 163, 0.85)" />
              <stop offset="100%" stopColor="rgba(93, 192, 255, 0.65)" />
            </linearGradient>
          </defs>
          <g className="car-silhouette">
            <path d="M85 155 L165 110 L285 120 L340 96 L470 100 L570 130 L655 150 L652 176 L620 184 L590 198 L532 192 L420 206 L320 206 L190 198 L126 180 L94 170 Z" fill="rgba(18, 28, 38, 0.9)" stroke="rgba(96,246,163,0.95)" strokeWidth="2" />
            <path d="M155 118 L180 100 L245 98 L270 109 L220 124 L155 118 Z" fill="rgba(96,246,163,0.12)" stroke="rgba(96,246,163,0.8)" strokeWidth="2" />
            <path d="M485 102 L548 108 L578 126 L542 145 L498 136 L470 123 Z" fill="rgba(146, 200, 255, 0.12)" stroke="rgba(96,246,163,0.7)" strokeWidth="2" />
            <path d="M215 118 L275 118 L283 174 L210 174 Z" fill="rgba(26, 44, 55, 0.85)" stroke="rgba(96,246,163,0.75)" strokeWidth="2" />
            <circle cx="185" cy="186" r="38" fill="rgba(12, 18, 22, 0.9)" stroke="rgba(96,246,163,0.85)" strokeWidth="2" />
            <circle cx="520" cy="186" r="38" fill="rgba(12, 18, 22, 0.9)" stroke="rgba(96,246,163,0.85)" strokeWidth="2" />
            <circle cx="58" cy="184" r="25" fill="rgba(12, 18, 22, 0.9)" stroke="rgba(96,246,163,0.85)" strokeWidth="2" />
            <circle cx="650" cy="184" r="25" fill="rgba(12, 18, 22, 0.9)" stroke="rgba(96,246,163,0.85)" strokeWidth="2" />
            <path d="M201 92 L220 60 L270 62 L282 100" fill="none" stroke="rgba(96,246,163,0.8)" strokeWidth="2" />
            <path d="M496 94 L520 60 L565 60 L581 108" fill="none" stroke="rgba(96,246,163,0.8)" strokeWidth="2" />
            <path d="M238 146 L247 188" stroke="rgba(96,246,163,0.75)" strokeWidth="2" />
            <path d="M490 146 L481 188" stroke="rgba(96,246,163,0.75)" strokeWidth="2" />
            <path d="M112 162 L136 146" stroke="rgba(96,246,163,0.6)" strokeWidth="2" />
            <path d="M590 162 L614 146" stroke="rgba(96,246,163,0.6)" strokeWidth="2" />
          </g>
        </svg>
      </div>
      <div className="car-metric-grid">
        <div className="car-metric"><span>TYRE</span><strong>{Math.round(tyreHealth)}%</strong></div>
        <div className="car-metric"><span>HEAT</span><strong>{Math.round(tyreHeat)}°C</strong></div>
        <div className="car-metric"><span>PRESS</span><strong>{pressureAverage > 0 ? `${pressureAverage.toFixed(1)} psi` : "—"}</strong></div>
        <div className="car-metric"><span>WING</span><strong>{Math.round(wingHealth)}%</strong></div>
      </div>
      <div className="wing-damage-grid">
        <div><span>FL wing</span><strong>{isNumber(player?.damage?.frontLeftWingDamage) ? `${Math.round(player.damage!.frontLeftWingDamage!)}%` : "—"}</strong></div>
        <div><span>FR wing</span><strong>{isNumber(player?.damage?.frontRightWingDamage) ? `${Math.round(player.damage!.frontRightWingDamage!)}%` : "—"}</strong></div>
        <div><span>Rear</span><strong>{isNumber(player?.damage?.rearWingDamage) ? `${Math.round(player.damage!.rearWingDamage!)}%` : "—"}</strong></div>
        <div><span>Floor</span><strong>{isNumber(player?.damage?.floorDamage) ? `${Math.round(player.damage!.floorDamage!)}%` : "—"}</strong></div>
      </div>
    </div>
  );
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
  const speedPath = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.speed).toFixed(1)}`).join(" ");
  const throttlePath = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.throttle * 100).toFixed(1)}`).join(" ");
  const brakePath = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.brake * 100).toFixed(1)}`).join(" ");
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

function LapComparisonGraph({
  selected,
  compareLaps,
  reference,
}: {
  selected: LapSummary | null;
  compareLaps: LapSummary[];
  reference: LapSummary | null;
}) {
  const width = 760;
  const height = 220;
  const padding = { top: 20, right: 20, bottom: 28, left: 34 };
  const selectedSamples = selected?.samples ?? [];
  const samplesToCompare = compareLaps
    .filter((lap) => Array.isArray(lap.samples) && lap.samples.length > 0)
    .slice(-8);

  const buildSeries = (samples: LapSample[], key: "throttle" | "brake") => {
    if (!samples.length) return "";
    const range = 100;
    const maxDistance = Math.max(...samples.map((sample) => Number(sample.distance ?? 0)), 1);
    return samples
      .map((sample) => {
        const x = padding.left + (Number(sample.distance ?? 0) / maxDistance) * (width - padding.left - padding.right);
        const y = padding.top + (1 - (Number(sample[key] ?? 0) / range)) * (height - padding.top - padding.bottom);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  };

  const selectedThrottle = buildSeries(selectedSamples, "throttle");
  const selectedBrake = buildSeries(selectedSamples, "brake");
  const compareThrottle = samplesToCompare.map((lap) => ({
    color: "series-reference",
    points: buildSeries(lap.samples ?? [], "throttle"),
  }));
  const compareBrake = samplesToCompare.map((lap) => ({
    color: "series-reference-brake",
    points: buildSeries(lap.samples ?? [], "brake"),
  }));
  const empty = !selectedThrottle && !selectedBrake && compareThrottle.every((lap) => !lap.points) && compareBrake.every((lap) => !lap.points);

  return (
    <svg className="lap-graph" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Throttle and brake comparison graph">
      {[0, 25, 50, 75, 100].map((value) => {
        const y = padding.top + (1 - value / 100) * (height - padding.top - padding.bottom);
        return (
          <g key={`grid-${value}`}>
            <line x1={padding.left} x2={width - padding.right} y1={y} y2={y} className="chart-grid" />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" className="chart-axis-label">{value}%</text>
          </g>
        );
      })}
      <line x1={padding.left} x2={width - padding.right} y1={height - padding.bottom} y2={height - padding.bottom} className="chart-grid" />
      <line x1={padding.left} x2={padding.left} y1={padding.top} y2={height - padding.bottom} className="chart-grid" />
      {compareThrottle.map((lap, index) => lap.points && <polyline key={`compare-throttle-${index}`} points={lap.points} className={lap.color} />)}
      {compareBrake.map((lap, index) => lap.points && <polyline key={`compare-brake-${index}`} points={lap.points} className={lap.color} />)}
      {selectedThrottle && <polyline points={selectedThrottle} className="series-throttle" />}
      {selectedBrake && <polyline points={selectedBrake} className="series-brake" />}
      {reference?.samples?.length && <polyline points={buildSeries(reference.samples, "throttle")} className="series-reference" />}
      {reference?.samples?.length && <polyline points={buildSeries(reference.samples, "brake")} className="series-reference-brake" />}
      {empty && <text x={width / 2} y={height / 2} textAnchor="middle" className="chart-empty">NO SAMPLE TRACE AVAILABLE</text>}
      <text x={padding.left} y={height - 4} className="chart-axis-label">DISTANCE</text>
      <text x={width - padding.right} y={height - 4} textAnchor="end" className="chart-axis-label">0→100%</text>
      <text x={width / 2} y={12} textAnchor="middle" className="chart-axis-label">THROTTLE / BRAKE COMPARISON</text>
    </svg>
  );
}

function App() {
  const { snapshot, state, lastMessageAt } = useTelemetry();
  const [plot, setPlot] = useState<PlotPoint[]>([]);
  const [mapHistory, setMapHistory] = useState<Position[]>([]);
  const [trackCatalog, setTrackCatalog] = useState<Record<number, TrackOutline>>({});
  const [trackOutline, setTrackOutline] = useState<TrackOutline | null>(null);
  const [lightTheme, setLightTheme] = useState(false);
  const [storedLaps, setStoredLaps] = useState<LapSummary[]>([]);
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
  const sessionIdRef = useRef<number | undefined>(undefined);
  const lapNumberRef = useRef<number | null>(null);
  
  useEffect(() => {
    fetch("/api/coach/status")
      .then((r) => r.json())
      .then((d) => setHasApiKey(Boolean(d.hasApiKey)))
      .catch(() => {});
  }, []);

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

  const player = snapshot?.player;
  const session = snapshot?.session;
  const stats = snapshot?.stats;
  const cars = Array.isArray(snapshot?.cars) ? snapshot.cars : [];
  const lapHistory = Array.isArray(snapshot?.laps) && snapshot.laps.length > 0 ? snapshot.laps : storedLaps;

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.sessionStorage.getItem("krem-lap-history");
      if (!saved) return;
      const parsed = JSON.parse(saved) as LapSummary[];
      if (Array.isArray(parsed)) {
        setStoredLaps(parsed);
      }
    } catch {
      // Ignore malformed cached lap data; the live feed will rebuild it.
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !Array.isArray(snapshot?.laps) || snapshot.laps.length === 0) return;
    setStoredLaps((current) => {
      const merged = [...current, ...snapshot.laps!];
      const unique = new Map<number, LapSummary>();
      for (const lap of merged) {
        const key = Number(lap.lap ?? -1);
        if (key < 0) continue;
        unique.set(key, lap);
      }
      const next = Array.from(unique.values()).slice(-10);
      window.sessionStorage.setItem("krem-lap-history", JSON.stringify(next));
      return next;
    });
  }, [snapshot?.laps]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const currentSessionId = snapshot?.session?.uid;
    if (currentSessionId !== undefined && currentSessionId !== null) {
      const previousSessionId = sessionIdRef.current;
      if (previousSessionId !== undefined && previousSessionId !== currentSessionId) {
        setStoredLaps([]);
        setSelectedLap(null);
        window.sessionStorage.removeItem("krem-lap-history");
      }
      sessionIdRef.current = currentSessionId;
    }
  }, [snapshot?.session?.uid]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const currentLapNum = isNumber(player?.lapNum) ? player.lapNum : null;
    if (currentLapNum !== null && lapNumberRef.current !== null && currentLapNum < lapNumberRef.current) {
      setStoredLaps([]);
      setSelectedLap(null);
      window.sessionStorage.removeItem("krem-lap-history");
    }
    lapNumberRef.current = currentLapNum;
  }, [player?.lapNum]);

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
          const response = await fetch(`/track_data/${fileName}`);
          if (!response.ok) continue;
          const data = await response.json() as {
            left_edge?: [number, number][];
            right_edge?: [number, number][];
            lines?: { formula1?: { racing_line?: [number, number][] } };
            orientation?: number;
          };

          const leftEdge = (data.left_edge ?? []).map(([x, z]) => ({ x, z }));
          const rightEdge = (data.right_edge ?? []).map(([x, z]) => ({ x, z }));
          const racingLine = (data.lines?.formula1?.racing_line ?? []).map(([x, z]) => ({ x, z }));

          nextCatalog[Number(trackIdString)] = {
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
    const trackId = snapshot?.session?.trackId;
    if (trackId === undefined || trackId === null || trackId < 0) {
      setTrackOutline(null);
      return;
    }
    setTrackOutline(trackCatalog[trackId] ?? null);
  }, [snapshot?.session?.trackId, trackCatalog]);

  useEffect(() => {
    if (!player) return;
    const marker = `${snapshot?.frameCount ?? ""}:${player.lapDist ?? ""}:${player.speed ?? ""}:${lastMessageAt ?? ""}`;
    if (marker === lastSample.current) return;
    lastSample.current = marker;

    if (isNumber(player.speed) || isNumber(player.throttle) || isNumber(player.brake)) {
      const point: PlotPoint = {
        at: Date.now(),
        distance: isNumber(player.lapDist) ? player.lapDist : 0,
        speed: Math.max(0, player.speed ?? 0),
        throttle: Math.max(0, Math.min(1, player.throttle ?? 0)),
        brake: Math.max(0, Math.min(1, player.brake ?? 0)),
      };
      setPlot((current) => [...current.slice(-(HISTORY_LIMIT - 1)), point]);
    }

    const playerCar = cars.find((car) => car.isPlayer)
      ?? (isNumber(player.position) ? cars.find((car) => car.position === player.position) : undefined);
    if (playerCar && isNumber(playerCar.worldX) && isNumber(playerCar.worldZ)) {
      setMapHistory((current) => [
        ...current.slice(-(MAP_HISTORY_LIMIT - 1)),
        { x: playerCar.worldX!, z: playerCar.worldZ! },
      ]);
    }
  }, [snapshot, player, cars, lastMessageAt]);

  const latestEvent = snapshot?.events?.at(-1);
  const eventText = typeof latestEvent === "string"
    ? latestEvent
    : latestEvent?.code
      ? `${latestEvent.code}${isNumber(latestEvent.time) ? ` · ${latestEvent.time.toFixed(1)}s` : ""}`
      : undefined;
  const socketConnected = state === "live" && lastMessageAt !== null && now - lastMessageAt < 5_000;
  const connected = socketConnected && stats?.connected === true;
  const currentSector = isNumber(player?.sector) ? Math.min(3, Math.max(1, player.sector + 1)) : null;
  const distance = isNumber(player?.lapDist) ? player.lapDist : null;
  const latestLap = lapHistory.length > 0 ? lapHistory[lapHistory.length - 1] : null;
  const selectedLapSummary = lapHistory.find((lap) => Number(lap.lap ?? -1) === selectedLap)
    ?? latestLap ?? null;
  const allComparedLaps = lapHistory.filter((lap) => Number(lap.lap ?? -1) !== Number(selectedLapSummary?.lap ?? -1));
  const lapDeltaMs = latestLap && selectedLapSummary && isNumber(latestLap.lapTimeMs) && isNumber(selectedLapSummary.lapTimeMs)
    ? latestLap.lapTimeMs - selectedLapSummary.lapTimeMs
    : null;
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
            <span>{connected ? "LIVE DATA" : socketConnected ? "WAITING FOR UDP" : state === "connecting" ? "CONNECTING" : "RECONNECTING"}</span>
          </div>
        </div>
      </header>

      <div className="status-strip">
        <div className="status-item"><span className="status-label">FEED</span><strong className={connected ? "text-green" : "text-amber"}>{connected ? "RECEIVING" : socketConnected ? "WAITING FOR UDP" : "OFFLINE"}</strong></div>
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
            <strong>{socketConnected ? "Waiting for F1 25 telemetry" : "Dashboard connection unavailable"}</strong>
            <span>{socketConnected
              ? "KREM is connected. Configure F1 25 to send UDP telemetry using format 2025 to port 20777."
              : `Attempting to reconnect to ${socketAddress()}. Check that KREM is running.`}</span>
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
              <div><span>LAP INVALID</span><strong className={player?.invalid ? "text-red" : "text-green"}>{player?.invalid ? "YES" : player ? "NO" : "—"}</strong></div>
            </div>
            <div className="timing-session">
              <div><span>TRACK</span><strong>{session?.trackName || "—"}</strong></div>
              <div><span>WEATHER</span><strong>{session?.weather ?? "—"}</strong></div>
              <div><span>TRACK TEMP</span><strong>{displayNumber(session?.trackTemp, 0, "°")}</strong></div>
              <div><span>AIR TEMP</span><strong>{displayNumber(session?.airTemp, 0, "°")}</strong></div>
            </div>
          </article>

          <article className="panel panel-charts">
            <PanelHeading eyebrow="03 / DRIVER INPUT" title="Telemetry traces" trailing={<span className="window-label">ROLLING · {plot.length} SAMPLES</span>} />
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
            <RaceCarRig player={player} />
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
              <Stat label="DRS" value={player?.drs ? "OPEN" : player ? "CLOSED" : "—"} />
              <Stat label="DRS AVAILABLE" value={player ? (player.drsAllowed ? "YES" : "NO") : "—"} />
              <Stat label="ERS STORE" value={displayNumber(player?.ersStore, 2)} unit="MJ" />
              <Stat label="ERS MODE" value={displayNumber(player?.ersMode)} />
              <Stat label="FUEL" value={displayNumber(player?.fuel, 1)} unit="KG" />
              <Stat label="FUEL LAPS" value={displayNumber(player?.fuelLaps, 1)} />
              <Stat label="TYRE COMPOUND" value={player?.tyreCompound == null ? "—" : String(player.tyreCompound)} />
              <Stat label="TYRE AGE" value={displayNumber(player?.tyreAge)} unit="LAPS" />
            </div>
            <div className="values-footer">
              <div className="driving-state"><span className="state-dot" /><span>{player ? (player.brake ?? 0) >= 0.02 ? "BRAKING" : (player.throttle ?? 0) >= 0.98 ? "FULL THROTTLE" : (player.throttle ?? 0) > 0.02 ? "ACCELERATING" : "COASTING" : "AWAITING TELEMETRY"}</span></div>
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
        <section className="lap-tab-panel">
          <div className="lap-layout">
            <article className="panel lap-main-panel">
              <PanelHeading eyebrow="LAP ANALYSIS" title="Selected lap compare" trailing={<span className="panel-chip">{lapHistory.length} saved</span>} />
              <div className="lap-selection-bar">
                <label htmlFor="lap-select">Selected lap</label>
                <select id="lap-select" value={selectedLapSummary?.lap ?? ""} onChange={(event) => setSelectedLap(Number(event.target.value) || null)}>
                  {lapHistory.map((lap) => (
                    <option key={`lap-option-${lap.lap ?? "unknown"}`} value={Number(lap.lap ?? 0)}>
                      Lap {lap.lap ?? "—"}
                    </option>
                  ))}
                </select>
              </div>
              <div className="lap-compare-grid">
                <div className="lap-card lap-card-current">
                  <span className="lap-card-label">SELECTED</span>
                  <strong>Lap {selectedLapSummary?.lap ?? "—"}</strong>
                  <div className="lap-card-row"><span>TIME</span><b>{formatTime(selectedLapSummary?.lapTimeMs)}</b></div>
                  <div className="lap-card-row"><span>AVG SPEED</span><b>{displayNumber(selectedLapSummary?.avgSpeedKph, 1)} km/h</b></div>
                  <div className="lap-card-row"><span>TOP SPEED</span><b>{displayNumber(selectedLapSummary?.maxSpeedKph, 1)} km/h</b></div>
                </div>
                <div className="lap-card">
                  <span className="lap-card-label">BENCHMARK</span>
                  <strong>{latestLap ? `Lap ${latestLap.lap}` : "—"}</strong>
                  <div className="lap-card-row"><span>DIFF</span><b className={lapDeltaMs !== null && lapDeltaMs <= 0 ? "text-green" : "text-amber"}>{lapDeltaMs === null ? "—" : `${lapDeltaMs > 0 ? "+" : ""}${lapDeltaMs} ms`}</b></div>
                  <div className="lap-card-row"><span>AVG THROTTLE</span><b>{displayNumber(selectedLapSummary?.avgThrottle, 1, "%")}</b></div>
                  <div className="lap-card-row"><span>AVG BRAKE</span><b>{displayNumber(selectedLapSummary?.avgBrake, 1, "%")}</b></div>
                </div>
              </div>
              <div className="lap-table">
                <div className="lap-table-head">
                  <span>Lap</span>
                  <span>Time</span>
                  <span>Delta</span>
                  <span>Avg speed</span>
                </div>
                {allComparedLaps.length === 0 && <div className="lap-table-empty">No other laps to compare against the selected lap.</div>}
                {allComparedLaps.slice().reverse().map((lap) => {
                  const deltaMs = selectedLapSummary && isNumber(selectedLapSummary.lapTimeMs) && isNumber(lap.lapTimeMs)
                    ? lap.lapTimeMs - selectedLapSummary.lapTimeMs
                    : null;
                  return (
                    <div key={`lap-compare-${lap.lap ?? "unknown"}`} className="lap-table-row lap-table-row-clickable" onClick={() => setSelectedLap(Number(lap.lap ?? 0) || null)}>
                      <span>{lap.lap ?? "—"}</span>
                      <span>{formatTime(lap.lapTimeMs)}</span>
                      <span className={deltaMs !== null && deltaMs <= 0 ? "text-green" : "text-amber"}>{deltaMs === null ? "—" : `${deltaMs > 0 ? "+" : ""}${deltaMs} ms`}</span>
                      <span>{displayNumber(lap.avgSpeedKph, 1)} km/h</span>
                    </div>
                  );
                })}
              </div>
              <div className="session-store-note">Stored in browser session storage while the dashboard remains open.</div>
            </article>

            <article className="panel lap-graph-panel">
              <PanelHeading eyebrow="GRAPH" title="Throttle / brake trace" trailing={<span className="panel-chip">selected vs reference</span>} />
              <div className="lap-graph-meta">
                <span>Selected {selectedLapSummary ? `Lap ${selectedLapSummary.lap}` : "—"}</span>
                <span>Reference {latestLap ? `Lap ${latestLap.lap}` : "—"}</span>
              </div>
              <LapComparisonGraph selected={selectedLapSummary} compareLaps={allComparedLaps} reference={latestLap} />
              <div className="lap-summary-row">
                <div><span>Selected throttle</span><strong>{displayNumber(selectedLapSummary?.avgThrottle, 1, "%")}</strong></div>
                <div><span>Selected brake</span><strong>{displayNumber(selectedLapSummary?.avgBrake, 1, "%")}</strong></div>
                <div><span>Reference throttle</span><strong>{displayNumber(latestLap?.avgThrottle, 1, "%")}</strong></div>
                <div><span>Reference brake</span><strong>{displayNumber(latestLap?.avgBrake, 1, "%")}</strong></div>
              </div>
            </article>
          </div>
        </section>
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
                    <div className="coach-markdown-text">
                      {coachData.advice.split("\n").map((line, idx) => {
                        const trimmed = line.trim();
                        if (!trimmed) return <div key={idx} className="briefing-spacer" />;
                        if (trimmed.startsWith("###") || trimmed.startsWith("**SECTOR") || trimmed.startsWith("**NEXT")) {
                          return <h4 key={idx} className="briefing-subhead">{trimmed.replace(/^[#*]+/, "").replace(/[*]+$/, "")}</h4>;
                        }
                        if (trimmed.startsWith("-") || trimmed.startsWith("*") || /^[0-9]\./.test(trimmed)) {
                          return (
                            <div key={idx} className="briefing-bullet">
                              <span className="bullet-dot">▸</span>
                              <span>{trimmed.replace(/^[-*0-9.]+\s*/, "")}</span>
                            </div>
                          );
                        }
                        return <p key={idx}>{trimmed}</p>;
                      })}
                    </div>
                  </div>

                  {coachData.deltas && coachData.deltas.length > 0 && (
                    <div className="coach-deltas-section">
                      <h3>SECTOR {coachData.nextSector ?? 1} CORNER DELTAS VS IDEAL GHOST</h3>
                      <div className="deltas-grid">
                        {coachData.deltas.slice(0, 6).map((delta) => (
                          <div key={delta.turn} className={`delta-card ${delta.time_loss_s > 0.15 ? "loss-high" : ""}`}>
                            <div className="delta-card-top">
                              <span className="delta-turn">T{delta.turn} {delta.name}</span>
                              <span className={`delta-loss-badge ${delta.time_loss_s > 0.1 ? "badge-red" : "badge-green"}`}>
                                {delta.time_loss_s > 0 ? `+${delta.time_loss_s.toFixed(2)}s` : "ON PACE"}
                              </span>
                            </div>
                            <div className="delta-diag">{delta.diagnosis}</div>
                            <div className="delta-stats">
                              <div><span>Ghost Apex:</span> <b>{delta.ideal_apex_speed_kph} km/h (G{delta.ideal_apex_gear})</b></div>
                              <div><span>Your Apex:</span> <b>{delta.player_min_speed_kph} km/h</b></div>
                              {isNumber(delta.brake_delta_m) && (
                                <div><span>Braking:</span> <b>{delta.brake_delta_m! > 0 ? `${Math.round(delta.brake_delta_m!)}m early` : `${Math.abs(Math.round(delta.brake_delta_m!))}m late`}</b></div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
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
