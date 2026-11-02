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

interface TelemetrySnapshot {
  stats?: Stats;
  session?: Session;
  player?: Player;
  cars?: Car[];
  events?: Array<string | TelemetryEvent>;
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

const HISTORY_LIMIT = 360;
const MAP_HISTORY_LIMIT = 700;

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

function TrackMap({ cars, history, player }: { cars: Car[]; history: Position[]; player?: Player }) {
  const bounds = useMemo(() => {
    const points = [
      ...history,
      ...cars
        .filter((car) => isNumber(car.worldX) && isNumber(car.worldZ))
        .map((car) => ({ x: car.worldX!, z: car.worldZ! })),
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
      y: height - offsetY - (point.z - minZ + padZ) * scale,
    });
    return { project };
  }, [cars, history]);

  const path = bounds && history.length > 1
    ? history.map((point) => {
      const projected = bounds.project(point);
      return `${projected.x.toFixed(1)},${projected.y.toFixed(1)}`;
    }).join(" ")
    : "";
  const hasTrack = history.length > 5;

  return (
    <div className="map-wrap">
      <svg className="track-map" viewBox="0 0 1000 560" role="img" aria-label="Live track map from car world positions">
        <defs>
          <pattern id="map-grid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M 50 0 L 0 0 0 50" fill="none" stroke="currentColor" strokeOpacity=".055" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="1000" height="560" fill="url(#map-grid)" />
        {hasTrack && path && <polyline points={path} className="track-shadow" />}
        {hasTrack && path && <polyline points={path} className="track-line" />}
        {cars.map((car, index) => {
          if (!bounds || !isNumber(car.worldX) || !isNumber(car.worldZ)) return null;
          const point = bounds.project({ x: car.worldX, z: car.worldZ });
          const isPlayer = Boolean(car.isPlayer) || (isNumber(player?.position) && car.position === player.position);
          const heading = isNumber(car.heading) ? car.heading : 0;
          const forwardX = Math.sin(heading);
          const forwardZ = Math.cos(heading);
          const magnitude = Math.hypot(forwardX, forwardZ) || 1;
          const arrowScale = isPlayer ? 17 : 10;
          const tip = {
            x: point.x + (forwardX / magnitude) * arrowScale,
            y: point.y - (forwardZ / magnitude) * arrowScale,
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
            <text x="500" y="350">WORLD POSITION TRACE</text>
            <text x="500" y="375">Track line builds as telemetry arrives</text>
          </g>
        )}
      </svg>
      <div className="map-scale"><span className="map-legend-dot" /> LIVE CARS <span className="map-legend-line" /> POSITION TRACE</div>
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

function App() {
  const { snapshot, state, lastMessageAt } = useTelemetry();
  const [plot, setPlot] = useState<PlotPoint[]>([]);
  const [mapHistory, setMapHistory] = useState<Position[]>([]);
  const [lightTheme, setLightTheme] = useState(false);
  const [now, setNow] = useState(Date.now());
  const lastSample = useRef<string>("");
  const player = snapshot?.player;
  const session = snapshot?.session;
  const stats = snapshot?.stats;
  const cars = Array.isArray(snapshot?.cars) ? snapshot.cars : [];

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

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

      <section className="dashboard-grid">
        <article className="panel panel-map">
          <PanelHeading eyebrow="01 / TRACK POSITION" title={session?.trackName || "Live track map"} trailing={<span className="panel-chip">{cars.length ? `${cars.length} CARS` : "NO CARS"}</span>} />
          <div className="map-meta">
            <span>{displayNumber(session?.trackLength)} <small>M TRACK</small></span>
            <span>{distance === null ? "—" : `${Math.max(0, distance).toFixed(0)} m`} <small>LAP DISTANCE</small></span>
            <span>{displayNumber(player?.speed)} <small>KM/H</small></span>
          </div>
          <TrackMap cars={cars} history={mapHistory} player={player} />
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
              <button className="coach-button" disabled title="Coming soon — Google AI Studio Gemini coaching will run server-side">
                <span className="coach-spark">✦</span> GEMINI COACH <span className="coming-soon">COMING SOON</span>
              </button>
              <span className="coach-note">GOOGLE AI STUDIO · SERVER-SIDE ONLY · NO BROWSER KEY</span>
            </div>
          </div>
        </article>
      </section>
      <footer className="footer">
        <span>KREM <i>·</i> LIVE TELEMETRY</span>
        <span>PACKETS {displayNumber(stats?.packetsReceived)} <i>·</i> ACCEPTED {displayNumber(stats?.packetsAccepted)} <i>·</i> REJECTED {displayNumber(stats?.packetsRejected)}</span>
        <span>{lastMessageAt ? `UPDATED ${new Date(lastMessageAt).toLocaleTimeString()}` : "WAITING FOR DATA"}</span>
      </footer>
    </main>
  );
}

export default App;
