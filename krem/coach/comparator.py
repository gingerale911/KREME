"""KREM Coach Telemetry Comparator.

Compares a player's lap telemetry samples against the track's configured
corner targets using corner exit speed with a 50 km/h buffer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from krem.coach.benchmarks import CornerBenchmark, TrackBenchmark

EXIT_SPEED_BUFFER_KPH = 50.0


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
    brake_delta_m: float | None
    apex_speed_delta_kph: float  # negative = slower than target
    throttle_delta_m: float | None
    time_loss_s: float
    diagnosis: str
    notes: str
    brake_on_ms: float | None = None
    brake_release_ms: float | None = None
    throttle_on_ms: float | None = None
    status: str = "insufficient_data"
    brake_status: str = "unavailable"
    throttle_status: str = "unavailable"
    sample_count: int = 0
    pace_status: str = "insufficient_data"
    player_exit_speed_kph: float | None = None
    exit_speed_delta_kph: float = 0.0
    speed_buffer_kph: float = EXIT_SPEED_BUFFER_KPH

    def to_dict(self) -> dict[str, Any]:
        measured = self.pace_status != "insufficient_data"
        exit_speed = round(self.player_exit_speed_kph, 1) if measured and self.player_exit_speed_kph is not None else None
        return {
            "turn": self.turn,
            "name": self.name,
            "start_m": round(self.start_m, 1),
            "end_m": round(self.end_m, 1),
            "apex_m": round(self.apex_m, 1),
            "sector": self.sector,
            "ideal_brake_m": round(self.ideal_brake_m, 1),
            "ideal_apex_speed_kph": round(self.ideal_apex_speed_kph, 1),
            "ideal_exit_speed_kph": round(self.ideal_apex_speed_kph, 1),
            "ideal_apex_gear": self.ideal_apex_gear,
            "player_brake_on_m": None,
            "player_min_speed_kph": exit_speed,
            "player_exit_speed_kph": exit_speed,
            "player_throttle_on_m": None,
            "brake_delta_m": None,
            "apex_speed_delta_kph": round(self.exit_speed_delta_kph, 1),
            "exit_speed_delta_kph": round(self.exit_speed_delta_kph, 1),
            "speed_buffer_kph": self.speed_buffer_kph,
            "throttle_delta_m": None,
            "time_loss_s": round(self.time_loss_s, 3),
            "diagnosis": self.diagnosis,
            "notes": self.notes,
            "brake_on_ms": None,
            "brake_release_ms": None,
            "throttle_on_ms": None,
            "ideal_throttle_m": self.ideal_throttle_m,
            "status": self.status,
            "brake_status": self.brake_status,
            "throttle_status": self.throttle_status,
            "sample_count": self.sample_count,
            "pace_status": self.pace_status,
        }


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _select_exit_sample(valid: list[dict[str, Any]], corner: CornerBenchmark) -> dict[str, Any] | None:
    """Return the valid telemetry sample closest to the corner exit (end_m)."""
    candidates = [s for s in valid if abs(s["distance"] - corner.end_m) <= 25]
    if not candidates:
        candidates = [s for s in valid if corner.start_m <= s["distance"] <= corner.end_m]
    if not candidates:
        return None
    return min(candidates, key=lambda s: (abs(s["distance"] - corner.end_m), -s["elapsedTimeMs"]))


def compare_lap_to_benchmark(
    samples: list[dict[str, Any]],
    benchmark: TrackBenchmark,
    target_sector: int | None = None,
) -> list[CornerDelta]:
    """Compare corner exit speed against configured corner targets with a 50 km/h buffer."""
    results: list[CornerDelta] = []
    for corner in benchmark.corners:
        if target_sector is not None and corner.sector != target_sector:
            continue
        start = max(0, corner.start_m - 30)
        end = min(benchmark.track_length_m, corner.end_m + 30)
        window = [s for s in samples if _finite(s.get("distance")) and start <= s["distance"] <= end]
        valid = [s for s in window if all(_finite(s.get(k)) for k in ("elapsedTimeMs", "speed"))]
        valid.sort(key=lambda s: s["elapsedTimeMs"])

        coverage = bool(valid and valid[0]["distance"] <= corner.start_m and valid[-1]["distance"] >= corner.end_m)
        core = [s for s in window if corner.start_m <= s["distance"] <= corner.end_m]
        core_valid = [s for s in core if all(_finite(s.get(k)) for k in ("elapsedTimeMs", "speed"))]
        coverage = coverage and len(core_valid) == len(core) and not any(s.get("gapBefore") for s in core_valid[1:])
        coverage = coverage and all(
            0 <= b["elapsedTimeMs"] - a["elapsedTimeMs"] <= 250 and b["distance"] >= a["distance"]
            for a, b in zip(core_valid, core_valid[1:])
        )

        exit_sample = _select_exit_sample(valid, corner) if coverage else None
        exit_speed = float(exit_sample["speed"]) if exit_sample is not None else 0.0
        speed_delta = exit_speed - corner.ideal_apex_speed_kph if exit_sample is not None else 0.0

        if not coverage or exit_sample is None:
            pace = "insufficient_data"
            status = "insufficient_data"
        elif speed_delta < -EXIT_SPEED_BUFFER_KPH:
            pace = "slow"
            status = "below_target"
        else:
            pace = "on_pace"
            status = "on_pace"

        if status == "insufficient_data":
            if not window:
                recorded = [s["distance"] for s in samples if _finite(s.get("distance"))]
                if recorded:
                    diagnosis = (
                        f"Turn at {corner.end_m:.0f} m exit was not recorded. "
                        f"This lap covers {min(recorded):.0f}–{max(recorded):.0f} m. "
                        "Keep telemetry running across a full lap, then analyse this sector on the next lap."
                    )
                else:
                    diagnosis = "No lap samples were recorded. Enable game UDP telemetry and complete a full lap before requesting this sector."
            elif not valid:
                diagnosis = "Lap positions were recorded, but speed packets are missing here. Check the game UDP feed and record a full lap."
            else:
                diagnosis = "Incomplete corner telemetry; no exit speed grade available."
        elif status == "below_target":
            diagnosis = (
                f"Exit speed {exit_speed:.0f} km/h is {abs(speed_delta):.0f} km/h below the "
                f"{corner.ideal_apex_speed_kph:.0f} km/h target (over the {EXIT_SPEED_BUFFER_KPH:.0f} km/h buffer). "
                "Carry more speed out of the corner."
            )
        elif speed_delta >= 0:
            diagnosis = f"Exit speed {exit_speed:.0f} km/h meets the {corner.ideal_apex_speed_kph:.0f} km/h target."
        else:
            diagnosis = (
                f"Exit speed {exit_speed:.0f} km/h vs {corner.ideal_apex_speed_kph:.0f} km/h target "
                f"({speed_delta:+.0f} km/h, within {EXIT_SPEED_BUFFER_KPH:.0f} km/h buffer)."
            )

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
            player_brake_on_m=None,
            player_min_speed_kph=exit_speed,
            player_throttle_on_m=None,
            brake_delta_m=None,
            apex_speed_delta_kph=speed_delta,
            throttle_delta_m=None,
            time_loss_s=0,
            diagnosis=diagnosis,
            notes=corner.notes,
            status=status,
            brake_status="unavailable",
            throttle_status="unavailable",
            sample_count=len(valid),
            pace_status=pace,
            player_exit_speed_kph=exit_speed if exit_sample is not None else None,
            exit_speed_delta_kph=speed_delta,
            speed_buffer_kph=EXIT_SPEED_BUFFER_KPH,
        ))
    return results
