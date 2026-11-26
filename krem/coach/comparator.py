"""KREM Coach Telemetry Comparator.

Compares a player's lap telemetry across each corner [start_m, end_m] using:
- Minimum corner speed against target ± 20 km/h
- Apex placement window [apex_m - 20 m, apex_m + 15 m] (early vs overshoot)
- Double-slowdown detection (slow early -> accelerate -> slow again)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from krem.coach.benchmarks import CornerBenchmark, TrackBenchmark

APEX_SPEED_BUFFER_KPH = 20.0
APEX_OVERSHOOT_ALLOWANCE_M = 15.0
APEX_EARLY_ALLOWANCE_M = 20.0
SPEED_SWING_THRESHOLD_KPH = 10.0


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
    min_speed_m: float | None = None
    apex_offset_m: float | None = None
    target_min_speed_kph: float = 0.0
    target_max_speed_kph: float = 0.0
    speed_buffer_kph: float = APEX_SPEED_BUFFER_KPH
    double_slowdown: bool = False
    is_braking_corner: bool = False

    def to_dict(self) -> dict[str, Any]:
        measured = self.pace_status != "insufficient_data"
        min_speed = round(self.player_min_speed_kph, 1) if measured else None
        return {
            "turn": self.turn,
            "name": self.name,
            "start_m": round(self.start_m, 1),
            "end_m": round(self.end_m, 1),
            "apex_m": round(self.apex_m, 1),
            "sector": self.sector,
            "ideal_brake_m": round(self.ideal_brake_m, 1),
            "ideal_apex_speed_kph": round(self.ideal_apex_speed_kph, 1),
            "target_min_speed_kph": round(self.target_min_speed_kph, 1),
            "target_max_speed_kph": round(self.target_max_speed_kph, 1),
            "ideal_apex_gear": self.ideal_apex_gear,
            "player_brake_on_m": None,
            "player_min_speed_kph": min_speed,
            "min_speed_m": round(self.min_speed_m, 1) if measured and self.min_speed_m is not None else None,
            "apex_offset_m": round(self.apex_offset_m, 1) if measured and self.apex_offset_m is not None else None,
            "player_throttle_on_m": None,
            "brake_delta_m": None,
            "apex_speed_delta_kph": round(self.apex_speed_delta_kph, 1),
            "speed_buffer_kph": self.speed_buffer_kph,
            "double_slowdown": self.double_slowdown,
            "is_braking_corner": self.is_braking_corner,
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


def _has_double_slowdown(
    core_valid: list[dict[str, Any]],
    swing_kph: float = SPEED_SWING_THRESHOLD_KPH,
) -> bool:
    """Detect slow -> accelerate (>= swing_kph) -> slow again (>= swing_kph) in one corner."""
    if len(core_valid) < 3:
        return False
    min_seen = float(core_valid[0]["speed"])
    peak_after_dip: float | None = None
    for s in core_valid[1:]:
        spd = float(s["speed"])
        if peak_after_dip is None:
            if spd < min_seen:
                min_seen = spd
            elif spd >= min_seen + swing_kph:
                peak_after_dip = spd
        else:
            if spd > peak_after_dip:
                peak_after_dip = spd
            elif spd <= peak_after_dip - swing_kph:
                return True
    return False


def compare_lap_to_benchmark(
    samples: list[dict[str, Any]],
    benchmark: TrackBenchmark,
    target_sector: int | None = None,
) -> list[CornerDelta]:
    """Compare minimum corner speed, apex timing window, and double-slowdowns."""
    results: list[CornerDelta] = []
    for corner in benchmark.corners:
        if target_sector is not None and corner.sector != target_sector:
            continue
        start = max(0, corner.start_m - 30)
        end = min(benchmark.track_length_m, corner.end_m + 30)
        window = [s for s in samples if _finite(s.get("distance")) and start <= s["distance"] <= end]
        valid = [s for s in window if all(_finite(s.get(k)) for k in ("elapsedTimeMs", "speed"))]
        valid.sort(key=lambda s: (s["elapsedTimeMs"], s["distance"]))

        coverage = bool(valid and valid[0]["distance"] <= corner.start_m and valid[-1]["distance"] >= corner.end_m)
        core = [s for s in window if corner.start_m <= s["distance"] <= corner.end_m]
        core_valid = [s for s in core if all(_finite(s.get(k)) for k in ("elapsedTimeMs", "speed"))]
        coverage = coverage and len(core_valid) == len(core) and not any(s.get("gapBefore") for s in core_valid[1:])
        coverage = coverage and all(
            0 <= b["elapsedTimeMs"] - a["elapsedTimeMs"] <= 250 and b["distance"] >= a["distance"]
            for a, b in zip(core_valid, core_valid[1:])
        )

        target_low = max(0.0, corner.ideal_apex_speed_kph - APEX_SPEED_BUFFER_KPH)
        target_high = corner.ideal_apex_speed_kph + APEX_SPEED_BUFFER_KPH

        if not coverage or not core_valid:
            min_speed = 0.0
            min_speed_m: float | None = None
            apex_offset_m: float | None = None
            speed_delta = 0.0
            is_braking_corner = False
            double_slowdown = False
            pace = "insufficient_data"
            status = "insufficient_data"

            if not window:
                recorded = [s["distance"] for s in samples if _finite(s.get("distance"))]
                if recorded:
                    diagnosis = (
                        f"Turn at {corner.apex_m:.0f} m was not recorded. "
                        f"This lap covers {min(recorded):.0f}–{max(recorded):.0f} m. "
                        "Keep telemetry running across a full lap, then analyse this sector on the next lap."
                    )
                else:
                    diagnosis = "No lap samples were recorded. Enable game UDP telemetry and complete a full lap before requesting this sector."
            elif not valid:
                diagnosis = "Lap positions were recorded, but speed packets are missing here. Check the game UDP feed and record a full lap."
            else:
                diagnosis = "Incomplete corner telemetry; no apex speed grade available."
        else:
            min_sample = min(core_valid, key=lambda s: (float(s["speed"]), float(s["elapsedTimeMs"])))
            min_speed = float(min_sample["speed"])
            min_speed_m = float(min_sample["distance"])
            entry_speed = float(core_valid[0]["speed"])
            is_braking_corner = (entry_speed - min_speed) >= SPEED_SWING_THRESHOLD_KPH
            section_type = getattr(corner, "section_type", "corner")
            double_slowdown = (section_type != "chicane") and _has_double_slowdown(core_valid)

            overshoot_limit_m = min(corner.end_m, corner.apex_m + APEX_OVERSHOOT_ALLOWANCE_M)
            early_limit_m = max(corner.start_m, corner.apex_m - APEX_EARLY_ALLOWANCE_M)
            apex_offset_m = min_speed_m - corner.apex_m
            speed_delta = min_speed - corner.ideal_apex_speed_kph

            if double_slowdown:
                status = "double_slowdown"
                pace = "slow" if min_speed < target_low else "inconsistent"
                diagnosis = (
                    f"Slowed early, accelerated, then had to slow again (lowest {min_speed:.0f} km/h at "
                    f"{min_speed_m:.0f} m vs {corner.apex_m:.0f} m apex). Carry smoother entry speed into one clean apex."
                )
            elif min_speed_m > overshoot_limit_m:
                status = "late"
                pace = "slow" if min_speed < target_low else "overshot"
                diagnosis = (
                    f"Overshot apex by {apex_offset_m:.0f} m (min {min_speed:.0f} km/h at {min_speed_m:.0f} m "
                    f"vs {corner.apex_m:.0f} m apex, >{APEX_OVERSHOOT_ALLOWANCE_M:.0f} m limit). Brake slightly earlier next sector."
                )
            elif is_braking_corner and min_speed_m < early_limit_m:
                status = "early"
                pace = "slow" if min_speed < target_low else "early"
                diagnosis = (
                    f"Hit min speed {abs(apex_offset_m):.0f} m early ({min_speed:.0f} km/h at {min_speed_m:.0f} m "
                    f"vs {corner.apex_m:.0f} m apex). Brake slightly later and trail-brake to the apex."
                )
            elif min_speed < target_low:
                status = "below_target"
                pace = "slow"
                diagnosis = (
                    f"Min speed {min_speed:.0f} km/h is below the {target_low:.0f}–{target_high:.0f} km/h target range. "
                    "Carry more speed through the apex."
                )
            elif min_speed > target_high:
                status = "on_pace"
                pace = "fast"
                diagnosis = (
                    f"Min speed {min_speed:.0f} km/h at {min_speed_m:.0f} m exceeds the "
                    f"{target_low:.0f}–{target_high:.0f} km/h target range cleanly without overshooting."
                )
            else:
                status = "on_pace"
                pace = "on_pace"
                diagnosis = (
                    f"Min speed {min_speed:.0f} km/h at {min_speed_m:.0f} m is within the "
                    f"{target_low:.0f}–{target_high:.0f} km/h target range."
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
            player_min_speed_kph=min_speed,
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
            min_speed_m=min_speed_m,
            apex_offset_m=apex_offset_m,
            target_min_speed_kph=target_low,
            target_max_speed_kph=target_high,
            speed_buffer_kph=APEX_SPEED_BUFFER_KPH,
            double_slowdown=double_slowdown,
            is_braking_corner=is_braking_corner,
        ))
    return results
