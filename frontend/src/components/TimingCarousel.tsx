import { useMemo, useState } from "react";

export interface TimingCar {
  index?: number | null;
  name?: string | null;
  driverNumber?: string | number | null;
  position?: number | null;
  deltaToCarInFrontMs?: number | null;
  deltaToRaceLeaderMs?: number | null;
  isPlayer?: boolean;
}

interface TimingCarouselProps {
  cars: TimingCar[];
  connected: boolean;
  paused: boolean;
  hasSample: boolean;
}

function formatDeltaMs(ms: number | null | undefined, isLeader: boolean): string {
  if (isLeader) return "LEADER";
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms < 0) return "—";
  if (ms === 0) return "+0.000s";
  const totalSeconds = ms / 1000;
  if (totalSeconds >= 60) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = (totalSeconds % 60).toFixed(1).padStart(4, "0");
    return `+${minutes}:${seconds}`;
  }
  return `+${totalSeconds.toFixed(3)}s`;
}

function driverLabel(car: TimingCar): string {
  const raw = car.name?.trim();
  if (raw) {
    const parts = raw.split(/\s+/);
    const last = parts[parts.length - 1] || raw;
    return last.slice(0, 10).toUpperCase();
  }
  if (car.driverNumber !== null && car.driverNumber !== undefined && car.driverNumber !== "") {
    return `#${car.driverNumber}`;
  }
  return typeof car.index === "number" ? `CAR ${car.index + 1}` : "CAR";
}

export default function TimingCarousel({
  cars,
  connected,
  paused,
  hasSample,
}: TimingCarouselProps) {
  const [mode, setMode] = useState<"interval" | "leader">("interval");

  const orderedCars = useMemo(() => {
    return [...cars]
      .filter((car) => typeof car.position === "number" && car.position > 0)
      .sort((a, b) => (a.position ?? 999) - (b.position ?? 999));
  }, [cars]);

  if (orderedCars.length === 0) {
    if (connected) return null;
    return (
      <div className="connection-banner" role="status">
        <span className="banner-icon">!</span>
        <div>
          <strong>
            {paused
              ? "Game paused — readings and traces frozen"
              : hasSample
                ? "Live feed unavailable — showing last received readings"
                : "Waiting for F1 25 telemetry"}
          </strong>
          <span>
            {paused
              ? "Inspect the existing traces at any point. Updates continue when the game resumes."
              : hasSample
                ? "Retained values are not live. No new graph samples are added until telemetry resumes."
                : "Configure F1 25 to send UDP telemetry using format 2025 to port 20777."}
          </span>
        </div>
      </div>
    );
  }

  const statusText = paused ? "PAUSED" : !connected ? "STALE" : "LIVE";
  const durationSeconds = Math.max(18, orderedCars.length * 2.2);

  const renderItem = (car: TimingCar, keyPrefix: string) => {
    const pos = car.position ?? 0;
    const isLeader = pos === 1;
    const deltaMs = mode === "interval" ? car.deltaToCarInFrontMs : car.deltaToRaceLeaderMs;
    const key = `${keyPrefix}-${car.index ?? pos}`;

    return (
      <div
        key={key}
        className={`timing-carousel-item ${car.isPlayer ? "is-player" : ""} ${isLeader ? "is-leader" : ""}`}
      >
        <span className="tc-pos">P{pos}</span>
        <span className="tc-name">{driverLabel(car)}</span>
        <span className="tc-delta">{formatDeltaMs(deltaMs, isLeader)}</span>
      </div>
    );
  };

  return (
    <div className={`timing-carousel-bar ${!connected ? "is-stale" : ""}`} role="region" aria-label="Driver timing intervals">
      <div className="timing-carousel-controls">
        {!connected && (
          <span
            className="tc-status-badge"
            title={paused ? "Game paused — showing frozen readings" : "Live feed unavailable — showing last received readings"}
          >
            ! {statusText}
          </span>
        )}
        <button
          type="button"
          className="tc-mode-btn"
          onClick={() => setMode((m) => (m === "interval" ? "leader" : "interval"))}
          title={mode === "interval" ? "Showing interval to car ahead. Click for gap to leader." : "Showing gap to race leader. Click for interval."}
        >
          {mode === "interval" ? "INT" : "LDR"}
        </button>
      </div>

      <div className="timing-carousel-viewport">
        <div
          className="timing-carousel-track"
          style={{ animationDuration: `${durationSeconds}s` }}
        >
          {orderedCars.map((car) => renderItem(car, "a"))}
          {orderedCars.map((car) => renderItem(car, "b"))}
        </div>
      </div>
    </div>
  );
}

