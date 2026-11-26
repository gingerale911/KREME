"""Deterministic corner exit comparison; missing measurements stay unknown."""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Any
from krem.coach.benchmarks import TrackBenchmark


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass
class CornerDelta:
    turn: str
    name: str
    sector: int
    exit_m: float
    ideal_brake_m: float | None
    ideal_throttle_m: float | None
    ideal_exit_speed_kph: float | None
    player_brake_on_m: float | None
    player_throttle_on_m: float | None
    player_exit_speed_kph: float | None
    exit_speed_delta_kph: float | None
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_exit(delta):
    if delta is None:
        return "unavailable"
    return "fast" if delta >= 50 else "slow" if delta <= -50 else "on pace"


def compare_lap_to_benchmark(samples, benchmark: TrackBenchmark, target_sector=None):
    results = []
    for c in benchmark.corners:
        if target_sector is not None and c.sector != target_sector:
            continue
        # Preserve trace order and gaps. Never interpolate across missing data.
        window = [s for s in samples if number(s.get("distance"))
                  and max(0, c.start_m - 120) <= s["distance"] <= c.end_m + 30]
        exit_speed = None
        brake_on = throttle_on = None
        for s in window:
            if s["distance"] == c.end_m and number(s.get("speed")):
                exit_speed = s["speed"]
        for a, b in zip(window, window[1:]):
            da, db = a["distance"], b["distance"]
            if b.get("gapBefore") or not 0 < db - da <= 30:
                continue
            if da < c.end_m < db and all(number(s.get("speed")) for s in (a, b)):
                exit_speed = a["speed"] + (b["speed"] - a["speed"]) * (c.end_m - da) / (db - da)
            if db < c.apex_m and brake_on is None and all(number(s.get("brake")) for s in (a,b)):
                if a["brake"] < .15 <= b["brake"]:
                    brake_on = db
            # Acceleration start means initial pedal application, not 85% throttle.
            if c.apex_m - 15 <= db <= c.end_m and throttle_on is None and all(number(s.get("throttle")) for s in (a,b)):
                if a["throttle"] < .1 <= b["throttle"]:
                    throttle_on = db
        ideal_exit = c.ideal_exit_speed_kph
        delta = exit_speed - ideal_exit if exit_speed is not None and ideal_exit is not None else None
        results.append(CornerDelta(c.turn, c.name, c.sector, c.end_m,
            c.optimal_brake_m, c.optimal_acceleration_start_m, ideal_exit,
            brake_on, throttle_on, exit_speed, delta, classify_exit(delta)))
    return results
