import "./CarStatusPanel.css";

type Reading = number | null | undefined;
type Availability = "fresh" | "stale" | "missing" | "offline";
interface Freshness { state: "missing" | "fresh" | "stale"; ageSeconds: number | null }
interface CarStatusPlayer {
  driverNumber?: Reading;
  tyres?: {
    wearPct?: Reading[] | null; damagePct?: Reading[] | null;
    surfaceTempC?: Reading[] | null; innerTempC?: Reading[] | null;
    brakeTempC?: Reading[] | null; pressurePsi?: Reading[] | null;
  };
  damage?: Partial<Record<DamageKey, Reading>>;
}
type DamageKey = "frontLeftWingDamage" | "frontRightWingDamage" | "rearWingDamage" | "floorDamage" | "diffuserDamage" | "sidepodDamage";
const PARTS: { key: DamageKey; label: string; path: string }[] = [
  { key: "floorDamage", label: "Floor", path: "M83 188 L217 188 L229 349 L205 380 L95 380 L71 349 Z" },
  { key: "frontLeftWingDamage", label: "Front left wing", path: "M144 48 L126 42 L57 62 L57 91 L131 79 L144 72 Z" },
  { key: "frontRightWingDamage", label: "Front right wing", path: "M156 48 L174 42 L243 62 L243 91 L169 79 L156 72 Z" },
  { key: "sidepodDamage", label: "Sidepods (shared reading)", path: "M116 206 L91 218 L84 300 L109 333 L126 294 Z M184 206 L209 218 L216 300 L191 333 L174 294 Z" },
  { key: "diffuserDamage", label: "Diffuser", path: "M106 365 L194 365 L205 393 L95 393 Z" },
  { key: "rearWingDamage", label: "Rear wing", path: "M78 404 L222 404 L222 433 L78 433 Z" },
];
// F1 packet order is RL, RR, FL, FR; the drawing faces upward.
const WHEELS = [
  { label: "FL", index: 2, x: 53, y: 111 },
  { label: "FR", index: 3, x: 211, y: 111 },
  { label: "RL", index: 0, x: 53, y: 327 },
  { label: "RR", index: 1, x: 211, y: 327 },
];
const finite = (v: Reading): v is number => typeof v === "number" && Number.isFinite(v);
const format = (v: Reading, unit: string, digits = 0) => finite(v) ? `${v.toFixed(digits)}${unit}` : "—";
const damageColor = (v: Reading) => finite(v) ? `hsl(${120 * (1 - Math.min(100, Math.max(0, v)) / 100)} 78% 58%)` : "#728091";

function WheelReading({ label, values, telemetryAvailability, damageAvailability }: {
  label: string;
  values: { wear: Reading; damage: Reading; surface: Reading; inner: Reading; brake: Reading; pressure: Reading };
  telemetryAvailability: Availability;
  damageAvailability: Availability;
}) {
  return <div className={`cs-wheel cs-wheel-${label.toLowerCase()}`}>
    <div className="cs-wheel-heading"><strong>{label}</strong><span className={`cs-mini-status cs-${damageAvailability}`}>{damageAvailability === "fresh" ? "LIVE" : damageAvailability.toUpperCase()}</span></div>
    <div className="cs-wheel-metrics">
      <div><span>WEAR</span><b style={{ color: damageColor(values.wear) }}>{format(values.wear, "%")}</b></div>
      <div><span>DAMAGE</span><b style={{ color: damageColor(values.damage) }}>{format(values.damage, "%")}</b></div>
      <div><span>SURFACE</span><b>{format(values.surface, "°C")}</b></div>
      <div><span>INNER</span><b>{format(values.inner, "°C")}</b></div>
      <div><span>PRESSURE</span><b>{format(values.pressure, " psi", 1)}</b></div>
      <div><span>BRAKE</span><b>{format(values.brake, "°C")}</b></div>
    </div>
    {telemetryAvailability !== "fresh" && <small className="cs-wheel-stale">TELEMETRY {telemetryAvailability.toUpperCase()}</small>}
  </div>;
}

function CarDiagram({ damage, wheelValues }: { damage: Partial<Record<DamageKey, Reading>>; wheelValues: Reading[] }) {
  return <svg className="cs-car" viewBox="0 0 300 460" role="img" aria-label="Top-down car, front at top; independently coloured damage components">
    <g stroke="#647181" strokeWidth="2" fill="none">
      <path d="M72 133 L142 166 M228 133 L158 166 M72 155 L138 183 M228 155 L162 183 M72 350 L137 324 M228 350 L163 324 M72 365 L133 352 M228 365 L167 352" />
    </g>
    {PARTS.map(part => <path key={part.key} d={part.path} data-part={part.key} fill={damageColor(damage[part.key])} fillOpacity="0.13" stroke={damageColor(damage[part.key])} strokeWidth="2.4" strokeLinejoin="round"><title>{`${part.label}: ${format(damage[part.key], "% damage")}`}</title></path>)}
    <g fill="#18232d" stroke="#8192a4" strokeWidth="2">
      <path d="M143 45 Q150 31 157 45 L163 186 L177 222 L171 280 L160 319 L157 377 L143 377 L140 319 L129 280 L123 222 L137 186 Z" />
      <ellipse cx="150" cy="222" rx="16" ry="29" fill="#0b1119" />
      <path d="M130 217 Q150 188 170 217 M150 198 L150 230 M140 286 L150 314 L160 286" fill="none" />
    </g>
    {WHEELS.map((wheel, i) => <rect key={wheel.label} data-tyre={wheel.label} x={wheel.x} y={wheel.y} width="36" height="60" rx="7" fill={damageColor(wheelValues[i])} fillOpacity="0.14" stroke={damageColor(wheelValues[i])} strokeWidth="2.5"><title>{`${wheel.label} tyre`}</title></rect>)}
    <g stroke="#647181" strokeWidth="1.5" fill="none"><path d="M117 408 L117 429 M137 408 L137 429 M163 408 L163 429 M183 408 L183 429" /></g>
  </svg>;
}

export default function CarStatusPanel({ player, freshness, online }: {
  player?: CarStatusPlayer; freshness?: Record<string, Freshness>; online: boolean;
}) {
  const status = (source: string): Availability => !online ? "offline" : freshness?.[source]?.state ?? "missing";
  const telemetryState = status("telemetry");
  const damageState = status("damage");
  const tyres = player?.tyres;
  const reading = (value: Reading, source: Availability) => source === "fresh" && finite(value) ? value : null;
  const damage = Object.fromEntries(PARTS.map(p => [p.key, reading(player?.damage?.[p.key], damageState)]));
  const wheelValues = WHEELS.map(wheel => ({
    wear: reading(tyres?.wearPct?.[wheel.index], damageState),
    damage: reading(tyres?.damagePct?.[wheel.index], damageState),
    surface: reading(tyres?.surfaceTempC?.[wheel.index], telemetryState),
    inner: reading(tyres?.innerTempC?.[wheel.index], telemetryState),
    brake: reading(tyres?.brakeTempC?.[wheel.index], telemetryState),
    pressure: reading(tyres?.pressurePsi?.[wheel.index], telemetryState),
  }));
  return <div className="cs-panel">
    <div className="cs-heading"><span>NUM {online ? player?.driverNumber ?? "—" : "—"}</span><span className={`cs-availability cs-${telemetryState === "fresh" && damageState === "fresh" ? "fresh" : telemetryState === "offline" && damageState === "offline" ? "offline" : "stale"}`}>{telemetryState === "fresh" && damageState === "fresh" ? "LIVE" : "PARTIAL / STALE"}</span></div>
    <div className="cs-stage cs-stage-all">
      <span className="cs-front">↑ FRONT</span>
      <CarDiagram damage={damage} wheelValues={wheelValues.map(w => w.wear)} />
      {WHEELS.map((wheel, i) => <WheelReading key={wheel.label} label={wheel.label} values={wheelValues[i]} telemetryAvailability={telemetryState} damageAvailability={damageState} />)}
    </div>
    <div className="cs-sources" role="status"><span>TELEMETRY <b className={`cs-${telemetryState}`}>{telemetryState.toUpperCase()}</b></span><span>DAMAGE <b className={`cs-${damageState}`}>{damageState.toUpperCase()}</b></span></div>
    <div className="cs-caption">ALL TYRE METRICS · Wear and damage in % · temperatures in °C · pressure in psi</div>
    <div className="cs-legend"><span><i style={{ background: "#73e747" }} />0%</span><span><i style={{ background: "#e7cb47" }} />50%</span><span><i style={{ background: "#e74747" }} />100%</span><span><i style={{ background: "#728091" }} />No current data</span></div>
    <div className="cs-note">Tyre diagram colour represents wear. Individual readings remain visible in each tyre card.</div>
    <section className="cs-chassis-section">
      <div className="cs-chassis-heading"><strong>CHASSIS DAMAGE</strong><span>BODY COMPONENTS</span></div>
      <div className="cs-damage-list">{PARTS.map(part => <div key={part.key}><span>{part.label}</span><strong style={{ color: damageColor(damage[part.key]) }}>{format(damage[part.key], "%")}</strong></div>)}</div>
    </section>
  </div>;
}
