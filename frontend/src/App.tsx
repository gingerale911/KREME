import CarStatusPanel from "./components/CarStatusPanel";
import LapComparePanel from "./components/LapComparePanel";
import { useEffect, useMemo, useRef, useState } from "react";

type ConnectionState = "connecting" | "live" | "reconnecting";
type DashboardTab = "live" | "laps" | "coach" | "settings";
type CoachKeyState = "checking" | "connected" | "not-connected" | "unavailable";
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
      <div className="panel-title-group">
        <div className="panel-eyebrow">{eyebrow}</div>
        <h2>{title}</h2>
      </div>
      <div className="panel-heading-end">
        <span className="f1-stripe-marker" aria-hidden="true" />
        {trailing && <div className="panel-trailing">{trailing}</div>}
      </div>
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
            <path d={trackSurfacePath} fill="rgba(152, 163, 177, 0.035)" stroke="#657181" strokeWidth={1.1} />
            <path d={trackRacingLine} fill="none" stroke="#98A3B1" strokeWidth={1.2} strokeDasharray="4 4" opacity=".58" />
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
            <text x="500" y="375">{liveTracePoints.length ? "Live positions · trace building" : "Waiting for live car positions"}</text>
          </g>
        )}
      </svg>
      {(staticTrackAvailable || liveTracePoints.length > 1) && (
        <div className="map-scale">
          <span className="map-legend-dot" /> LIVE CARS
          <span className="map-legend-line" /> {staticTrackAvailable ? "STATIC OUTLINE" : "LEARNED TRACE"}
        </div>
      )}
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

function App() {
  const { snapshot, state, lastMessageAt } = useTelemetry();
  const [plot, setPlot] = useState<PlotPoint[]>([]);
  const [mapHistory, setMapHistory] = useState<Position[]>([]);
  const [trackCatalog, setTrackCatalog] = useState<Record<number, TrackOutline>>({});
  const [trackOutline, setTrackOutline] = useState<TrackOutline | null>(null);
  const [selectedLap, setSelectedLap] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<DashboardTab>("live");
  const [coachLoading, setCoachLoading] = useState(false);
  const [coachError, setCoachError] = useState("");
  const [coachData, setCoachData] = useState<CoachAnalysisResponse | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [keySaveMsg, setKeySaveMsg] = useState("");
  const [keySaving, setKeySaving] = useState(false);
  const [hasApiKey, setHasApiKey] = useState(false);
  const [coachKeyState, setCoachKeyState] = useState<CoachKeyState>("checking");
  const [coachKeyError, setCoachKeyError] = useState("");
  const [now, setNow] = useState(Date.now());
  const lastSample = useRef<string>("");
  const lastGameTime = useRef<number | null>(null);
  const traceGap = useRef(false);
  const socketConnected = state === "live" && lastMessageAt !== null && now - lastMessageAt < 2_000;

  useEffect(() => {
    fetch("/api/coach/status")
      .then(async (response) => {
        if (!response.ok) throw new Error(`Coach status unavailable (${response.status})`);
        return response.json() as Promise<{ hasApiKey?: unknown }>;
      })
      .then((data) => {
        if (typeof data.hasApiKey !== "boolean") throw new Error("Coach status response was invalid");
        setHasApiKey(data.hasApiKey);
        setCoachKeyState(data.hasApiKey ? "connected" : "not-connected");
      })
      .catch((error: unknown) => {
        setCoachKeyState("unavailable");
        setCoachKeyError(error instanceof Error ? error.message : "Coach key status request failed");
      });
  }, []);

  const saveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    setKeySaving(true);
    setKeySaveMsg("");
    try {
      const res = await fetch("/api/coach/key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: apiKeyInput.trim() }),
      });
      if (!res.ok) {
        let message = `Unable to save API key (${res.status})`;
        try {
          const body = await res.json() as { detail?: unknown };
          if (typeof body.detail === "string") message = body.detail;
        } catch {
          // Keep the status-based message when the server does not return JSON.
        }
        throw new Error(message);
      }
      setHasApiKey(true);
      setCoachKeyState("connected");
      setKeySaveMsg("API key saved on the server.");
      setApiKeyInput("");
    } catch (error) {
      setKeySaveMsg(error instanceof Error ? error.message : "Unable to save API key");
    } finally {
      setKeySaving(false);
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
    setCoachError("");
    setCoachData(null);
    try {
      const res = await fetch("/api/coach/analyse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trackId: session?.trackId,
          lapNum: isNumber(player?.lapNum) && player.lapNum > 1 ? player.lapNum - 1 : undefined,
        }),
      });
      const data = await res.json() as CoachAnalysisResponse & { detail?: unknown };
      if (!res.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : `Analysis failed (${res.status})`);
      }
      if (typeof data.advice !== "string") {
        throw new Error("The coach returned no analysis for the selected lap.");
      }
      setCoachData(data);
      if (typeof data.hasApiKey === "boolean") setHasApiKey(data.hasApiKey);
    } catch (error) {
      setCoachError(error instanceof Error ? error.message : "Analysis request failed");
    } finally {
      setCoachLoading(false);
    }
  };
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

  const pageCopy: Record<DashboardTab, { title: string; subtitle: string }> = {
    live: { title: "LIVE DASHBOARD", subtitle: "REAL-TIME VEHICLE TELEMETRY" },
    laps: { title: "LAP ANALYSIS", subtitle: "DISTANCE-ALIGNED COMPARISON" },
    coach: { title: "AI COACH", subtitle: "LAST COMPLETED LAP ANALYSIS" },
    settings: { title: "SETTINGS", subtitle: "CONNECTION HELP & DIAGNOSTICS" },
  };
  const navItems: { id: DashboardTab; label: string }[] = [
    { id: "live", label: "01 LIVE" },
    { id: "laps", label: "02 LAP ANALYSIS" },
    { id: "coach", label: "03 AI COACH" },
    { id: "settings", label: "04 SETTINGS" },
  ];
  const keyStatusLabel = coachKeyState === "checking"
    ? "CHECKING"
    : coachKeyState === "connected"
      ? "CONNECTED"
      : coachKeyState === "not-connected"
        ? "NOT CONFIGURED"
        : "STATUS UNAVAILABLE";
  const coachKeyPanel = (
    <section className={`coach-key-panel f1-panel ${hasApiKey ? "" : "coach-key-panel--warning"}`}>
      <div className="section-heading">
        <div>
          <span className="panel-eyebrow">SERVER-SIDE CREDENTIAL</span>
          <h2>AI coach key</h2>
        </div>
        <span className={`panel-chip ${hasApiKey ? "text-green" : ""}`}>{keyStatusLabel}</span>
      </div>
      {coachKeyState === "checking" ? (
        <p className="muted-copy">Checking the server-side key status…</p>
      ) : hasApiKey ? (
        <p className="muted-copy">A key is configured on the server. It is not stored in this browser.</p>
      ) : (
        <>
          <p className="muted-copy">
            {coachKeyState === "unavailable"
              ? `Key status could not be checked${coachKeyError ? `: ${coachKeyError}` : ""}. You can still submit a key to the server.`
              : "Add a Gemini API key to enable analysis. The key is sent only to the server and is not saved in browser storage."}
          </p>
          <label className="coach-key-label" htmlFor="coach-api-key">GEMINI API KEY</label>
          <div className="coach-key-inputs">
            <input
              id="coach-api-key"
              type="password"
              autoComplete="new-password"
              placeholder="Enter Gemini API key"
              value={apiKeyInput}
              onChange={(event) => setApiKeyInput(event.target.value)}
            />
            <button type="button" onClick={saveApiKey} disabled={keySaving || !apiKeyInput.trim()}>
              {keySaving ? "SAVING..." : "SAVE KEY"}
            </button>
          </div>
        </>
      )}
      {keySaveMsg && <p className={`key-msg ${hasApiKey ? "text-green" : "text-red"}`} role="status">{keySaveMsg}</p>}
    </section>
  );
  const chartState = connected ? "ROLLING" : feedLabel;
  const pageTrackLabel = session?.trackName || "WAITING FOR SESSION";
  const feedWarning = paused || feedLabel === "STALE" || feedLabel === "WAITING FOR UDP";
  const disconnectedFeed = feedLabel === "DISCONNECTED";

  return (
    <main className="dashboard">
      <header className={`app-header ${disconnectedFeed ? "app-header--disconnected" : ""}`}>
        <button className="brand" type="button" onClick={() => setActiveTab("live")} aria-label="K.R.E.M.E. dashboard home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span>K.R.E.M.E.<span className="brand-sub">TELEMETRY</span></span>
        </button>
        <div className="app-header-center">
          <span>{pageTrackLabel}</span>
          {isNumber(player?.position) && <span className="position-pill">P{player.position}</span>}
        </div>
        <div className={`connection-state ${connected ? "is-connected" : paused ? "is-paused" : feedWarning ? "is-warning" : ""}`}>
          <span className="connection-dot" />
          <span>{feedLabel}</span>
        </div>
      </header>

      <section className="connection-strip" aria-label="Telemetry connection diagnostics">
        <div className="connection-cell"><span>FEED</span><strong className={connected ? "text-green" : feedWarning ? "text-amber" : ""}>{feedLabel}</strong></div>
        <div className="connection-cell"><span>PACKETS / SEC</span><strong>{displayNumber(stats?.packetsPerSecond)}</strong></div>
        <div className="connection-cell"><span>FRAME GAPS</span><strong className={isNumber(stats?.frameGaps) && stats.frameGaps > 0 ? "text-amber" : ""}>{displayNumber(stats?.frameGaps)}</strong></div>
        <div className="connection-cell"><span>FORMAT</span><strong>F1 25 · 2025</strong></div>
        {eventText && <div className="connection-event"><span className="event-pulse" />{eventText}</div>}
      </section>

      <nav className="primary-nav" aria-label="Dashboard pages">
        {navItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={activeTab === item.id ? "nav-tab is-active" : "nav-tab"}
            aria-current={activeTab === item.id ? "page" : undefined}
            onClick={() => setActiveTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <section className="page-heading">
        <div>
          <span className="page-kicker">{pageTrackLabel}{isNumber(player?.position) ? ` · P${player.position}` : ""}</span>
          <h1>{pageCopy[activeTab].title}</h1>
          <p>{pageCopy[activeTab].subtitle}</p>
        </div>
        <span className={`page-state ${connected ? "text-green" : feedWarning ? "text-amber" : ""}`}>
          <i className="state-dot" />{feedLabel}
        </span>
      </section>

      <div className="page-content">
        {!connected && activeTab === "live" && (
          <div className={`connection-banner ${paused ? "connection-banner--paused" : ""}`} role="status">
            <span className="banner-icon">!</span>
            <div>
              <strong>{paused ? "Game paused · readings and traces frozen" : snapshot?.telemetrySample ? "Feed unavailable · showing retained readings" : "Waiting for F1 25 telemetry"}</strong>
              <span>{paused
                ? "Existing values and traces are retained until telemetry resumes."
                : snapshot?.telemetrySample
                  ? "Retained values are not live. New samples are added only when telemetry resumes."
                  : "Configure F1 25 to send UDP telemetry in format 2025 to port 20777."}</span>
            </div>
          </div>
        )}

        {activeTab === "live" && (
          <section className="live-grid">
            <article className="panel f1-panel panel-map">
              <PanelHeading eyebrow="01 / TRACK POSITION" title="Track position" trailing={<span className="panel-chip">{cars.length ? `${cars.length} CARS` : "NO LIVE CARS"}</span>} />
              <div className="map-meta">
                <span>{displayNumber(session?.trackLength)} <small>M TRACK</small></span>
                <span>{distance === null ? "—" : `${Math.max(0, distance).toFixed(0)} m`} <small>LAP DISTANCE</small></span>
                <span>{displayNumber(player?.speed)} <small>KM/H</small></span>
              </div>
              <TrackMap cars={cars} history={mapHistory} player={player} trackOutline={trackOutline} />
              <div className="panel-foot">
                <span><i className="legend-live" />LIVE CARS</span>
                <span>{trackOutline ? "STATIC TRACK OUTLINE" : mapHistory.length > 1 ? "LEARNED TRACE" : "NO TRACK GEOMETRY"}</span>
              </div>
            </article>

            <article className="panel f1-panel f1-panel--accent panel-timing">
              <PanelHeading eyebrow="02 / LAP DATA" title="Timing & sectors" trailing={isNumber(player?.lapNum) ? <span className="lap-badge">LAP {player.lapNum}</span> : undefined} />
              <div className="timing-main">
                <div className="timer-block">
                  <span className="eyebrow">CURRENT LAP</span>
                  <strong>{formatTime(player?.lapTime)}</strong>
                  <span className={`timer-status ${player?.invalid ? "text-red" : player?.invalid === false ? "text-green" : "text-amber"}`}>
                    {player?.invalid == null ? "VALIDITY UNKNOWN" : player.invalid ? "INVALID LAP" : "VALID LAP"}
                  </span>
                </div>
                <div className="position-large"><span>POSITION</span><strong>{isNumber(player?.position) ? `P${player.position}` : "—"}</strong></div>
              </div>
              <div className="sector-track" aria-label="Three sector timing">
                {[1, 2, 3].map((sector) => (
                  <div key={sector} className={`sector-segment ${currentSector === sector ? "sector-current" : ""}`}>
                    <span>S{sector}{currentSector === sector ? " · CURRENT" : ""}</span>
                    <strong>{formatTime(sector === 1 ? player?.sector1TimeMs : sector === 2 ? player?.sector2TimeMs : player?.sector3TimeMs)}</strong>
                  </div>
                ))}
              </div>
              <div className="timing-details">
                <div><span>LAP DISTANCE</span><strong>{distance === null ? "—" : `${Math.max(0, distance).toFixed(0)} m`}</strong></div>
                <div><span>RACE LAP COUNT</span><strong>{isNumber(player?.lapNum) && isNumber(session?.totalLaps) ? `${player.lapNum} / ${session.totalLaps}` : "—"}</strong></div>
                <div><span>TRACK / WEATHER</span><strong>{[session?.trackName, session?.weather].filter((value) => value != null && value !== "").join(" · ") || "—"}</strong></div>
                <div><span>TRACK / AIR TEMP</span><strong>{isNumber(session?.trackTemp) || isNumber(session?.airTemp) ? `${displayNumber(session?.trackTemp, 0, "°")} / ${displayNumber(session?.airTemp, 0, "°")}` : "—"}</strong></div>
              </div>
            </article>

            <article className="panel f1-panel panel-charts">
              <PanelHeading eyebrow="03 / DRIVER INPUT" title="Telemetry traces" trailing={<span className="window-label">{chartState} · {plot.length} SAMPLES</span>} />
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

            <article className="panel f1-panel panel-car-health">
              <PanelHeading eyebrow="04 / CHASSIS" title="Car health" trailing={<span className="panel-chip">TYRE & DAMAGE DATA</span>} />
              <CarStatusPanel player={player} freshness={snapshot?.freshness} online={socketConnected} retained={frozen} paused={paused} />
            </article>

            <article className="panel f1-panel panel-values">
              <PanelHeading eyebrow="05 / CAR TELEMETRY" title="Player values" />
              <div className="primary-readouts">
                <div className="speed-readout"><span>SPEED</span><strong>{displayNumber(player?.speed)}</strong><small>KM/H</small></div>
                <div className="gear-readout"><span>GEAR</span><strong>{displayNumber(player?.gear)}</strong></div>
                <div className="pedal-readout">
                  {([
                    { key: "throttle", label: "THROTTLE", value: player?.throttle },
                    { key: "brake", label: "BRAKE", value: player?.brake },
                  ] as const).map(({ key, label, value }) => (
                    <div className={`pedal-meter-row pedal-meter-row--${key}`} key={key}>
                      <div className="pedal-meter-label"><span>{label}</span><strong>{percent(value)}</strong></div>
                      <div className="pedal-meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={isNumber(value) ? Math.round(value * 100) : undefined}>
                        <span style={{ width: isNumber(value) ? `${Math.max(0, Math.min(100, value * 100))}%` : "0%" }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="values-grid">
                <Stat label="ENGINE RPM" value={isNumber(player?.rpm) ? player.rpm.toLocaleString() : "—"} />
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
                <div className="driving-state"><span className={`state-dot ${connected ? "" : "state-dot--inactive"}`} /><span>{connected && isNumber(player?.brake) && isNumber(player?.throttle) ? player.brake >= 0.02 ? "BRAKING" : player.throttle >= 0.98 ? "FULL THROTTLE" : player.throttle > 0.02 ? "ACCELERATING" : "COASTING" : "AWAITING TELEMETRY"}</span></div>
                <button className="coach-button" type="button" onClick={() => setActiveTab("coach")}>OPEN AI COACH <span aria-hidden="true">→</span></button>
              </div>
            </article>
          </section>
        )}

        {activeTab === "laps" && <LapComparePanel />}

        {activeTab === "coach" && (
          <section className="coach-layout">
            <div className="coach-results-column">
              {coachLoading ? (
                <div className="coach-state-block" role="status">Comparing telemetry with the ideal benchmark…</div>
              ) : coachError ? (
                <div className="coach-state-block coach-state-block--error" role="alert">{coachError}</div>
              ) : coachData ? (
                <div className="coach-results">
                  <section className="coach-report-box f1-panel f1-panel--accent">
                    <div className="coach-result-heading">
                      <div><span className="panel-eyebrow">ANALYSIS REPORT</span><h2>{coachData.track?.track_name || "Coach analysis"}</h2></div>
                      {isNumber(coachData.lapNum) && <span className="panel-chip">LAP {coachData.lapNum}</span>}
                    </div>
                    <div className="coach-result-meta">
                      <span><small>TRACK</small>{coachData.track?.track_name || "—"}</span>
                      <span><small>LAP</small>{isNumber(coachData.lapNum) ? coachData.lapNum : "—"}</span>
                      <span><small>TARGET SECTOR</small>{isNumber(coachData.nextSector) ? `S${coachData.nextSector}` : "—"}</span>
                    </div>
                    <div className="coach-advice">{coachData.advice}</div>
                  </section>
                  {coachData.deltas.length > 0 && (
                    <section className="coach-deltas-section">
                      <div className="section-heading"><div><span className="panel-eyebrow">CORNER BREAKDOWN</span><h2>Telemetry deltas</h2></div></div>
                      <div className="deltas-grid">
                        {coachData.deltas.map((delta) => {
                          const lossClass = delta.time_loss_s > 0 ? "badge-red" : "badge-green";
                          const lossLabel = delta.time_loss_s > 0
                            ? `+${delta.time_loss_s.toFixed(2)}s`
                            : delta.time_loss_s < 0
                              ? `${delta.time_loss_s.toFixed(2)}s`
                              : "ON PACE";
                          return (
                            <article className="delta-card f1-panel" key={`${delta.turn}-${delta.name}`}>
                              <div className="delta-card-top">
                                <span className="delta-turn">T{delta.turn} · {delta.name}</span>
                                <span className={`delta-loss-badge ${lossClass}`}>{lossLabel}</span>
                              </div>
                              <p className="delta-diag">{delta.diagnosis}</p>
                              <div className="delta-stats">
                                <div><span>IDEAL APEX</span><b>{delta.ideal_apex_speed_kph} km/h · G{delta.ideal_apex_gear}</b></div>
                                <div><span>PLAYER MIN SPEED</span><b>{delta.player_min_speed_kph} km/h</b></div>
                                {isNumber(delta.brake_delta_m) && <div><span>BRAKING DELTA</span><b>{delta.brake_delta_m > 0 ? `${Math.round(delta.brake_delta_m)} m early` : `${Math.abs(Math.round(delta.brake_delta_m))} m late`}</b></div>}
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  )}
                </div>
              ) : (
                <div className="coach-state-block">Run an analysis to see coaching feedback.</div>
              )}
            </div>
            <aside className="coach-controls">
              {coachKeyPanel}
              <section className="coach-action-panel f1-panel">
                <span className="panel-eyebrow">LAST COMPLETED LAP</span>
                <p className="muted-copy">Analysis uses the current track and most recently completed lap when available.</p>
                <button
                  className="primary-action"
                  type="button"
                  onClick={runCoachAnalysis}
                  disabled={coachLoading || !hasApiKey}
                >
                  {coachLoading ? "ANALYSING..." : "ANALYSE LAST COMPLETED LAP"}
                </button>
                {!hasApiKey && <small className="action-note">Configure the server-side key to run analysis.</small>}
              </section>
            </aside>
          </section>
        )}

        {activeTab === "settings" && (
          <section className="settings-grid">
            <article className="f1-panel f1-panel--accent settings-panel">
              <div className="section-heading"><div><span className="panel-eyebrow">CONNECTION GUIDE</span><h2>F1 25 telemetry setup</h2></div></div>
              <ol className="setup-list">
                <li><span>01</span><div><strong>Enable UDP telemetry</strong><p>In F1 25 telemetry settings, enable UDP telemetry.</p></div></li>
                <li><span>02</span><div><strong>Choose packet format 2025</strong><p>Set the game’s UDP packet format to <code>2025</code>.</p></div></li>
                <li><span>03</span><div><strong>Set destination port 20777</strong><p>Configure destination port <code>20777</code> in the game. This dashboard does not save UDP destination settings.</p></div></li>
                <li><span>04</span><div><strong>Open the local dashboard</strong><p>By default, K.R.E.M.E. is served at <code>http://localhost:8765</code>.</p></div></li>
              </ol>
            </article>
            <article className="f1-panel settings-panel">
              <div className="section-heading"><div><span className="panel-eyebrow">LIVE DIAGNOSTICS</span><h2>Feed status</h2></div><span className="panel-chip">{feedLabel}</span></div>
              <div className="diagnostic-grid">
                <Stat label="FEED STATE" value={feedLabel} />
                <Stat label="PACKETS / SEC" value={displayNumber(stats?.packetsPerSecond)} />
                <Stat label="PACKETS RECEIVED" value={displayNumber(stats?.packetsReceived)} />
                <Stat label="PACKETS ACCEPTED" value={displayNumber(stats?.packetsAccepted)} />
                <Stat label="PACKETS REJECTED" value={displayNumber(stats?.packetsRejected)} />
                <Stat label="FRAME GAPS" value={displayNumber(stats?.frameGaps)} />
                <Stat label="LAST BROWSER UPDATE" value={lastMessageAt ? new Date(lastMessageAt).toLocaleTimeString() : "—"} />
              </div>
              <p className="muted-copy">Unavailable diagnostics are shown as —. Paused and retained readings are not live updates.</p>
            </article>
            <div className="settings-key">{coachKeyPanel}</div>
            <article className="f1-panel settings-panel attribution-panel">
              <div className="section-heading"><div><span className="panel-eyebrow">PROJECT INFORMATION</span><h2>Attribution & independence</h2></div></div>
              <p>Track map data by <a href="https://github.com/shfonic/ShfonicDashTracks" target="_blank" rel="noreferrer"><strong>Shfonic Dash Track Maps</strong></a> (Richard Hawes and contributors), licensed under <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.</p>
              <p>K.R.E.M.E. is an independent project and is not affiliated with or endorsed by EA or Formula 1.</p>
            </article>
          </section>
        )}
      </div>

      <footer className="app-footer">
        <span>K.R.E.M.E. <i>·</i> F1 25 TELEMETRY</span>
        <span>RECEIVED {displayNumber(stats?.packetsReceived)} <i>·</i> ACCEPTED {displayNumber(stats?.packetsAccepted)} <i>·</i> REJECTED {displayNumber(stats?.packetsRejected)}</span>
        <span>{lastMessageAt ? `UPDATED ${new Date(lastMessageAt).toLocaleTimeString()}` : "WAITING FOR DATA"}</span>
      </footer>
    </main>
  );
}

export default App;
