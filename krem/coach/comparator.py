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
    brake_on_ms: float | None = None
    brake_release_ms: float | None = None
    throttle_on_ms: float | None = None
    status: str = "insufficient_data"
    brake_status: str = "unavailable"
    throttle_status: str = "unavailable"
    sample_count: int = 0
    pace_status: str = "insufficient_data"

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
            "player_min_speed_kph": round(self.player_min_speed_kph, 1) if self.pace_status != 'insufficient_data' else None,
            "player_throttle_on_m": round(self.player_throttle_on_m, 1) if self.player_throttle_on_m is not None else None,
            "brake_delta_m": round(self.brake_delta_m, 1) if self.brake_delta_m is not None else None,
            "apex_speed_delta_kph": round(self.apex_speed_delta_kph, 1),
            "throttle_delta_m": round(self.throttle_delta_m, 1) if self.throttle_delta_m is not None else None,
            "time_loss_s": round(self.time_loss_s, 3),
            "diagnosis": self.diagnosis,
            "notes": self.notes,
            "brake_on_ms": self.brake_on_ms,
            "brake_release_ms": self.brake_release_ms,
            "throttle_on_ms": self.throttle_on_ms,
            "ideal_throttle_m": self.ideal_throttle_m,
            "status": self.status,
            "brake_status": self.brake_status,
            "throttle_status": self.throttle_status,
            "sample_count": self.sample_count,
            "pace_status": self.pace_status,
        }


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def compare_lap_to_benchmark(samples, benchmark, target_sector=None):
    """Measure input transitions without converting missing samples into zeroes.

    Positions are absolute lap distances. Times are elapsed milliseconds from
    the previous lap's start, not predicted time losses against a reference lap.
    """
    results = []
    for corner in benchmark.corners:
        if target_sector is not None and corner.sector != target_sector:
            continue
        start = max(0, min(corner.start_m - 120, corner.ideal_brake_m - 80) if corner.ideal_brake_m else corner.start_m - 120)
        end = min(benchmark.track_length_m, corner.end_m + 80)
        window = [s for s in samples if _finite(s.get('distance')) and start <= s['distance'] <= end]
        valid = [s for s in window if all(_finite(s.get(k)) for k in ('elapsedTimeMs', 'speed', 'throttle', 'brake'))]
        valid.sort(key=lambda s: s['elapsedTimeMs'])
        coverage = bool(valid and valid[0]['distance'] <= corner.start_m and valid[-1]['distance'] >= corner.end_m)
        core = [s for s in window if corner.start_m <= s['distance'] <= corner.end_m]
        core_valid = [s for s in core if all(_finite(s.get(k)) for k in ('elapsedTimeMs', 'speed', 'throttle', 'brake'))]
        coverage = coverage and len(core_valid) == len(core) and not any(s.get('gapBefore') for s in core_valid[1:])
        coverage = coverage and all(0 <= b['elapsedTimeMs'] - a['elapsedTimeMs'] <= 250 and b['distance'] >= a['distance']
                                    for a, b in zip(core_valid, core_valid[1:]))
        brake_on = release = throttle_on = None
        for a, b in zip(valid, valid[1:]):
            if b.get('gapBefore') or b['elapsedTimeMs'] - a['elapsedTimeMs'] > 250:
                continue
            if brake_on is None and b['distance'] < corner.apex_m and a['brake'] < .15 <= b['brake']:
                brake_on = b
            if brake_on is not None and release is None and a['brake'] >= .15 > b['brake']:
                release = b
            if throttle_on is None and b['distance'] >= corner.apex_m - 15 and a['throttle'] < .85 <= b['throttle']:
                throttle_on = b
        # A fully flat corner has no pickup transition; do not invent one.
        flat = bool(coverage and core_valid and all(s['throttle'] >= .85 for s in core_valid))
        brake_delta = corner.ideal_brake_m - brake_on['distance'] if brake_on and corner.ideal_brake_m else None
        throttle_delta = throttle_on['distance'] - corner.ideal_throttle_m if throttle_on else None
        brake_status = ('early' if brake_delta > 20 else 'late' if brake_delta < -15 else 'on_pace') if brake_delta is not None else ('not_required' if coverage and not corner.ideal_brake_m else 'unavailable')
        throttle_status = ('late' if throttle_delta > 15 else 'early' if throttle_delta < -15 else 'on_pace') if throttle_delta is not None else ('flat' if flat else 'unavailable')
        if coverage and brake_status == 'unavailable':
            brake_status = 'no_braking' if all(s['brake'] < .15 for s in core_valid) else 'already_braking'
        if coverage and throttle_status == 'unavailable':
            throttle_status = 'held_below_85_percent' if all(s['throttle'] < .85 for s in core_valid) else 'no_pickup_transition'
        apex_samples = [s['speed'] for s in valid if abs(s['distance'] - corner.apex_m) <= 20]
        minimum = min(apex_samples, default=0)
        speed_delta = minimum - corner.ideal_apex_speed_kph
        tolerance = max(5, corner.ideal_apex_speed_kph * .05)
        pace = ('fast' if speed_delta > tolerance else 'slow' if speed_delta < -tolerance else 'on_pace') if coverage and apex_samples else 'insufficient_data'
        if not coverage:
            status = 'insufficient_data'
        elif 'late' in (brake_status, throttle_status):
            status = 'late'
        elif brake_status == 'early':
            status = 'early'
        elif speed_delta < -12:
            status = 'below_target'
        else:
            status = 'on_pace'
        notes = []
        if coverage and pace != 'insufficient_data':
            notes.append(f'Apex speed {minimum:.0f} km/h versus {corner.ideal_apex_speed_kph:.0f} km/h configured target: {pace.replace("_", " ")}')
            if flat:
                notes.append('Throttle stayed above 85% through the turn; no pickup event was needed')
            elif throttle_status == 'held_below_85_percent':
                notes.append('Throttle stayed below 85% throughout the turn; build power progressively as steering unwinds on exit')
            if brake_status == 'no_braking':
                notes.append('No braking above 15% was recorded through this turn')
        if status == 'insufficient_data':
            notes.append('Incomplete corner telemetry; no pace grade available')
            if not window:
                recorded = [s['distance'] for s in samples if _finite(s.get('distance'))]
                if recorded:
                    notes[-1] = f"Turn at {corner.apex_m:.0f} m was not recorded. This lap covers {min(recorded):.0f}–{max(recorded):.0f} m. Keep telemetry running across a full lap, then analyse this sector on the next lap."
                else:
                    notes[-1] = 'No lap samples were recorded. Enable game UDP telemetry and complete a full lap before requesting this sector.'
            elif not valid:
                notes[-1] = 'Lap positions were recorded, but matched pedal and speed packets are missing here. Check the game UDP feed and record a full lap with telemetry enabled.'
        if brake_delta is not None and brake_status != 'on_pace':
            notes.append(f"Brake {abs(brake_delta):.0f} m {'later' if brake_delta > 0 else 'earlier'}")
        if throttle_delta is not None and throttle_delta > 15:
            notes.append(f'Build throttle {throttle_delta:.0f} m earlier on exit as grip allows')
        if coverage and speed_delta < -12:
            notes.append(f'Carry more apex speed toward the {corner.ideal_apex_speed_kph:.0f} km/h target')
        diagnosis = '. '.join(notes) or 'On pace against the configured targets; repeat the input timing'
        results.append(CornerDelta(
            turn=corner.turn, name=corner.name, start_m=corner.start_m, end_m=corner.end_m,
            apex_m=corner.apex_m, sector=corner.sector,
            ideal_brake_m=corner.ideal_brake_m, ideal_apex_speed_kph=corner.ideal_apex_speed_kph,
            ideal_apex_gear=corner.ideal_apex_gear, ideal_throttle_m=corner.ideal_throttle_m,
            player_brake_on_m=brake_on['distance'] if brake_on else None,
            player_min_speed_kph=minimum,
            player_throttle_on_m=throttle_on['distance'] if throttle_on else None,
            brake_delta_m=brake_delta, apex_speed_delta_kph=speed_delta,
            throttle_delta_m=throttle_delta, time_loss_s=0, diagnosis=diagnosis, notes=corner.notes,
            brake_on_ms=brake_on['elapsedTimeMs'] if brake_on else None,
            brake_release_ms=release['elapsedTimeMs'] if release else None,
            throttle_on_ms=throttle_on['elapsedTimeMs'] if throttle_on else None,
            status=status, brake_status=brake_status, throttle_status=throttle_status, sample_count=len(valid),
            pace_status=pace,
        ))
    return results
