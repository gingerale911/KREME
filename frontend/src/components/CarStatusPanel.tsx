import "./CarStatusPanel.css";

type Reading = number | null | undefined;
type Availability = "fresh" | "stale" | "missing" | "offline" | "paused";
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
// Even small non-zero damage must be visibly different from an intact part.
const damageColor = (v: Reading, tyre = false) => {
  if (!finite(v)) return "#728091";
  const damage = Math.min(100, Math.max(0, v));

  const hue = damage >= 100 ? 0 : tyre ? (damage < 50 ? 120 : damage < 75 ? 55 : 28) : (damage < 2 ? 120 : damage < 50 ? 55 : 28);
  return `hsl(${hue} 78% 58%)`;
};

function CarDiagram({ damage, wheelValues }: { damage: Partial<Record<DamageKey, Reading>>; wheelValues: Reading[] }) {
  return <svg className="cs-car" viewBox="0 0 300 460" role="img" aria-label="Top-down car, front at top; independently coloured damage components">
    <g stroke="#647181" strokeWidth="2" fill="none">
      <path d="M72 133 L142 166 M228 133 L158 166 M72 155 L138 183 M228 155 L162 183 M72 350 L137 324 M228 350 L163 324 M72 365 L133 352 M228 365 L167 352" />
    </g>
    {PARTS.map(part => <path key={part.key} d={part.path} data-part={part.key} fill={damageColor(damage[part.key])} fillOpacity="0.65" stroke={damageColor(damage[part.key])} strokeWidth="3" strokeLinejoin="round"><title>{`${part.label}: ${format(damage[part.key], "% damage")}`}</title></path>)}
    <g fill="#18232d" stroke="#8192a4" strokeWidth="2">
      <path d="M147 42 Q150 34 153 42 L158 103 L169 146 L167 183 L177 207 L172 239 L163 255 L162 324 L157 381 L143 381 L138 324 L137 255 L128 239 L123 207 L133 183 L131 146 L142 103 Z" />
      <path d="M139 127 L161 127 L170 161 L163 201 L137 201 L130 161 Z" fill="#253440" />
      <path d="M138 210 Q150 188 162 210 L163 248 Q150 262 137 248 Z" fill="#090e15" />
      <ellipse cx="150" cy="219" rx="10" ry="17" fill="#1a2630" stroke="#9dacba" />
      <path d="M150 42 L150 183 M132 161 L168 161 M135 272 L165 272 M138 290 L162 290 M143 320 L157 320" stroke="#9dacba" strokeWidth="1.3" fill="none" />
    </g>
    {WHEELS.map((wheel, i) => <rect key={wheel.label} data-tyre={wheel.label} x={wheel.x} y={wheel.y} width="36" height="60" rx="7" fill={damageColor(wheelValues[i], true)} fillOpacity="0.8" stroke={damageColor(wheelValues[i], true)} strokeWidth="2.5"><title>{`${wheel.label}: ${format(wheelValues[i], "% damage")}`}</title></rect>)}
    <g stroke="#647181" strokeWidth="1.5" fill="none"><path d="M117 408 L117 429 M137 408 L137 429 M163 408 L163 429 M183 408 L183 429" /></g>
  </svg>;
}

export default function CarStatusPanel({ player, freshness, online, retained = false, paused = false }: {
  player?: CarStatusPlayer; freshness?: Record<string, Freshness>; online: boolean; retained?: boolean; paused?: boolean;
}) {
  const status = (source: string): Availability => !online ? "offline" : paused && freshness?.[source]?.state !== "missing" ? "paused" : freshness?.[source]?.state ?? "missing";
  const telemetryState = status("telemetry");
  const damageState = status("damage");
  const tyres = player?.tyres;
  const reading = (value: Reading, source: Availability) => (source === "fresh" || retained) && finite(value) ? value : null;
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
    <div className="cs-heading"><span>NUM {player?.driverNumber ?? "—"}</span><span className={`cs-availability cs-${telemetryState === "fresh" && damageState === "fresh" ? "fresh" : telemetryState === "offline" && damageState === "offline" ? "offline" : "stale"}`}>{paused ? "PAUSED" : !online ? "DISCONNECTED · RETAINED" : retained ? "STALE · RETAINED" : telemetryState === "fresh" && damageState === "fresh" ? "LIVE" : "PARTIAL / STALE"}</span></div>
    <div className="cs-stage cs-stage-all">
      <span className="cs-front">↑ FRONT</span>
      <CarDiagram damage={damage} wheelValues={wheelValues.map(w => w.damage)} />
      {WHEELS.map((wheel, i) => <div key={wheel.label} className={`cs-tyre-gauge cs-gauge-${wheel.label.toLowerCase()}`} style={{ borderColor: damageColor(wheelValues[i].wear, true) }} title={`${wheel.label}: ${format(wheelValues[i].wear, "% wear")} · ${format(wheelValues[i].damage, "% physical damage")}`}><small>{wheel.label}</small><strong>{format(finite(wheelValues[i].wear) ? 100 - Math.min(100, Math.max(0, wheelValues[i].wear!)) : null, "%")}</strong><small>HEALTH</small></div>)}
    </div>
    <div className="cs-sources" role="status"><span>TELEMETRY <b className={`cs-${telemetryState}`}>{telemetryState.toUpperCase()}</b></span><span>DAMAGE <b className={`cs-${damageState}`}>{damageState.toUpperCase()}</b></span></div>
    <div className="cs-caption">ALL TYRE METRICS · Wear and damage in % · temperatures in °C · pressure in psi</div>
    <div className="cs-legend">Wings: 0–1 green · 2–49 yellow · 50–99 orange · 100 red<br />Tyres: 0–49 green · 50–74 yellow · 75–99 orange · 100 red</div>
    <div className="cs-note">Circles: remaining tyre health (100 − wear). Car: physical damage. Grey: unavailable.</div>
  </div>;
}
