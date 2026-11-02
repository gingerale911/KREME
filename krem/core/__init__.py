"""KREM core constants — packet IDs, sizes, enumerations, track IDs.

All values verified against the EA F1 25 UDP spec (format 2025)
and cross-checked via struct-size rebuild (16/16 match, see plan Appendix A).
"""

from __future__ import annotations

import struct
from enum import IntEnum
from typing import Final

# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------
PACKET_FORMAT: Final[int] = 2025
GAME_YEAR: Final[int] = 25
DEFAULT_UDP_PORT: Final[int] = 20777
MAX_CARS: Final[int] = 22
ENDIAN: Final[str] = "<"  # little-endian, packed, no padding

# ---------------------------------------------------------------------------
# Packet IDs
# ---------------------------------------------------------------------------

class PacketId(IntEnum):
    MOTION = 0
    SESSION = 1
    LAP_DATA = 2
    EVENT = 3
    PARTICIPANTS = 4
    CAR_SETUPS = 5
    CAR_TELEMETRY = 6
    CAR_STATUS = 7
    FINAL_CLASSIFICATION = 8
    LOBBY_INFO = 9
    CAR_DAMAGE = 10
    SESSION_HISTORY = 11
    TYRE_SETS = 12
    MOTION_EX = 13
    TIME_TRIAL = 14
    LAP_POSITIONS = 15


# ---------------------------------------------------------------------------
# Published packet sizes (bytes) — verified 16/16 (plan Appendix A)
# ---------------------------------------------------------------------------

PACKET_SIZES: dict[int, int] = {
    PacketId.MOTION: 1349,
    PacketId.SESSION: 753,
    PacketId.LAP_DATA: 1285,
    PacketId.EVENT: 45,
    PacketId.PARTICIPANTS: 1284,
    PacketId.CAR_SETUPS: 1133,
    PacketId.CAR_TELEMETRY: 1352,
    PacketId.CAR_STATUS: 1239,
    PacketId.FINAL_CLASSIFICATION: 1042,
    PacketId.LOBBY_INFO: 954,
    PacketId.CAR_DAMAGE: 1041,
    PacketId.SESSION_HISTORY: 1460,
    PacketId.TYRE_SETS: 231,
    PacketId.MOTION_EX: 273,
    PacketId.TIME_TRIAL: 101,
    PacketId.LAP_POSITIONS: 1131,
}

# ---------------------------------------------------------------------------
# Header layout — 29 bytes
# u16 packetFormat · u8 gameYear · u8 gameMajorVersion · u8 gameMinorVersion
# u8 packetVersion · u8 packetId · u64 sessionUID · f32 sessionTime
# u32 frameIdentifier · u32 overallFrameIdentifier
# u8 playerCarIndex · u8 secondaryPlayerCarIndex
# ---------------------------------------------------------------------------

HEADER_FORMAT: Final[str] = f"{ENDIAN}HBBBBBQfIIBB"
HEADER_SIZE: Final[int] = struct.calcsize(HEADER_FORMAT)  # 29

assert HEADER_SIZE == 29, f"Header size mismatch: {HEADER_SIZE}"

# Named indices into the header tuple
class HeaderField(IntEnum):
    PACKET_FORMAT = 0
    GAME_YEAR = 1
    GAME_MAJOR_VERSION = 2
    GAME_MINOR_VERSION = 3
    PACKET_VERSION = 4
    PACKET_ID = 5
    SESSION_UID = 6
    SESSION_TIME = 7
    FRAME_IDENTIFIER = 8
    OVERALL_FRAME_IDENTIFIER = 9
    PLAYER_CAR_INDEX = 10
    SECONDARY_PLAYER_CAR_INDEX = 11


# ---------------------------------------------------------------------------
# Track IDs (2025 format only — id 42 Madrid is 2026 format only)
# ---------------------------------------------------------------------------

TRACK_NAMES: dict[int, str] = {
    0: "Melbourne",
    2: "Shanghai",
    3: "Sakhir",
    4: "Catalunya",
    5: "Monaco",
    6: "Montreal",
    7: "Silverstone",
    9: "Hungaroring",
    10: "Spa",
    11: "Monza",
    12: "Singapore",
    13: "Suzuka",
    14: "Abu Dhabi",
    15: "Texas",
    16: "Brazil",
    17: "Austria",
    19: "Mexico",
    20: "Baku",
    26: "Zandvoort",
    27: "Imola",
    29: "Jeddah",
    30: "Miami",
    31: "Las Vegas",
    32: "Losail",
    39: "Silverstone (Rev)",
    40: "Austria (Rev)",
    41: "Zandvoort (Rev)",
}


# ---------------------------------------------------------------------------
# Tyre compounds (F1 Modern)
# ---------------------------------------------------------------------------

class TyreCompoundActual(IntEnum):
    C5 = 16
    C4 = 17
    C3 = 18
    C2 = 19
    C1 = 20
    C0 = 21
    C6 = 22
    INTER = 7
    WET = 8


class TyreCompoundVisual(IntEnum):
    SOFT = 16
    MEDIUM = 17
    HARD = 18
    INTER = 7
    WET = 8


TYRE_COMPOUND_NAMES: dict[int, str] = {
    16: "C5 (Soft)", 17: "C4 (Medium)", 18: "C3 (Hard)",
    19: "C2", 20: "C1", 21: "C0", 22: "C6",
    7: "Inter", 8: "Wet",
}

TYRE_VISUAL_NAMES: dict[int, str] = {
    16: "Soft", 17: "Medium", 18: "Hard", 7: "Inter", 8: "Wet",
}

TYRE_VISUAL_COLOURS: dict[int, str] = {
    16: "#FF3333",  # Soft — red
    17: "#FFD700",  # Medium — yellow
    18: "#FFFFFF",  # Hard — white
    7: "#00CC00",   # Inter — green
    8: "#0088FF",   # Wet — blue
}

# ---------------------------------------------------------------------------
# ERS deploy modes
# ---------------------------------------------------------------------------

class ERSDeployMode(IntEnum):
    NONE = 0
    MEDIUM = 1
    HOTLAP = 2
    OVERTAKE = 3


# ---------------------------------------------------------------------------
# Safety car status
# ---------------------------------------------------------------------------

class SafetyCarStatus(IntEnum):
    NONE = 0
    FULL = 1
    VIRTUAL = 2
    FORMATION_LAP = 3


# ---------------------------------------------------------------------------
# FIA flags
# ---------------------------------------------------------------------------

class FIAFlag(IntEnum):
    UNKNOWN = -1
    NONE = 0
    GREEN = 1
    BLUE = 2
    YELLOW = 3


# ---------------------------------------------------------------------------
# Driver status
# ---------------------------------------------------------------------------

class DriverStatus(IntEnum):
    IN_GARAGE = 0
    FLYING_LAP = 1
    IN_LAP = 2
    OUT_LAP = 3
    ON_TRACK = 4


# ---------------------------------------------------------------------------
# Pit status
# ---------------------------------------------------------------------------

class PitStatus(IntEnum):
    NONE = 0
    PITTING = 1
    IN_PIT_AREA = 2


# ---------------------------------------------------------------------------
# Result status
# ---------------------------------------------------------------------------

class ResultStatus(IntEnum):
    INVALID = 0
    INACTIVE = 1
    ACTIVE = 2
    FINISHED = 3
    DNF = 4
    DISQUALIFIED = 5
    NOT_CLASSIFIED = 6
    RETIRED = 7


# ---------------------------------------------------------------------------
# Surface types
# ---------------------------------------------------------------------------

class SurfaceType(IntEnum):
    TARMAC = 0
    RUMBLE_STRIP = 1
    CONCRETE = 2
    ROCK = 3
    GRAVEL = 4
    MUD = 5
    SAND = 6
    GRASS = 7
    WATER = 8
    COBBLESTONE = 9
    METAL = 10
    RIDGED = 11


# Off-track surfaces
OFF_TRACK_SURFACES: frozenset[int] = frozenset({
    SurfaceType.GRAVEL,
    SurfaceType.MUD,
    SurfaceType.SAND,
    SurfaceType.GRASS,
})

KERB_SURFACES: frozenset[int] = frozenset({
    SurfaceType.RUMBLE_STRIP,
    SurfaceType.RIDGED,
})


# ---------------------------------------------------------------------------
# Formula type
# ---------------------------------------------------------------------------

class Formula(IntEnum):
    F1_MODERN = 0
    F1_CLASSIC = 1
    F2 = 2
    F1_GENERIC = 3
    BETA = 4
    ESPORTS = 6
    F1_WORLD = 8
    F1_ELIMINATION = 9


# ---------------------------------------------------------------------------
# Session type
# ---------------------------------------------------------------------------

class SessionType(IntEnum):
    UNKNOWN = 0
    P1 = 1
    P2 = 2
    P3 = 3
    SHORT_P = 4
    Q1 = 5
    Q2 = 6
    Q3 = 7
    SHORT_Q = 8
    OSQ = 9
    SPRINT_SHOOTOUT_1 = 10
    SPRINT_SHOOTOUT_2 = 11
    SPRINT_SHOOTOUT_3 = 12
    SHORT_SPRINT_SHOOTOUT = 13
    SPRINT = 14
    R = 15
    R2 = 16
    R3 = 17
    TIME_TRIAL = 18


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

class Weather(IntEnum):
    CLEAR = 0
    LIGHT_CLOUD = 1
    OVERCAST = 2
    LIGHT_RAIN = 3
    HEAVY_RAIN = 4
    STORM = 5


# Weather buckets for reference lap matching (plan §7.2)
DRY_WEATHER: frozenset[int] = frozenset({0, 1, 2})
WET_WEATHER: frozenset[int] = frozenset({3, 4, 5})


# ---------------------------------------------------------------------------
# Event string codes
# ---------------------------------------------------------------------------

EVENT_CODES: dict[str, str] = {
    "SSTA": "Session Started",
    "SEND": "Session Ended",
    "FTLP": "Fastest Lap",
    "RTMT": "Retirement",
    "DRSE": "DRS Enabled",
    "DRSD": "DRS Disabled",
    "TMPT": "Team Mate in Pits",
    "CHQF": "Chequered Flag",
    "RCWN": "Race Winner",
    "PENA": "Penalty",
    "SPTP": "Speed Trap",
    "STLG": "Start Lights",
    "LGOT": "Lights Out",
    "DTSV": "Drive Through Served",
    "SGSV": "Stop Go Served",
    "FLBK": "Flashback",
    "BUTN": "Button Status",
    "RDFL": "Red Flag",
    "OVTK": "Overtake",
    "SCAR": "Safety Car",
    "COLL": "Collision",
}


# ---------------------------------------------------------------------------
# Wheel order (all wheel arrays)
# ---------------------------------------------------------------------------

class WheelIndex(IntEnum):
    RL = 0  # Rear Left
    RR = 1  # Rear Right
    FL = 2  # Front Left
    FR = 3  # Front Right


WHEEL_NAMES: tuple[str, ...] = ("RL", "RR", "FL", "FR")


# ---------------------------------------------------------------------------
# Sector display colours (plan §8 Panel 2)
# ---------------------------------------------------------------------------

COLOUR_PURPLE: Final[str] = "#A855F7"
COLOUR_GREEN: Final[str] = "#22C55E"
COLOUR_RED: Final[str] = "#EF4444"
COLOUR_GREY: Final[str] = "#6B7280"


# ---------------------------------------------------------------------------
# Packets consumed by the dashboard (plan §2.4)
# ---------------------------------------------------------------------------

CONSUMED_PACKET_IDS: frozenset[int] = frozenset({
    PacketId.MOTION,
    PacketId.SESSION,
    PacketId.LAP_DATA,
    PacketId.EVENT,
    PacketId.PARTICIPANTS,
    PacketId.CAR_SETUPS,
    PacketId.CAR_TELEMETRY,
    PacketId.CAR_STATUS,
    PacketId.CAR_DAMAGE,
    PacketId.SESSION_HISTORY,
    PacketId.TYRE_SETS,
    PacketId.MOTION_EX,
    PacketId.TIME_TRIAL,
})

# Packets sent at menu rate (join on m_overallFrameIdentifier)
MENU_RATE_PACKET_IDS: frozenset[int] = frozenset({
    PacketId.MOTION,
    PacketId.LAP_DATA,
    PacketId.CAR_TELEMETRY,
    PacketId.CAR_STATUS,
    PacketId.MOTION_EX,
})
