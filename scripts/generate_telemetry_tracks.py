"""Extract accurate track circuit maps from F1 25 capture files in game world coordinates."""

import json
import math
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from krem.ingest.recorder import ReplayReader
from krem.ingest import decode_packet, decode_header


def generate_track_from_capture(
    capture_path: str,
    car_idx: int,
    track_name: str,
    track_length_m: float,
    sectors: list[dict],
    sections: list[dict],
    out_filenames: list[str],
    orientation: float = 0.0,
    track_width: float = 13.0,
):
    print(f"Reading capture {capture_path} for {track_name}...")
    reader = ReplayReader(capture_path)

    dists, xs, zs, yaws = [], [], [], []
    current_lap_dist = None

    for ts, raw in reader:
        hdr = decode_header(raw)
        if hdr.packet_id == 2:  # LapData
            p = decode_packet(raw)
            if p and "cars" in p.data and car_idx < len(p.data["cars"]):
                car = p.data["cars"][car_idx]
                current_lap_dist = float(car["lapDistance"])
        elif hdr.packet_id == 0:  # Motion
            if current_lap_dist is not None and 0.0 <= current_lap_dist <= track_length_m:
                p = decode_packet(raw)
                if p and "cars" in p.data and car_idx < len(p.data["cars"]):
                    car = p.data["cars"][car_idx]
                    dists.append(current_lap_dist)
                    xs.append(float(car["worldPositionX"]))
                    zs.append(float(car["worldPositionZ"]))
                    yaws.append(float(car["yaw"]))

    dists = np.array(dists)
    xs = np.array(xs)
    zs = np.array(zs)
    yaws = np.array(yaws)

    idx = np.argsort(dists)
    dists, xs, zs, yaws = dists[idx], xs[idx], zs[idx], yaws[idx]

    # Remove duplicates
    unique_mask = np.diff(dists, prepend=-1) > 1e-4
    dists, xs, zs, yaws = dists[unique_mask], xs[unique_mask], zs[unique_mask], yaws[unique_mask]

    N = 400
    target_dists = np.linspace(0, track_length_m, N, endpoint=False)
    rl_x = np.interp(target_dists, dists, xs)
    rl_z = np.interp(target_dists, dists, zs)

    left_edge = []
    right_edge = []
    racing_line = []
    half_width = track_width / 2.0

    for i in range(N):
        prev_i = (i - 1) % N
        next_i = (i + 1) % N
        dx = rl_x[next_i] - rl_x[prev_i]
        dz = rl_z[next_i] - rl_z[prev_i]
        L = math.hypot(dx, dz) or 1.0
        nx = -dz / L
        nz = dx / L

        rx = round(float(rl_x[i]), 2)
        rz = round(float(rl_z[i]), 2)
        racing_line.append([rx, rz])
        left_edge.append([round(rx + nx * half_width, 2), round(rz + nz * half_width, 2)])
        right_edge.append([round(rx - nx * half_width, 2), round(rz - nz * half_width, 2)])

    sf_pos = [round(float(rl_x[0]), 2), round(float(rl_z[0]), 2)]
    sf_heading = round(float(yaws[0]), 4)

    data = {
        "format_version": 1,
        "game": "f1_25",
        "track": track_name,
        "game_track_length_m": track_length_m,
        "notes": f"Exact telemetry-extracted circuit line from F1 25 game world space ({track_name})",
        "orientation": orientation,
        "sf_line": {"pos": sf_pos, "heading": sf_heading},
        "left_edge": left_edge,
        "right_edge": right_edge,
        "lines": {
            "formula1": {
                "racing_line": racing_line
            }
        },
        "sectors": sectors,
        "sections": sections,
    }

    base_dir = Path(__file__).resolve().parent.parent
    for fname in out_filenames:
        for folder in ["frontend/public/track_data", "frontend/dist/track_data"]:
            out_file = base_dir / folder / fname
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"Wrote {out_file}")


def main():
    base_dir = Path(__file__).resolve().parent.parent

    # 1. Las Vegas (Track ID 31)
    vegas_capture = str(base_dir / "captures" / "capture_20261105_022946_0000000000000000.f1udp")
    vegas_sections = [
        {"turn": "1", "name": "Turn 1", "type": "corner", "start_m": 10, "end_m": 80, "apex_m": 40},
        {"turn": "2", "name": "Turn 2", "type": "corner", "start_m": 90, "end_m": 150, "apex_m": 120},
        {"turn": "3", "name": "Turn 3", "type": "corner", "start_m": 160, "end_m": 220, "apex_m": 190},
        {"turn": "4", "name": "Turn 4 (Koval)", "type": "corner", "start_m": 270, "end_m": 340, "apex_m": 300},
        {"turn": "5", "name": "Turn 5 (Sphere Entry)", "type": "corner", "start_m": 1520, "end_m": 1620, "apex_m": 1580},
        {"turn": "6", "name": "Turn 6 (Sphere Sweeper)", "type": "corner", "start_m": 1630, "end_m": 1800, "apex_m": 1710},
        {"turn": "7", "name": "Turn 7", "type": "corner", "start_m": 1810, "end_m": 1920, "apex_m": 1860},
        {"turn": "8", "name": "Turn 8", "type": "corner", "start_m": 1930, "end_m": 2000, "apex_m": 1965},
        {"turn": "9", "name": "Turn 9 (Sands Entry)", "type": "corner", "start_m": 2010, "end_m": 2090, "apex_m": 2060},
        {"turn": "10", "name": "Turn 10", "type": "corner", "start_m": 2100, "end_m": 2160, "apex_m": 2125},
        {"turn": "11", "name": "Turn 11", "type": "corner", "start_m": 2190, "end_m": 2260, "apex_m": 2235},
        {"turn": "12", "name": "Turn 12 (Strip Entry)", "type": "corner", "start_m": 3200, "end_m": 3300, "apex_m": 3245},
        {"turn": "13", "name": "Turn 13 (Strip Curve)", "type": "corner", "start_m": 4100, "end_m": 4250, "apex_m": 4180},
        {"turn": "14", "name": "Turn 14 (Harmon Entry)", "type": "corner", "start_m": 5140, "end_m": 5240, "apex_m": 5200},
        {"turn": "15", "name": "Turn 15", "type": "corner", "start_m": 5250, "end_m": 5340, "apex_m": 5300},
        {"turn": "16", "name": "Turn 16", "type": "corner", "start_m": 5360, "end_m": 5430, "apex_m": 5395},
        {"turn": "17", "name": "Turn 17", "type": "corner", "start_m": 6080, "end_m": 6180, "apex_m": 6140},
    ]
    vegas_sectors = [
        {"sector": 1, "lap_dist_m": 0.0},
        {"sector": 2, "lap_dist_m": 1703.8},
        {"sector": 3, "lap_dist_m": 3376.5},
    ]
    generate_track_from_capture(
        vegas_capture,
        car_idx=4,
        track_name="Las Vegas",
        track_length_m=6200.0,
        sectors=vegas_sectors,
        sections=vegas_sections,
        out_filenames=["f1-25_las-vegas.json"],
        orientation=0.0,
    )

    # 2. Miami (Track ID 30)
    miami_capture = str(base_dir / "captures" / "capture_20261103_121941_0000000000000000.f1udp")
    miami_sections = [
        {"turn": "1", "name": "Turn 1", "type": "corner", "start_m": 100, "end_m": 220, "apex_m": 160},
        {"turn": "2", "name": "Turn 2", "type": "corner", "start_m": 280, "end_m": 360, "apex_m": 320},
        {"turn": "3", "name": "Turn 3", "type": "corner", "start_m": 380, "end_m": 460, "apex_m": 420},
        {"turn": "4", "name": "Turn 4", "type": "corner", "start_m": 520, "end_m": 620, "apex_m": 570},
        {"turn": "5", "name": "Turn 5", "type": "corner", "start_m": 670, "end_m": 760, "apex_m": 710},
        {"turn": "6", "name": "Turn 6", "type": "corner", "start_m": 800, "end_m": 920, "apex_m": 860},
        {"turn": "7", "name": "Turn 7", "type": "corner", "start_m": 950, "end_m": 1150, "apex_m": 1050},
        {"turn": "8", "name": "Turn 8", "type": "corner", "start_m": 1200, "end_m": 1350, "apex_m": 1280},
        {"turn": "9", "name": "Turn 9", "type": "corner", "start_m": 1700, "end_m": 1820, "apex_m": 1760},
        {"turn": "10", "name": "Turn 10", "type": "corner", "start_m": 1850, "end_m": 1950, "apex_m": 1900},
        {"turn": "11", "name": "Turn 11", "type": "corner", "start_m": 2100, "end_m": 2220, "apex_m": 2160},
        {"turn": "12", "name": "Turn 12", "type": "corner", "start_m": 2240, "end_m": 2340, "apex_m": 2290},
        {"turn": "13", "name": "Turn 13", "type": "corner", "start_m": 2360, "end_m": 2450, "apex_m": 2400},
        {"turn": "14", "name": "Turn 14", "type": "corner", "start_m": 2480, "end_m": 2560, "apex_m": 2520},
        {"turn": "15", "name": "Turn 15", "type": "corner", "start_m": 2580, "end_m": 2680, "apex_m": 2630},
        {"turn": "16", "name": "Turn 16", "type": "corner", "start_m": 2750, "end_m": 2900, "apex_m": 2820},
        {"turn": "17", "name": "Turn 17", "type": "corner", "start_m": 4200, "end_m": 4350, "apex_m": 4280},
        {"turn": "18", "name": "Turn 18", "type": "corner", "start_m": 4900, "end_m": 5050, "apex_m": 4980},
        {"turn": "19", "name": "Turn 19", "type": "corner", "start_m": 5100, "end_m": 5250, "apex_m": 5180},
    ]
    miami_sectors = [
        {"sector": 1, "lap_dist_m": 0.0},
        {"sector": 2, "lap_dist_m": 1780.0},
        {"sector": 3, "lap_dist_m": 3610.0},
    ]
    generate_track_from_capture(
        miami_capture,
        car_idx=5,
        track_name="Miami",
        track_length_m=5412.0,
        sectors=miami_sectors,
        sections=miami_sections,
        out_filenames=["f1-25_miami.json"],
        orientation=0.0,
    )


if __name__ == "__main__":
    main()
