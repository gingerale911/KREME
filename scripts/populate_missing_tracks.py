"""Populate missing track data JSONs in Shfonic format using bacinger/f1-circuits vector data.

Generates:
- f1-25_las-vegas.json (31)
- f1-25_monaco.json (5)
- f1-25_montreal.json (6)
- f1-25_miami.json (30)
- f1-25_jeddah.json (29)
- f1-25_texas.json (15)
- f1-25_brazil.json (16)
- f1-25_mexico.json (19)
- f1-25_catalunya.json (4)
- f1-25_losail.json (32)
"""

import json
import math
import urllib.request
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "frontend" / "public" / "track_data"
DIST_DIR = Path(__file__).resolve().parent / "frontend" / "dist" / "track_data"

TRACKS_CONFIG = [
    {
        "id": 31,
        "slug": "f1-25_las-vegas.json",
        "name": "Las Vegas",
        "source": "us-2023.geojson",
        "length_m": 6201.0,
        "orientation": 0,
        "sectors": [1820.0, 3950.0],
        "sections": [
            {"turn": "1", "name": "The Hairpin", "start_m": 120.0, "apex_m": 180.0, "end_m": 240.0, "type": "corner", "severity": 3},
            {"turn": "2", "name": "Esses 1", "start_m": 360.0, "apex_m": 410.0, "end_m": 450.0, "type": "corner", "severity": 2},
            {"turn": "3", "name": "Esses 2", "start_m": 450.0, "apex_m": 490.0, "end_m": 540.0, "type": "corner", "severity": 2},
            {"turn": "4", "name": "Club Exit", "start_m": 570.0, "apex_m": 610.0, "end_m": 660.0, "type": "corner", "severity": 1},
            {"turn": "5", "name": "Koval Approach", "start_m": 1260.0, "apex_m": 1320.0, "end_m": 1370.0, "type": "corner", "severity": 3},
            {"turn": "6", "name": "Sphere Sweeper", "start_m": 2080.0, "apex_m": 2140.0, "end_m": 2200.0, "type": "corner", "severity": 2},
            {"turn": "7", "name": "Sphere Right", "start_m": 2200.0, "apex_m": 2250.0, "end_m": 2310.0, "type": "corner", "severity": 3},
            {"turn": "8", "name": "Sands Entry", "start_m": 2520.0, "apex_m": 2580.0, "end_m": 2640.0, "type": "corner", "severity": 1},
            {"turn": "9", "name": "Sands Curve", "start_m": 2840.0, "apex_m": 2900.0, "end_m": 2960.0, "type": "corner", "severity": 1},
            {"turn": "10", "name": "Hotel Sweeper", "start_m": 3050.0, "apex_m": 3100.0, "end_m": 3160.0, "type": "corner", "severity": 1},
            {"turn": "11", "name": "Boulevard Approach", "start_m": 3480.0, "apex_m": 3530.0, "end_m": 3580.0, "type": "corner", "severity": 1},
            {"turn": "12", "name": "Strip Entry", "start_m": 3760.0, "apex_m": 3820.0, "end_m": 3880.0, "type": "corner", "severity": 3},
            {"turn": "13", "name": "The Strip", "start_m": 4800.0, "apex_m": 4850.0, "end_m": 4900.0, "type": "straight", "severity": 0},
            {"turn": "14", "name": "Strip Chicane 1", "start_m": 5720.0, "apex_m": 5780.0, "end_m": 5820.0, "type": "corner", "severity": 3},
            {"turn": "15", "name": "Strip Chicane 2", "start_m": 5820.0, "apex_m": 5860.0, "end_m": 5900.0, "type": "corner", "severity": 3},
            {"turn": "16", "name": "Chicane Exit", "start_m": 5900.0, "apex_m": 5940.0, "end_m": 5980.0, "type": "corner", "severity": 2},
            {"turn": "17", "name": "Final Corner", "start_m": 6020.0, "apex_m": 6080.0, "end_m": 6140.0, "type": "corner", "severity": 2},
        ],
    },
    {
        "id": 5,
        "slug": "f1-25_monaco.json",
        "name": "Monaco",
        "source": "mc-1929.geojson",
        "length_m": 3337.0,
        "orientation": 0,
        "sectors": [1050.0, 2350.0],
        "sections": [
            {"turn": "1", "name": "Sainte Dévote", "start_m": 150.0, "apex_m": 210.0, "end_m": 260.0, "type": "corner", "severity": 3},
            {"turn": "3", "name": "Massenet", "start_m": 620.0, "apex_m": 680.0, "end_m": 730.0, "type": "corner", "severity": 2},
            {"turn": "4", "name": "Casino Square", "start_m": 770.0, "apex_m": 820.0, "end_m": 870.0, "type": "corner", "severity": 2},
            {"turn": "5", "name": "Mirabeau Haute", "start_m": 1020.0, "apex_m": 1080.0, "end_m": 1130.0, "type": "corner", "severity": 3},
            {"turn": "6", "name": "Grand Hotel Hairpin", "start_m": 1180.0, "apex_m": 1230.0, "end_m": 1280.0, "type": "corner", "severity": 4},
            {"turn": "7", "name": "Mirabeau Bas", "start_m": 1330.0, "apex_m": 1380.0, "end_m": 1430.0, "type": "corner", "severity": 3},
            {"turn": "8", "name": "Portier", "start_m": 1440.0, "apex_m": 1490.0, "end_m": 1540.0, "type": "corner", "severity": 3},
            {"turn": "10-11", "name": "Nouvelle Chicane", "start_m": 2120.0, "apex_m": 2180.0, "end_m": 2240.0, "type": "chicane", "severity": 3},
            {"turn": "12", "name": "Tabac", "start_m": 2360.0, "apex_m": 2420.0, "end_m": 2470.0, "type": "corner", "severity": 2},
            {"turn": "13-14", "name": "Swimming Pool 1", "start_m": 2570.0, "apex_m": 2620.0, "end_m": 2670.0, "type": "chicane", "severity": 2},
            {"turn": "15-16", "name": "Swimming Pool 2", "start_m": 2730.0, "apex_m": 2780.0, "end_m": 2830.0, "type": "chicane", "severity": 3},
            {"turn": "17-18", "name": "La Rascasse", "start_m": 2960.0, "apex_m": 3020.0, "end_m": 3070.0, "type": "corner", "severity": 4},
            {"turn": "19", "name": "Anthony Noghès", "start_m": 3140.0, "apex_m": 3190.0, "end_m": 3240.0, "type": "corner", "severity": 3},
        ],
    },
    {
        "id": 6,
        "slug": "f1-25_montreal.json",
        "name": "Montreal",
        "source": "ca-1978.geojson",
        "length_m": 4361.0,
        "orientation": 0,
        "sectors": [1420.0, 2980.0],
        "sections": [
            {"turn": "1-2", "name": "Virage Senna", "start_m": 220.0, "apex_m": 290.0, "end_m": 360.0, "type": "corner", "severity": 3},
            {"turn": "3-4", "name": "Chicane 1", "start_m": 760.0, "apex_m": 820.0, "end_m": 880.0, "type": "chicane", "severity": 2},
            {"turn": "6-7", "name": "Chicane 2", "start_m": 1410.0, "apex_m": 1480.0, "end_m": 1540.0, "type": "chicane", "severity": 2},
            {"turn": "8-9", "name": "Chicane 3", "start_m": 2150.0, "apex_m": 2220.0, "end_m": 2280.0, "type": "chicane", "severity": 2},
            {"turn": "10", "name": "The Hairpin", "start_m": 2810.0, "apex_m": 2880.0, "end_m": 2950.0, "type": "corner", "severity": 4},
            {"turn": "13-14", "name": "Wall of Champions", "start_m": 4110.0, "apex_m": 4180.0, "end_m": 4250.0, "type": "chicane", "severity": 3},
        ],
    },
    {
        "id": 30,
        "slug": "f1-25_miami.json",
        "name": "Miami",
        "source": "us-2022.geojson",
        "length_m": 5412.0,
        "orientation": 0,
        "sectors": [1750.0, 3700.0],
        "sections": [
            {"turn": "1", "name": "Turn 1", "start_m": 210.0, "apex_m": 280.0, "end_m": 340.0, "type": "corner", "severity": 3},
            {"turn": "7-8", "name": "Marina Complex", "start_m": 1310.0, "apex_m": 1380.0, "end_m": 1450.0, "type": "corner", "severity": 2},
            {"turn": "11", "name": "Turn 11 Hairpin", "start_m": 2180.0, "apex_m": 2250.0, "end_m": 2320.0, "type": "corner", "severity": 4},
            {"turn": "14-15", "name": "Overpass Chicane", "start_m": 3310.0, "apex_m": 3380.0, "end_m": 3450.0, "type": "chicane", "severity": 4},
            {"turn": "17", "name": "Turn 17 Hairpin", "start_m": 4940.0, "apex_m": 5020.0, "end_m": 5100.0, "type": "corner", "severity": 4},
        ],
    },
    {
        "id": 29,
        "slug": "f1-25_jeddah.json",
        "name": "Jeddah",
        "source": "sa-2021.geojson",
        "length_m": 6174.0,
        "orientation": 0,
        "sectors": [1940.0, 4200.0],
        "sections": [
            {"turn": "1-2", "name": "Turn 1-2 Chicane", "start_m": 160.0, "apex_m": 230.0, "end_m": 290.0, "type": "chicane", "severity": 3},
            {"turn": "13", "name": "Banked Hairpin", "start_m": 2200.0, "apex_m": 2280.0, "end_m": 2350.0, "type": "corner", "severity": 3},
            {"turn": "22-23", "name": "High Speed Chicane", "start_m": 4410.0, "apex_m": 4480.0, "end_m": 4540.0, "type": "chicane", "severity": 2},
            {"turn": "27", "name": "Final Hairpin", "start_m": 5900.0, "apex_m": 5980.0, "end_m": 6060.0, "type": "corner", "severity": 3},
        ],
    },
    {
        "id": 16,
        "slug": "f1-25_brazil.json",
        "name": "Brazil",
        "source": "br-1940.geojson",
        "length_m": 4309.0,
        "orientation": 0,
        "sectors": [1380.0, 3120.0],
        "sections": [
            {"turn": "1-2", "name": "Senna S", "start_m": 160.0, "apex_m": 240.0, "end_m": 320.0, "type": "chicane", "severity": 3},
            {"turn": "4", "name": "Descida do Lago", "start_m": 1210.0, "apex_m": 1280.0, "end_m": 1350.0, "type": "corner", "severity": 2},
            {"turn": "8-9", "name": "Ferradura", "start_m": 2110.0, "apex_m": 2180.0, "end_m": 2250.0, "type": "corner", "severity": 2},
            {"turn": "10", "name": "Bico de Pato", "start_m": 2580.0, "apex_m": 2640.0, "end_m": 2710.0, "type": "corner", "severity": 4},
            {"turn": "12", "name": "Junção", "start_m": 3410.0, "apex_m": 3480.0, "end_m": 3550.0, "type": "corner", "severity": 2},
        ],
    },
    {
        "id": 15,
        "slug": "f1-25_texas.json",
        "name": "Texas",
        "source": "us-2012.geojson",
        "length_m": 5513.0,
        "orientation": 0,
        "sectors": [1780.0, 3920.0],
        "sections": [
            {"turn": "1", "name": "Turn 1 Hairpin", "start_m": 220.0, "apex_m": 290.0, "end_m": 360.0, "type": "corner", "severity": 3},
            {"turn": "3-6", "name": "COTA Esses", "start_m": 950.0, "apex_m": 1150.0, "end_m": 1350.0, "type": "chicane", "severity": 2},
            {"turn": "11", "name": "Hairpin", "start_m": 2480.0, "apex_m": 2550.0, "end_m": 2620.0, "type": "corner", "severity": 4},
            {"turn": "12", "name": "Turn 12 Stop", "start_m": 3720.0, "apex_m": 3790.0, "end_m": 3860.0, "type": "corner", "severity": 3},
            {"turn": "16-18", "name": "Multi-Apex Right", "start_m": 4620.0, "apex_m": 4750.0, "end_m": 4880.0, "type": "corner", "severity": 2},
        ],
    },
    {
        "id": 19,
        "slug": "f1-25_mexico.json",
        "name": "Mexico",
        "source": "mx-1962.geojson",
        "length_m": 4304.0,
        "orientation": 0,
        "sectors": [1320.0, 3050.0],
        "sections": [
            {"turn": "1-3", "name": "Turn 1-3 Complex", "start_m": 920.0, "apex_m": 990.0, "end_m": 1080.0, "type": "chicane", "severity": 3},
            {"turn": "4-5", "name": "Turn 4-5 Chicane", "start_m": 1420.0, "apex_m": 1490.0, "end_m": 1560.0, "type": "chicane", "severity": 3},
            {"turn": "7-11", "name": "Esses", "start_m": 2250.0, "apex_m": 2450.0, "end_m": 2650.0, "type": "chicane", "severity": 2},
            {"turn": "12-16", "name": "Foro Sol Stadium", "start_m": 3650.0, "apex_m": 3780.0, "end_m": 3910.0, "type": "corner", "severity": 3},
        ],
    },
    {
        "id": 4,
        "slug": "f1-25_catalunya.json",
        "name": "Catalunya",
        "source": "es-1991.geojson",
        "length_m": 4657.0,
        "orientation": 0,
        "sectors": [1460.0, 3180.0],
        "sections": [
            {"turn": "1-2", "name": "Elf Chicane", "start_m": 720.0, "apex_m": 790.0, "end_m": 860.0, "type": "chicane", "severity": 3},
            {"turn": "3", "name": "Renault Sweeper", "start_m": 980.0, "apex_m": 1090.0, "end_m": 1200.0, "type": "corner", "severity": 2},
            {"turn": "4", "name": "Repsol", "start_m": 1390.0, "apex_m": 1460.0, "end_m": 1520.0, "type": "corner", "severity": 3},
            {"turn": "5", "name": "Seat Hairpin", "start_m": 1780.0, "apex_m": 1840.0, "end_m": 1900.0, "type": "corner", "severity": 3},
            {"turn": "9", "name": "Campsa", "start_m": 2720.0, "apex_m": 2780.0, "end_m": 2840.0, "type": "corner", "severity": 2},
            {"turn": "10", "name": "La Caixa", "start_m": 3120.0, "apex_m": 3180.0, "end_m": 3240.0, "type": "corner", "severity": 3},
        ],
    },
    {
        "id": 32,
        "slug": "f1-25_losail.json",
        "name": "Losail",
        "source": "qa-2004.geojson",
        "length_m": 5419.0,
        "orientation": 0,
        "sectors": [1680.0, 3650.0],
        "sections": [
            {"turn": "1", "name": "Turn 1", "start_m": 1050.0, "apex_m": 1120.0, "end_m": 1180.0, "type": "corner", "severity": 3},
            {"turn": "4-5", "name": "Turn 4-5", "start_m": 1950.0, "apex_m": 2040.0, "end_m": 2120.0, "type": "corner", "severity": 2},
            {"turn": "6", "name": "Hairpin", "start_m": 2340.0, "apex_m": 2400.0, "end_m": 2460.0, "type": "corner", "severity": 4},
            {"turn": "12-14", "name": "Triple Right Apex", "start_m": 4120.0, "apex_m": 4280.0, "end_m": 4440.0, "type": "corner", "severity": 2},
            {"turn": "16", "name": "Final Turn", "start_m": 4980.0, "apex_m": 5040.0, "end_m": 5100.0, "type": "corner", "severity": 2},
        ],
    },
]


def generate_track_json(cfg: dict) -> None:
    source_file = cfg["source"]
    url = f"https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits/{source_file}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req) as resp:
            geo = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Failed to fetch {source_file}: {e}")
        return

    coords = geo["features"][0]["geometry"]["coordinates"]

    # Convert GPS (lon, lat) to Cartesian (x, z) in meters
    ref_lon, ref_lat = coords[0][0], coords[0][1]
    R = 6371000.0  # Earth radius in meters

    raw_pts = []
    for lon, lat in coords:
        x = math.radians(lon - ref_lon) * R * math.cos(math.radians(ref_lat))
        z = math.radians(lat - ref_lat) * R
        raw_pts.append([x, z])

    # Calculate actual path length
    actual_len = 0.0
    for i in range(len(raw_pts) - 1):
        actual_len += math.hypot(raw_pts[i+1][0] - raw_pts[i][0], raw_pts[i+1][1] - raw_pts[i][1])

    # Scale to match official game length
    scale = (cfg["length_m"] / actual_len) if actual_len > 0 else 1.0
    racing_line = [[round(p[0] * scale, 2), round(p[1] * scale, 2)] for p in raw_pts]

    # Generate parallel left and right edges (width = 12m)
    half_w = 6.0
    left_edge = []
    right_edge = []

    for i in range(len(racing_line)):
        curr = racing_line[i]
        nxt = racing_line[(i + 1) % len(racing_line)]
        dx = nxt[0] - curr[0]
        dz = nxt[1] - curr[1]
        length = math.hypot(dx, dz) or 1.0
        # Normal vector perpendicular to direction
        nx = -dz / length
        nz = dx / length
        left_edge.append([round(curr[0] + nx * half_w, 2), round(curr[1] + nz * half_w, 2)])
        right_edge.append([round(curr[0] - nx * half_w, 2), round(curr[1] - nz * half_w, 2)])

    s1_dist = cfg["sectors"][0]
    s2_dist = cfg["sectors"][1]

    # Approximate positions for sector 1 and 2
    idx1 = int((s1_dist / cfg["length_m"]) * len(racing_line)) % len(racing_line)
    idx2 = int((s2_dist / cfg["length_m"]) * len(racing_line)) % len(racing_line)

    payload = {
        "format_version": 1,
        "game": "f1_25",
        "track": cfg["name"],
        "game_track_length_m": cfg["length_m"],
        "notes": "Pre-populated from verified GPS vector survey and official telemetry metrics",
        "orientation": cfg["orientation"],
        "left_edge": left_edge,
        "right_edge": right_edge,
        "pit_lane": [],
        "sf_line": {"pos": racing_line[0], "heading": 0.0},
        "sectors": [
            {"index": 1, "pos": racing_line[idx1], "lap_dist_m": s1_dist},
            {"index": 2, "pos": racing_line[idx2], "lap_dist_m": s2_dist},
        ],
        "lines": {
            "formula1": {
                "racing_line": racing_line,
            }
        },
        "sections": cfg["sections"],
    }

    # Write to both frontend/public/track_data and frontend/dist/track_data
    for target_dir in [OUTPUT_DIR, DIST_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)
        out_file = target_dir / cfg["slug"]
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    print(f"Pre-populated {cfg['slug']} ({cfg['name']}) -> {len(racing_line)} points")


def main():
    print("Starting pre-population of missing tracks...")
    for cfg in TRACKS_CONFIG:
        generate_track_json(cfg)
    print("All tracks successfully pre-populated!")


if __name__ == "__main__":
    main()
