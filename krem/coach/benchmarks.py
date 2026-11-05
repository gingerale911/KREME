"""KREM Coach Track Benchmark Registry.

Reads the track data JSON files (all 24 circuits, including Las Vegas, Monaco, etc.)
and generates the ideal benchmark targets for each track.
NO Silverstone fallbacks!
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from krem.core import TRACK_NAMES


@dataclass
class CornerBenchmark:
    turn: str
    name: str
    start_m: float
    end_m: float
    apex_m: float
    sector: int  # 1, 2, or 3
    ideal_brake_m: float
    ideal_apex_speed_kph: float
    ideal_apex_gear: int
    ideal_throttle_m: float
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn": self.turn,
            "name": self.name,
            "start_m": round(self.start_m, 1),
            "end_m": round(self.end_m, 1),
            "apex_m": round(self.apex_m, 1),
            "sector": self.sector,
            "ideal_brake_m": round(self.ideal_brake_m, 1),
            "ideal_apex_speed_kph": round(self.ideal_apex_speed_kph, 1),
            "ideal_apex_gear": self.ideal_apex_gear,
            "ideal_throttle_m": round(self.ideal_throttle_m, 1),
            "notes": self.notes,
        }


@dataclass
class TrackBenchmark:
    track_id: int
    track_name: str
    track_length_m: float
    sector1_end_m: float
    sector2_end_m: float
    ideal_lap_time_ms: int
    corners: list[CornerBenchmark] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "track_name": self.track_name,
            "track_length_m": round(self.track_length_m, 1),
            "sector1_end_m": round(self.sector1_end_m, 1),
            "sector2_end_m": round(self.sector2_end_m, 1),
            "ideal_lap_time_ms": self.ideal_lap_time_ms,
            "corners": [c.to_dict() for c in self.corners],
        }


TRACK_FILE_MAP: dict[int, str] = {
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
}

CURATED_CORNER_BENCHMARKS: dict[tuple[int, str], tuple[float, int, float, str]] = {
    # --- LAS VEGAS (Track 31) ---
    (31, "1"): (78.0, 2, 95.0, "The Hairpin: Heavy straight-line braking off main straight into 2nd gear. Rotate early."),
    (31, "2"): (135.0, 3, 50.0, "Esses 1: Flow into left kink, smooth steering rhythm"),
    (31, "3"): (155.0, 4, 40.0, "Esses 2: Quick flick right, avoid high curb"),
    (31, "4"): (190.0, 5, 0.0, "Club Exit: Full throttle acceleration sweep onto straight"),
    (31, "5"): (90.0, 2, 75.0, "Koval Approach: 90-degree right onto Koval Lane. 50m board. Clean exit is vital!"),
    (31, "6"): (165.0, 4, 60.0, "Sphere Sweeper: Accelerating left past Sphere. Tests rear traction"),
    (31, "7"): (100.0, 3, 75.0, "Sphere Right: 75m mark before tight right. Trail-brake smoothly"),
    (31, "8"): (220.0, 6, 0.0, "Sands Entry: Sweeping left onto Sands Avenue"),
    (31, "9"): (235.0, 6, 0.0, "Sands Curve: High-speed sweep, maintain momentum"),
    (31, "10"): (245.0, 7, 0.0, "Hotel Sweeper: Flat out past Venetian in dry conditions"),
    (31, "11"): (230.0, 6, 50.0, "Boulevard Approach: Quick left flick setting up the Strip entry"),
    (31, "12"): (110.0, 3, 100.0, "Strip Entry: 100m board. Crucial corner! Good exit dictates speed down 1.9km Strip!"),
    (31, "13"): (350.0, 8, 0.0, "The Strip: 100% full throttle blast at 350+ km/h"),
    (31, "14"): (84.0, 2, 100.0, "Strip Chicane 1: 100m board from 350+ km/h. Heaviest stop on track. Brake straight!"),
    (31, "15"): (105.0, 3, 0.0, "Strip Chicane 2: Flick right across inside kerb. Stay off high orange curb"),
    (31, "16"): (125.0, 3, 0.0, "Chicane Exit: Open steering and roll onto power smoothly"),
    (31, "17"): (165.0, 4, 50.0, "Final Corner: Light drag-brake to tuck nose in, full throttle onto pit straight"),

    # --- SPA (Track 10) ---
    (10, "1"): (82.0, 3, 105.0, "La Source: 100m board, trail-brake into 3rd, avoid exit sausage curb"),
    (10, "3"): (308.0, 8, 0.0, "Eau Rouge: Flat out in 8th, clip curb on entry smoothly"),
    (10, "4"): (300.0, 8, 0.0, "Raidillon: Flat out, minimize steering scrub over crest"),
    (10, "5"): (95.0, 3, 80.0, "Les Combes (entry): 75m mark, aggressive trail-brake into apex"),
    (10, "6"): (125.0, 4, 15.0, "Les Combes (exit): Fast weight shift left, cut inside curb"),
    (10, "7"): (175.0, 4, 45.0, "Malmedy: Light lift/dab, feed throttle progressively"),
    (10, "8"): (88.0, 2, 65.0, "Rivage: 60m board, downhill trail-braking, avoid early turn-in"),
    (10, "9"): (150.0, 4, 45.0, "Bruxelles exit / T9: Trail-brake flick, drift wide for entry into valley"),
    (10, "10"): (240.0, 7, 30.0, "Pouhon (entry): Quick dab/lift at entry, commit into apex"),
    (10, "11"): (252.0, 7, 0.0, "Pouhon (exit): Full throttle sweep through second apex"),
    (10, "12"): (165.0, 4, 55.0, "Fagnes (entry): 50m board, sharp stab on brakes into 4th"),
    (10, "13"): (185.0, 5, 0.0, "Fagnes (exit): Flow through left apex without unsettling rear"),
    (10, "14"): (215.0, 5, 50.0, "Campus / Stavelot: Light tap, maximize minimum speed for long run"),
    (10, "15"): (275.0, 7, 0.0, "Courbe Paul Frère: Flat out acceleration sweep"),
    (10, "17"): (310.0, 8, 0.0, "Blanchimont: 100% full throttle, smooth progressive line"),
    (10, "18"): (78.0, 2, 90.0, "Bus Stop: 90m board, heaviest braking on track, stay off high exit sausages"),
    (10, "19"): (82.0, 2, 10.0, "Bus Stop exit: Rotate car early and hit full throttle onto straight"),

    # --- MONZA (Track 11) ---
    (11, "1"): (78.0, 2, 120.0, "Variante del Rettifilo T1: 120m board, straight-line 100% brake hit into 2nd"),
    (11, "2"): (90.0, 2, 15.0, "Variante del Rettifilo T2: Hop left kerb, full throttle on exit"),
    (11, "4"): (115.0, 3, 95.0, "Variante della Roggia T4: 100m board, trail brake over curb"),
    (11, "5"): (130.0, 3, 10.0, "Variante della Roggia T5: Clip left kerb, quick acceleration into Lesmos"),
    (11, "6"): (165.0, 4, 50.0, "1st Lesmo: 50m board dab, rotate in 4th, carry momentum"),
    (11, "7"): (155.0, 4, 55.0, "2nd Lesmo: 50m board, clip inside kerb, maximize exit drive"),
    (11, "8"): (160.0, 4, 70.0, "Ascari entry (T8): 70m board, heavy trail-brake into fast chicane"),
    (11, "9"): (185.0, 5, 10.0, "Ascari middle (T9): Right flick across curb flat out"),
    (11, "10"): (215.0, 6, 0.0, "Ascari exit (T10): 100% throttle launch onto back straight"),
    (11, "11"): (180.0, 5, 75.0, "Parabolica / Curva Alboreto: 80m board, smooth trail-brake, hug mid-corner"),

    # --- SILVERSTONE (Track 7) ---
    (7, "1"): (255.0, 7, 25.0, "Abbey: High speed flick in 7th, minimal lift, carry 250+ km/h"),
    (7, "2"): (285.0, 8, 0.0, "Farm: Flat out in 8th"),
    (7, "3"): (85.0, 2, 85.0, "Village: 80m board, heavy trail-brake into tight hairpin in 2nd"),
    (7, "4"): (105.0, 3, 20.0, "The Loop: Slowest turn, late apex for early acceleration"),
    (7, "5"): (165.0, 4, 15.0, "Aintree: Full throttle launch down Wellington straight"),
    (7, "6"): (140.0, 4, 85.0, "Brooklands: 85m board, long progressive trail-brake into 4th"),
    (7, "7"): (115.0, 3, 35.0, "Luffield: Long sustained apex, patient throttle feed"),
    (7, "8"): (225.0, 7, 0.0, "Woodcote: Flat out exit onto National Straight"),
    (7, "9"): (265.0, 7, 30.0, "Copse: 30m tap/lift, commit aggressively, 260+ km/h apex"),
    (7, "10"): (275.0, 7, 15.0, "Maggotts: Flat out initial flick right in 7th"),
    (7, "11"): (240.0, 6, 25.0, "Becketts 1: Quick dab, rotate left in 6th"),
    (7, "12"): (195.0, 5, 30.0, "Becketts 2: Down to 5th, tight right clip"),
    (7, "13"): (155.0, 4, 25.0, "Chapel: Power down early onto Hangar Straight"),
    (7, "15"): (175.0, 4, 90.0, "Stowe: 90m board, firm initial brake, ride outside exit curb"),
    (7, "16"): (95.0, 2, 75.0, "Vale: Downhill stop, hard 100% brake hit into 2nd"),
    (7, "17"): (110.0, 3, 20.0, "Club entry: Hop right curb, patient on power"),
    (7, "18"): (180.0, 5, 0.0, "Club exit: Full throttle launch over start/finish"),
}


def load_track_sections_from_json(json_path: Path) -> tuple[str, float, float, float, list[dict[str, Any]]]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    track_name = data.get("track", "Unknown Track")
    track_length = float(data.get("game_track_length_m", 5000.0))
    sectors = data.get("sectors", [])
    splits = sorted([float(s.get("lap_dist_m", 0.0)) for s in sectors if float(s.get("lap_dist_m", 0.0)) > 50.0])
    s1_end = splits[0] if len(splits) > 0 else track_length * 0.33
    s2_end = splits[1] if len(splits) > 1 else track_length * 0.66
    sections = data.get("sections", [])
    return track_name, track_length, s1_end, s2_end, sections


def generate_benchmark_for_track(track_id: int, track_data_dir: Path) -> TrackBenchmark:
    """Generate or retrieve the ideal benchmark for ANY track_id from JSON data."""
    filename = TRACK_FILE_MAP.get(track_id)
    if filename:
        json_path = track_data_dir / filename
        if json_path.is_file():
            track_name, track_length, s1_end, s2_end, sections = load_track_sections_from_json(json_path)
            corners = []
            for s in sections:
                turn = str(s.get("turn") or "")
                name = str(s.get("name") or (f"Turn {turn}" if turn else "Section"))
                start_m = float(s.get("start_m", 0.0))
                end_m = float(s.get("end_m", start_m + 50.0))
                apex_m = float(s.get("apex_m") if s.get("apex_m") is not None else (start_m + end_m) / 2.0)
                sec = 1 if apex_m <= s1_end else 2 if apex_m <= s2_end else 3

                curated = CURATED_CORNER_BENCHMARKS.get((track_id, turn))
                if curated:
                    ideal_speed, ideal_gear, brake_offset, notes = curated
                    ideal_brake = max(0.0, apex_m - brake_offset) if brake_offset > 0 else 0.0
                    ideal_throttle = apex_m + 25.0
                else:
                    span = max(20.0, end_m - start_m)
                    severity = float(s.get("severity", 2.0) or 2.0)
                    if severity >= 3.0 or span < 60.0:
                        ideal_speed, ideal_gear, brake_dist = 85.0, 2, 85.0
                    elif severity >= 2.0 or span < 120.0:
                        ideal_speed, ideal_gear, brake_dist = 135.0, 3, 65.0
                    elif span < 200.0:
                        ideal_speed, ideal_gear, brake_dist = 185.0, 5, 40.0
                    else:
                        ideal_speed, ideal_gear, brake_dist = 250.0, 7, 25.0

                    ideal_brake = max(0.0, apex_m - brake_dist)
                    ideal_throttle = apex_m + 25.0
                    notes = f"Turn {turn} {name}: Maintain smooth trail braking in gear {ideal_gear}"

                corners.append(CornerBenchmark(
                    turn=turn or str(len(corners) + 1),
                    name=name,
                    start_m=start_m,
                    end_m=end_m,
                    apex_m=apex_m,
                    sector=sec,
                    ideal_brake_m=ideal_brake,
                    ideal_apex_speed_kph=ideal_speed,
                    ideal_apex_gear=ideal_gear,
                    ideal_throttle_m=ideal_throttle,
                    notes=notes,
                ))

            return TrackBenchmark(
                track_id=track_id,
                track_name=track_name,
                track_length_m=track_length,
                sector1_end_m=s1_end,
                sector2_end_m=s2_end,
                ideal_lap_time_ms=int((track_length / 64.0) * 1000),
                corners=corners,
            )

    # Dynamic fallback using game's official track name from core
    track_name = TRACK_NAMES.get(track_id, f"Circuit {track_id}")
    track_length = 5000.0
    s1_end = 1650.0
    s2_end = 3300.0
    return TrackBenchmark(
        track_id=track_id,
        track_name=track_name,
        track_length_m=track_length,
        sector1_end_m=s1_end,
        sector2_end_m=s2_end,
        ideal_lap_time_ms=int((track_length / 64.0) * 1000),
        corners=[],
    )


class BenchmarkRegistry:
    """Caches and serves track benchmarks."""

    def __init__(self, track_data_dir: Path | None = None) -> None:
        if track_data_dir is None:
            track_data_dir = Path(__file__).resolve().parents[2] / "frontend" / "public" / "track_data"
        self.track_data_dir = track_data_dir
        self._cache: dict[int, TrackBenchmark] = {}

    def get_benchmark(self, track_id: int) -> TrackBenchmark:
        if track_id in self._cache:
            return self._cache[track_id]

        benchmark = generate_benchmark_for_track(track_id, self.track_data_dir)
        self._cache[track_id] = benchmark
        return benchmark
