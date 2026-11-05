"""KREM Coach Telemetry Comparator.

Compares a player's lap telemetry samples against the track's ideal benchmark
to compute deterministic corner-by-corner performance deltas:
- Braking point delta (meters early or late)
- Minimum corner / apex speed deficit (km/h)
- Full-throttle exit pick-up point delta (meters)
- Estimated time loss per corner
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from krem.coach.benchmarks import CornerBenchmark, TrackBenchmark


@dataclass
class CornerDelta:
    turn: str
    name: str
    start_m: float
    end_m: float
    apex_m: float
    sector: int
    # Benchmark targets
    ideal_brake_m: float
    ideal_apex_speed_kph: float
    ideal_apex_gear: int
    ideal_throttle_m: float
    # Player actuals
    player_brake_on_m: float | None
    player_min_speed_kph: float
    player_throttle_on_m: float | None
    # Computed deltas
    brake_delta_m: float | None  # positive = braked early, negative = braked late
    apex_speed_delta_kph: float  # negative = slower than ideal (overslowing)
    throttle_delta_m: float | None  # positive = got on throttle later than ideal
    time_loss_s: float
    diagnosis: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "name": self.name,
            "apex_m": round(self.apex_m, 1),
            "sector": self.sector,
            "ideal_brake_m": round(self.ideal_brake_m, 1),
            "ideal_apex_speed_kph": round(self.ideal_apex_speed_kph, 1),
            "ideal_apex_gear": self.ideal_apex_gear,
            "player_brake_on_m": round(self.player_brake_on_m, 1) if self.player_brake_on_m is not None else None,
            "player_min_speed_kph": round(self.player_min_speed_kph, 1),
            "player_throttle_on_m": round(self.player_throttle_on_m, 1) if self.player_throttle_on_m is not None else None,
            "brake_delta_m": round(self.brake_delta_m, 1) if self.brake_delta_m is not None else None,
            "apex_speed_delta_kph": round(self.apex_speed_delta_kph, 1),
            "throttle_delta_m": round(self.throttle_delta_m, 1) if self.throttle_delta_m is not None else None,
            "time_loss_s": round(self.time_loss_s, 3),
            "diagnosis": self.diagnosis,
            "notes": self.notes,
        }


def compare_lap_to_benchmark(
    samples: list[dict[str, Any]],
    benchmark: TrackBenchmark,
    target_sector: int | None = None,
) -> list[CornerDelta]:
    """Compare a list of lap telemetry samples to the track's ideal benchmark."""
    if not samples or not benchmark.corners:
        return []

    results: list[CornerDelta] = []

    for corner in benchmark.corners:
        if target_sector is not None and corner.sector != target_sector:
            continue

        search_start = max(0.0, corner.start_m - 120.0)
        search_end = min(benchmark.track_length_m, corner.end_m + 80.0)

        corner_samples = [
            s for s in samples
            if search_start <= float(s.get("distance", s.get("lapDistance", 0.0))) <= search_end
        ]

        if not corner_samples:
            continue

        speeds = [float(s.get("speed", 0.0)) for s in corner_samples]
        player_min_speed = min(speeds) if speeds else 0.0

        player_brake_on_m: float | None = None
        for s in corner_samples:
            dist = float(s.get("distance", s.get("lapDistance", 0.0)))
            brake = float(s.get("brake", 0.0))
            if dist < corner.apex_m and brake >= 0.15:
                player_brake_on_m = dist
                break

        player_throttle_on_m: float | None = None
        for s in corner_samples:
            dist = float(s.get("distance", s.get("lapDistance", 0.0)))
            throttle = float(s.get("throttle", 0.0))
            if dist >= (corner.apex_m - 15.0) and throttle >= 0.85:
                player_throttle_on_m = dist
                break

        brake_delta: float | None = None
        if player_brake_on_m is not None and corner.ideal_brake_m > 0:
            brake_delta = corner.ideal_brake_m - player_brake_on_m

        speed_delta = player_min_speed - corner.ideal_apex_speed_kph

        throttle_delta: float | None = None
        if player_throttle_on_m is not None and corner.ideal_throttle_m > 0:
            throttle_delta = player_throttle_on_m - corner.ideal_throttle_m

        corner_span = max(40.0, corner.end_m - corner.start_m)
        v_actual_mps = max(10.0, player_min_speed / 3.6)
        v_ideal_mps = max(10.0, corner.ideal_apex_speed_kph / 3.6)

        raw_time_loss = corner_span * (1.0 / v_actual_mps - 1.0 / v_ideal_mps)
        if throttle_delta and throttle_delta > 0:
            raw_time_loss += (throttle_delta / v_actual_mps) * 0.4

        time_loss_s = max(0.0, raw_time_loss)

        diagnoses: list[str] = []
        if brake_delta is not None:
            if brake_delta > 20.0:
                diagnoses.append(f"Braked {abs(round(brake_delta))}m too early")
            elif brake_delta < -15.0:
                diagnoses.append(f"Braked {abs(round(brake_delta))}m late (missed apex risk)")

        if speed_delta < -12.0:
            diagnoses.append(f"Overslowed by {abs(round(speed_delta))} km/h at apex")
        elif speed_delta > 10.0:
            diagnoses.append(f"High apex speed (+{round(speed_delta)} km/h)")

        if throttle_delta is not None and throttle_delta > 15.0:
            diagnoses.append(f"Late on throttle by {round(throttle_delta)}m")

        diagnosis = " · ".join(diagnoses) if diagnoses else "Clean execution on ideal line"

        results.append(CornerDelta(
            turn=corner.turn,
            name=corner.name,
            start_m=corner.start_m,
            end_m=corner.end_m,
            apex_m=corner.apex_m,
            sector=corner.sector,
            ideal_brake_m=corner.ideal_brake_m,
            ideal_apex_speed_kph=corner.ideal_apex_speed_kph,
            ideal_apex_gear=corner.ideal_apex_gear,
            ideal_throttle_m=corner.ideal_throttle_m,
            player_brake_on_m=player_brake_on_m,
            player_min_speed_kph=player_min_speed,
            player_throttle_on_m=player_throttle_on_m,
            brake_delta_m=brake_delta,
            apex_speed_delta_kph=speed_delta,
            throttle_delta_m=throttle_delta,
            time_loss_s=round(time_loss_s, 3),
            diagnosis=diagnosis,
            notes=corner.notes,
        ))

    return results
