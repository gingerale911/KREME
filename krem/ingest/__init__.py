"""KREM decoder — numpy-based zero-copy packet parser for F1 25 UDP format 2025.

Every struct layout is built from the official EA spec (verified 16/16 sizes match).
Decodes raw datagrams into structured numpy arrays for fast downstream access.

Wire rules (plan §2.2):
- Little-endian, packed, no padding
- Wheel arrays: 0=RL, 1=RR, 2=FL, 3=FR
- 22 car slots per array packet
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from krem.core import (
    ENDIAN,
    HEADER_FORMAT,
    HEADER_SIZE,
    PACKET_SIZES,
    HeaderField,
    PacketId,
)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PacketHeader:
    """Decoded 29-byte UDP header."""
    packet_format: int
    game_year: int
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int
    secondary_player_car_index: int

    @classmethod
    def from_bytes(cls, data: bytes) -> PacketHeader:
        vals = struct.unpack_from(HEADER_FORMAT, data, 0)
        return cls(*vals)


# ---------------------------------------------------------------------------
# Numpy dtypes for each per-car struct
# ---------------------------------------------------------------------------

# CarMotionData — 60 bytes per car
DT_CAR_MOTION = np.dtype([
    ("worldPositionX", "<f4"),
    ("worldPositionY", "<f4"),
    ("worldPositionZ", "<f4"),
    ("worldVelocityX", "<f4"),
    ("worldVelocityY", "<f4"),
    ("worldVelocityZ", "<f4"),
    ("worldForwardDirX", "<i2"),
    ("worldForwardDirY", "<i2"),
    ("worldForwardDirZ", "<i2"),
    ("worldRightDirX", "<i2"),
    ("worldRightDirY", "<i2"),
    ("worldRightDirZ", "<i2"),
    ("gForceLateral", "<f4"),
    ("gForceLongitudinal", "<f4"),
    ("gForceVertical", "<f4"),
    ("yaw", "<f4"),
    ("pitch", "<f4"),
    ("roll", "<f4"),
])
assert DT_CAR_MOTION.itemsize == 60

# LapData — 57 bytes per car
DT_LAP_DATA = np.dtype([
    ("lastLapTimeInMS", "<u4"),
    ("currentLapTimeInMS", "<u4"),
    ("sector1TimeMSPart", "<u2"),
    ("sector1TimeMinutesPart", "<u1"),
    ("sector2TimeMSPart", "<u2"),
    ("sector2TimeMinutesPart", "<u1"),
    ("deltaToCarInFrontMSPart", "<u2"),
    ("deltaToCarInFrontMinutesPart", "<u1"),
    ("deltaToRaceLeaderMSPart", "<u2"),
    ("deltaToRaceLeaderMinutesPart", "<u1"),
    ("lapDistance", "<f4"),
    ("totalDistance", "<f4"),
    ("safetyCarDelta", "<f4"),
    ("carPosition", "<u1"),
    ("currentLapNum", "<u1"),
    ("pitStatus", "<u1"),
    ("numPitStops", "<u1"),
    ("sector", "<u1"),
    ("currentLapInvalid", "<u1"),
    ("penalties", "<u1"),
    ("totalWarnings", "<u1"),
    ("cornerCuttingWarnings", "<u1"),
    ("numUnservedDriveThroughPens", "<u1"),
    ("numUnservedStopGoPens", "<u1"),
    ("gridPosition", "<u1"),
    ("driverStatus", "<u1"),
    ("resultStatus", "<u1"),
    ("pitLaneTimerActive", "<u1"),
    ("pitLaneTimeInLaneInMS", "<u2"),
    ("pitStopTimerInMS", "<u2"),
    ("pitStopShouldServePen", "<u1"),
    ("speedTrapFastestSpeed", "<f4"),
    ("speedTrapFastestLap", "<u1"),
])
assert DT_LAP_DATA.itemsize == 57

# CarTelemetryData — 60 bytes per car
DT_CAR_TELEMETRY = np.dtype([
    ("speed", "<u2"),
    ("throttle", "<f4"),
    ("steer", "<f4"),
    ("brake", "<f4"),
    ("clutch", "<u1"),
    ("gear", "<i1"),
    ("engineRPM", "<u2"),
    ("drs", "<u1"),
    ("revLightsPercent", "<u1"),
    ("revLightsBitValue", "<u2"),
    ("brakesTemperature", "<u2", (4,)),
    ("tyresSurfaceTemperature", "<u1", (4,)),
    ("tyresInnerTemperature", "<u1", (4,)),
    ("engineTemperature", "<u2"),
    ("tyresPressure", "<f4", (4,)),
    ("surfaceType", "<u1", (4,)),
])
assert DT_CAR_TELEMETRY.itemsize == 60

# CarStatusData — 55 bytes per car
DT_CAR_STATUS = np.dtype([
    ("tractionControl", "<u1"),
    ("antiLockBrakes", "<u1"),
    ("fuelMix", "<u1"),
    ("frontBrakeBias", "<u1"),
    ("pitLimiterStatus", "<u1"),
    ("fuelInTank", "<f4"),
    ("fuelCapacity", "<f4"),
    ("fuelRemainingLaps", "<f4"),
    ("maxRPM", "<u2"),
    ("idleRPM", "<u2"),
    ("maxGears", "<u1"),
    ("drsAllowed", "<u1"),
    ("drsActivationDistance", "<u2"),
    ("actualTyreCompound", "<u1"),
    ("visualTyreCompound", "<u1"),
    ("tyresAgeLaps", "<u1"),
    ("vehicleFIAFlags", "<i1"),
    ("enginePowerICE", "<f4"),
    ("enginePowerMGUK", "<f4"),
    ("ersStoreEnergy", "<f4"),
    ("ersDeployMode", "<u1"),
    ("ersHarvestedThisLapMGUK", "<f4"),
    ("ersHarvestedThisLapMGUH", "<f4"),
    ("ersDeployedThisLap", "<f4"),
    ("networkPaused", "<u1"),
])
assert DT_CAR_STATUS.itemsize == 55

# CarDamageData — 46 bytes per car
DT_CAR_DAMAGE = np.dtype([
    ("tyresWear", "<f4", (4,)),
    ("tyresDamage", "<u1", (4,)),
    ("brakesDamage", "<u1", (4,)),
    ("tyreBlisters", "<u1", (4,)),
    ("frontLeftWingDamage", "<u1"),
    ("frontRightWingDamage", "<u1"),
    ("rearWingDamage", "<u1"),
    ("floorDamage", "<u1"),
    ("diffuserDamage", "<u1"),
    ("sidepodDamage", "<u1"),
    ("drsFault", "<u1"),
    ("ersFault", "<u1"),
    ("gearBoxDamage", "<u1"),
    ("engineDamage", "<u1"),
    ("engineMGUHWear", "<u1"),
    ("engineESWear", "<u1"),
    ("engineCEWear", "<u1"),
    ("engineICEWear", "<u1"),
    ("engineMGUKWear", "<u1"),
    ("engineTCWear", "<u1"),
    ("engineBlown", "<u1"),
    ("engineSeized", "<u1"),
])
assert DT_CAR_DAMAGE.itemsize == 46

# ParticipantData — 57 bytes per car
DT_PARTICIPANT = np.dtype([
    ("aiControlled", "<u1"),
    ("driverId", "<u1"),
    ("networkId", "<u1"),
    ("teamId", "<u1"),
    ("myTeam", "<u1"),
    ("raceNumber", "<u1"),
    ("nationality", "<u1"),
    ("name", "S32"),
    ("yourTelemetry", "<u1"),
    ("showOnlineNames", "<u1"),
    ("techLevel", "<u2"),
    ("platform", "<u1"),
    ("numColours", "<u1"),
    # 4 × LiveryColour (3 bytes each = 12 bytes)
    ("liveryColours", "<u1", (4, 3)),
])
assert DT_PARTICIPANT.itemsize == 57

# CarSetupData — 50 bytes per car
DT_CAR_SETUP = np.dtype([
    ("frontWing", "<u1"),
    ("rearWing", "<u1"),
    ("onThrottle", "<u1"),
    ("offThrottle", "<u1"),
    ("frontCamber", "<f4"),
    ("rearCamber", "<f4"),
    ("frontToe", "<f4"),
    ("rearToe", "<f4"),
    ("frontSuspension", "<u1"),
    ("rearSuspension", "<u1"),
    ("frontAntiRollBar", "<u1"),
    ("rearAntiRollBar", "<u1"),
    ("frontSuspensionHeight", "<u1"),
    ("rearSuspensionHeight", "<u1"),
    ("brakePressure", "<u1"),
    ("brakeBias", "<u1"),
    ("engineBraking", "<u1"),
    ("rearLeftTyrePressure", "<f4"),
    ("rearRightTyrePressure", "<f4"),
    ("frontLeftTyrePressure", "<f4"),
    ("frontRightTyrePressure", "<f4"),
    ("ballast", "<u1"),
    ("fuelLoad", "<f4"),
])
assert DT_CAR_SETUP.itemsize == 50

# MarshalZone — 5 bytes each
DT_MARSHAL_ZONE = np.dtype([
    ("zoneStart", "<f4"),
    ("zoneFlag", "<i1"),
])
assert DT_MARSHAL_ZONE.itemsize == 5

# WeatherForecastSample — 8 bytes each
DT_WEATHER_FORECAST = np.dtype([
    ("sessionType", "<u1"),
    ("timeOffset", "<u1"),
    ("weather", "<u1"),
    ("trackTemperature", "<i1"),
    ("trackTemperatureChange", "<i1"),
    ("airTemperature", "<i1"),
    ("airTemperatureChange", "<i1"),
    ("rainPercentage", "<u1"),
])
assert DT_WEATHER_FORECAST.itemsize == 8

# LapHistoryData — 14 bytes each
DT_LAP_HISTORY = np.dtype([
    ("lapTimeInMS", "<u4"),
    ("sector1TimeMSPart", "<u2"),
    ("sector1TimeMinutesPart", "<u1"),
    ("sector2TimeMSPart", "<u2"),
    ("sector2TimeMinutesPart", "<u1"),
    ("sector3TimeMSPart", "<u2"),
    ("sector3TimeMinutesPart", "<u1"),
    ("lapValidBitFlags", "<u1"),
])
assert DT_LAP_HISTORY.itemsize == 14

# TyreStintHistoryData — 3 bytes each
DT_TYRE_STINT = np.dtype([
    ("endLap", "<u1"),
    ("tyreActualCompound", "<u1"),
    ("tyreVisualCompound", "<u1"),
])
assert DT_TYRE_STINT.itemsize == 3

# TyreSetData — 10 bytes each
DT_TYRE_SET = np.dtype([
    ("actualTyreCompound", "<u1"),
    ("visualTyreCompound", "<u1"),
    ("wear", "<u1"),
    ("available", "<u1"),
    ("recommendedSession", "<u1"),
    ("lifeSpan", "<u1"),
    ("usableLife", "<u1"),
    ("lapDeltaTime", "<i2"),
    ("fitted", "<u1"),
])
assert DT_TYRE_SET.itemsize == 10

# FinalClassificationData — 46 bytes per car
DT_FINAL_CLASSIFICATION = np.dtype([
    ("position", "<u1"),
    ("numLaps", "<u1"),
    ("gridPosition", "<u1"),
    ("points", "<u1"),
    ("numPitStops", "<u1"),
    ("resultStatus", "<u1"),
    ("resultReason", "<u1"),
    ("bestLapTimeInMS", "<u4"),
    ("totalRaceTime", "<f8"),
    ("penaltiesTime", "<u1"),
    ("numPenalties", "<u1"),
    ("numTyreStints", "<u1"),
    ("tyreStintsActual", "<u1", (8,)),
    ("tyreStintsVisual", "<u1", (8,)),
    ("tyreStintsEndLaps", "<u1", (8,)),
])
assert DT_FINAL_CLASSIFICATION.itemsize == 46

# LobbyInfoData — 42 bytes per car
DT_LOBBY_INFO = np.dtype([
    ("aiControlled", "<u1"),
    ("teamId", "<u1"),
    ("nationality", "<u1"),
    ("platform", "<u1"),
    ("name", "S32"),
    ("carNumber", "<u1"),
    ("yourTelemetry", "<u1"),
    ("showOnlineNames", "<u1"),
    ("techLevel", "<u2"),
    ("readyStatus", "<u1"),
])
assert DT_LOBBY_INFO.itemsize == 42

# TimeTrialDataSet — 24 bytes each
DT_TIME_TRIAL_DATA_SET = np.dtype([
    ("carIdx", "<u1"),
    ("teamId", "<u1"),
    ("lapTimeInMS", "<u4"),
    ("sector1TimeInMS", "<u4"),
    ("sector2TimeInMS", "<u4"),
    ("sector3TimeInMS", "<u4"),
    ("tractionControl", "<u1"),
    ("gearboxAssist", "<u1"),
    ("antiLockBrakes", "<u1"),
    ("equalCarPerformance", "<u1"),
    ("customSetup", "<u1"),
    ("valid", "<u1"),
])
assert DT_TIME_TRIAL_DATA_SET.itemsize == 24


# ---------------------------------------------------------------------------
# MotionEx dtype — 244 bytes payload (player only)
# ---------------------------------------------------------------------------

DT_MOTION_EX = np.dtype([
    ("suspensionPosition", "<f4", (4,)),
    ("suspensionVelocity", "<f4", (4,)),
    ("suspensionAcceleration", "<f4", (4,)),
    ("wheelSpeed", "<f4", (4,)),
    ("wheelSlipRatio", "<f4", (4,)),
    ("wheelSlipAngle", "<f4", (4,)),
    ("wheelLatForce", "<f4", (4,)),
    ("wheelLongForce", "<f4", (4,)),
    ("heightOfCOGAboveGround", "<f4"),
    ("localVelocityX", "<f4"),
    ("localVelocityY", "<f4"),
    ("localVelocityZ", "<f4"),
    ("angularVelocityX", "<f4"),
    ("angularVelocityY", "<f4"),
    ("angularVelocityZ", "<f4"),
    ("angularAccelerationX", "<f4"),
    ("angularAccelerationY", "<f4"),
    ("angularAccelerationZ", "<f4"),
    ("frontWheelsAngle", "<f4"),
    ("wheelVertForce", "<f4", (4,)),
    ("frontAeroHeight", "<f4"),
    ("rearAeroHeight", "<f4"),
    ("frontRollAngle", "<f4"),
    ("rearRollAngle", "<f4"),
    ("chassisYaw", "<f4"),
    ("chassisPitch", "<f4"),
    ("wheelCamber", "<f4", (4,)),
    ("wheelCamberGain", "<f4", (4,)),
])
assert DT_MOTION_EX.itemsize == 244, f"MotionEx payload size: {DT_MOTION_EX.itemsize}"


# ---------------------------------------------------------------------------
# Decoded packet containers
# ---------------------------------------------------------------------------

@dataclass()
class DecodedPacket:
    """A fully decoded F1 25 UDP packet."""
    header: PacketHeader
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decoder functions — one per packet type
# ---------------------------------------------------------------------------

def decode_header(data: bytes) -> PacketHeader:
    """Decode just the 29-byte header."""
    return PacketHeader.from_bytes(data)


def decode_motion(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 0 — Motion: 22 × CarMotionData."""
    cars = np.frombuffer(data, dtype=DT_CAR_MOTION, count=22, offset=HEADER_SIZE)
    return DecodedPacket(header=header, data={"cars": cars})


def decode_session(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 1 — Session: track info, weather, marshal zones, settings."""
    offset = HEADER_SIZE
    fmt = "<bbbBHBbBHH6B"  # weather through numMarshalZones (14 scalar fields)
    # Unpack scalar weather/track fields first
    # weather(u8), trackTemp(i8), airTemp(i8), totalLaps(u8), trackLength(u16),
    # sessionType(u8), trackId(i8), formula(u8), sessionTimeLeft(u16), sessionDuration(u16),
    # pitSpeedLimit(u8), gamePaused(u8), isSpectating(u8), spectatorCarIndex(u8),
    # sliProNativeSupport(u8), numMarshalZones(u8)
    session_fmt = "<BbbBHBbBHHBBBBBB"
    vals = struct.unpack_from(session_fmt, data, offset)
    offset += struct.calcsize(session_fmt)

    result: dict[str, Any] = {
        "weather": vals[0],
        "trackTemperature": vals[1],
        "airTemperature": vals[2],
        "totalLaps": vals[3],
        "trackLength": vals[4],
        "sessionType": vals[5],
        "trackId": vals[6],
        "formula": vals[7],
        "sessionTimeLeft": vals[8],
        "sessionDuration": vals[9],
        "pitSpeedLimit": vals[10],
        "gamePaused": vals[11],
        "isSpectating": vals[12],
        "spectatorCarIndex": vals[13],
        "sliProNativeSupport": vals[14],
        "numMarshalZones": vals[15],
    }

    # Marshal zones: 21 × (f32 zoneStart, i8 zoneFlag)
    marshal_zones = np.frombuffer(data, dtype=DT_MARSHAL_ZONE, count=21, offset=offset)
    result["marshalZones"] = marshal_zones
    offset += 21 * DT_MARSHAL_ZONE.itemsize

    # Safety car + network game + numWeatherForecast
    sc_fmt = "<BBB"
    sc_vals = struct.unpack_from(sc_fmt, data, offset)
    result["safetyCarStatus"] = sc_vals[0]
    result["networkGame"] = sc_vals[1]
    result["numWeatherForecastSamples"] = sc_vals[2]
    offset += struct.calcsize(sc_fmt)

    # Weather forecast: 64 samples
    forecasts = np.frombuffer(data, dtype=DT_WEATHER_FORECAST, count=64, offset=offset)
    result["weatherForecastSamples"] = forecasts
    offset += 64 * DT_WEATHER_FORECAST.itemsize

    # Remaining session fields — unpack as a block
    # forecastAccuracy(u8), aiDifficulty(u8), seasonLinkId(u32), weekendLinkId(u32),
    # sessionLinkId(u32), pitStopWindowIdealLap(u8), pitStopWindowLatestLap(u8),
    # pitStopRejoinPosition(u8), steeringAssist(u8) ... through to sector distances
    rest_fmt = "<BB3I3B11BI4B3B24B2B12Bff"
    rest_vals = struct.unpack_from(rest_fmt, data, offset)

    result["forecastAccuracy"] = rest_vals[0]
    result["aiDifficulty"] = rest_vals[1]
    result["seasonLinkIdentifier"] = rest_vals[2]
    result["weekendLinkIdentifier"] = rest_vals[3]
    result["sessionLinkIdentifier"] = rest_vals[4]
    result["pitStopWindowIdealLap"] = rest_vals[5]
    result["pitStopWindowLatestLap"] = rest_vals[6]
    result["pitStopRejoinPosition"] = rest_vals[7]

    # Assists block
    idx = 8
    assist_names = [
        "steeringAssist", "brakingAssist", "gearboxAssist",
        "pitAssist", "pitReleaseAssist", "ERSAssist", "DRSAssist",
        "dynamicRacingLine", "dynamicRacingLineType", "gameMode", "ruleSet",
    ]
    for name in assist_names:
        result[name] = rest_vals[idx]
        idx += 1

    result["timeOfDay"] = rest_vals[idx]; idx += 1

    settings_names = [
        "sessionLength", "speedUnitsLeadPlayer", "temperatureUnitsLeadPlayer",
        "speedUnitsSecondaryPlayer",
    ]
    for name in settings_names:
        result[name] = rest_vals[idx]
        idx += 1

    more_names = [
        "temperatureUnitsSecondaryPlayer",
        "numSafetyCarPeriods", "numVirtualSafetyCarPeriods",
    ]
    for name in more_names:
        result[name] = rest_vals[idx]
        idx += 1

    # Remaining game settings
    game_settings = [
        "numRedFlagPeriods", "equalCarPerformance", "recoveryMode", "flashbackLimit",
        "surfaceType", "lowFuelMode", "raceStarts", "tyreTemperature",
        "pitLaneTyreSim", "carDamage", "carDamageRate", "collisions",
        "collisionsOffForFirstLapOnly", "mpUnsafePitRelease", "mpOffForGriefing",
        "cornerCuttingStringency", "parcFermeRules", "pitStopExperience",
        "safetyCar", "safetyCarExperience", "formationLap", "formationLapExperience",
        "redFlags", "affectsLicenceLevelSolo",
    ]
    for name in game_settings:
        result[name] = rest_vals[idx]
        idx += 1

    result["affectsLicenceLevelMP"] = rest_vals[idx]; idx += 1
    result["numSessionsInWeekend"] = rest_vals[idx]; idx += 1

    # weekendStructure[12]
    weekend_struct = []
    for _ in range(12):
        weekend_struct.append(rest_vals[idx]); idx += 1
    result["weekendStructure"] = weekend_struct

    result["sector2LapDistanceStart"] = rest_vals[idx]; idx += 1
    result["sector3LapDistanceStart"] = rest_vals[idx]; idx += 1

    return DecodedPacket(header=header, data=result)


def decode_lap_data(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 2 — LapData: 22 × LapData + 2 trailer bytes."""
    cars = np.frombuffer(data, dtype=DT_LAP_DATA, count=22, offset=HEADER_SIZE)
    trailer_offset = HEADER_SIZE + 22 * DT_LAP_DATA.itemsize
    tt_pb, tt_rival = struct.unpack_from("<BB", data, trailer_offset)
    return DecodedPacket(header=header, data={
        "cars": cars,
        "timeTrialPBCarIdx": tt_pb,
        "timeTrialRivalCarIdx": tt_rival,
    })


def decode_event(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 3 — Event: 4-char code + union details."""
    offset = HEADER_SIZE
    code = data[offset:offset + 4].decode("ascii", errors="replace")
    offset += 4
    details: dict[str, Any] = {"code": code}

    # Parse union based on event code
    remaining = data[offset:]
    if code == "FTLP":
        details["vehicleIdx"] = remaining[0]
        details["lapTime"] = struct.unpack_from("<f", remaining, 1)[0]
    elif code in ("RTMT", "TMPT", "RCWN", "DTSV"):
        details["vehicleIdx"] = remaining[0]
        if code == "RTMT" and len(remaining) > 1:
            details["reason"] = remaining[1]
    elif code == "PENA":
        details["penaltyType"] = remaining[0]
        details["infringementType"] = remaining[1]
        details["vehicleIdx"] = remaining[2]
        details["otherVehicleIdx"] = remaining[3]
        details["time"] = remaining[4]
        details["lapNum"] = remaining[5]
        details["placesGained"] = remaining[6]
    elif code == "SPTP":
        details["vehicleIdx"] = remaining[0]
        details["speed"] = struct.unpack_from("<f", remaining, 1)[0]
        details["isOverallFastestInSession"] = remaining[5]
        details["isDriverFastestInSession"] = remaining[6]
        details["fastestVehicleIdxInSession"] = remaining[7]
        details["fastestSpeedInSession"] = struct.unpack_from("<f", remaining, 8)[0]
    elif code == "STLG":
        details["numLights"] = remaining[0]
    elif code == "SGSV":
        details["vehicleIdx"] = remaining[0]
        details["stopTime"] = struct.unpack_from("<f", remaining, 1)[0]
    elif code == "FLBK":
        details["flashbackFrameIdentifier"] = struct.unpack_from("<I", remaining, 0)[0]
        details["flashbackSessionTime"] = struct.unpack_from("<f", remaining, 4)[0]
    elif code == "BUTN":
        details["buttonStatus"] = struct.unpack_from("<I", remaining, 0)[0]
    elif code == "OVTK":
        details["overtakingVehicleIdx"] = remaining[0]
        details["beingOvertakenVehicleIdx"] = remaining[1]
    elif code == "SCAR":
        details["safetyCarType"] = remaining[0]
        details["eventType"] = remaining[1]
    elif code == "COLL":
        details["vehicle1Idx"] = remaining[0]
        details["vehicle2Idx"] = remaining[1]
    elif code == "DRSD":
        details["reason"] = remaining[0]

    return DecodedPacket(header=header, data=details)


def decode_participants(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 4 — Participants: numActiveCars + 22 × ParticipantData."""
    num_active = data[HEADER_SIZE]
    cars = np.frombuffer(data, dtype=DT_PARTICIPANT, count=22, offset=HEADER_SIZE + 1)
    return DecodedPacket(header=header, data={
        "numActiveCars": num_active,
        "cars": cars,
    })


def decode_car_setups(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 5 — CarSetups: 22 × CarSetupData + nextFrontWingValue."""
    cars = np.frombuffer(data, dtype=DT_CAR_SETUP, count=22, offset=HEADER_SIZE)
    trailer_offset = HEADER_SIZE + 22 * DT_CAR_SETUP.itemsize
    next_fw = struct.unpack_from("<f", data, trailer_offset)[0]
    return DecodedPacket(header=header, data={
        "cars": cars,
        "nextFrontWingValue": next_fw,
    })


def decode_car_telemetry(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 6 — CarTelemetry: 22 × CarTelemetryData + 3-byte trailer."""
    cars = np.frombuffer(data, dtype=DT_CAR_TELEMETRY, count=22, offset=HEADER_SIZE)
    trailer_offset = HEADER_SIZE + 22 * DT_CAR_TELEMETRY.itemsize
    mfd1, mfd2, suggested_gear = struct.unpack_from("<BBb", data, trailer_offset)
    return DecodedPacket(header=header, data={
        "cars": cars,
        "mfdPanelIndex": mfd1,
        "mfdPanelIndexSecondaryPlayer": mfd2,
        "suggestedGear": suggested_gear,
    })


def decode_car_status(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 7 — CarStatus: 22 × CarStatusData."""
    cars = np.frombuffer(data, dtype=DT_CAR_STATUS, count=22, offset=HEADER_SIZE)
    return DecodedPacket(header=header, data={"cars": cars})


def decode_final_classification(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 8 — FinalClassification: numCars + 22 × FinalClassificationData."""
    num_cars = data[HEADER_SIZE]
    cars = np.frombuffer(data, dtype=DT_FINAL_CLASSIFICATION, count=22, offset=HEADER_SIZE + 1)
    return DecodedPacket(header=header, data={"numCars": num_cars, "cars": cars})


def decode_lobby_info(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 9 — LobbyInfo: numPlayers + 22 × LobbyInfoData."""
    num_players = data[HEADER_SIZE]
    cars = np.frombuffer(data, dtype=DT_LOBBY_INFO, count=22, offset=HEADER_SIZE + 1)
    return DecodedPacket(header=header, data={"numPlayers": num_players, "cars": cars})


def decode_car_damage(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 10 — CarDamage: 22 × CarDamageData."""
    cars = np.frombuffer(data, dtype=DT_CAR_DAMAGE, count=22, offset=HEADER_SIZE)
    return DecodedPacket(header=header, data={"cars": cars})


def decode_session_history(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 11 — SessionHistory: per-car lap history + tyre stints."""
    offset = HEADER_SIZE
    car_idx, num_laps, num_tyre_stints = struct.unpack_from("<BBB", data, offset)
    offset += 3
    best_lap, best_s1, best_s2, best_s3 = struct.unpack_from("<BBBB", data, offset)
    offset += 4

    laps = np.frombuffer(data, dtype=DT_LAP_HISTORY, count=100, offset=offset)
    offset += 100 * DT_LAP_HISTORY.itemsize

    stints = np.frombuffer(data, dtype=DT_TYRE_STINT, count=8, offset=offset)

    return DecodedPacket(header=header, data={
        "carIdx": car_idx,
        "numLaps": num_laps,
        "numTyreStints": num_tyre_stints,
        "bestLapTimeLapNum": best_lap,
        "bestSector1LapNum": best_s1,
        "bestSector2LapNum": best_s2,
        "bestSector3LapNum": best_s3,
        "lapHistoryData": laps,
        "tyreStintsHistoryData": stints,
    })


def decode_tyre_sets(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 12 — TyreSets: carIdx + 20 × TyreSetData + fittedIdx."""
    offset = HEADER_SIZE
    car_idx = data[offset]; offset += 1
    sets = np.frombuffer(data, dtype=DT_TYRE_SET, count=20, offset=offset)
    offset += 20 * DT_TYRE_SET.itemsize
    fitted_idx = data[offset]
    return DecodedPacket(header=header, data={
        "carIdx": car_idx,
        "tyreSetData": sets,
        "fittedIdx": fitted_idx,
    })


def decode_motion_ex(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 13 — MotionEx: player-only extended motion data."""
    motion = np.frombuffer(data, dtype=DT_MOTION_EX, count=1, offset=HEADER_SIZE)
    return DecodedPacket(header=header, data={"motion": motion[0]})


def decode_time_trial(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 14 — TimeTrial: 3 × TimeTrialDataSet."""
    offset = HEADER_SIZE
    sets = np.frombuffer(data, dtype=DT_TIME_TRIAL_DATA_SET, count=3, offset=offset)
    return DecodedPacket(header=header, data={
        "playerSessionBestDataSet": sets[0],
        "personalBestDataSet": sets[1],
        "rivalDataSet": sets[2],
    })


def decode_lap_positions(data: bytes, header: PacketHeader) -> DecodedPacket:
    """Packet 15 — LapPositions: numLaps, lapStart + 50×22 position grid."""
    offset = HEADER_SIZE
    num_laps = data[offset]; offset += 1
    lap_start = data[offset]; offset += 1
    positions = np.frombuffer(data, dtype="<u1", count=50 * 22, offset=offset).reshape(50, 22)
    return DecodedPacket(header=header, data={
        "numLaps": num_laps,
        "lapStart": lap_start,
        "positions": positions,
    })


# ---------------------------------------------------------------------------
# Decoder dispatch table
# ---------------------------------------------------------------------------

DECODERS: dict[int, Any] = {
    PacketId.MOTION: decode_motion,
    PacketId.SESSION: decode_session,
    PacketId.LAP_DATA: decode_lap_data,
    PacketId.EVENT: decode_event,
    PacketId.PARTICIPANTS: decode_participants,
    PacketId.CAR_SETUPS: decode_car_setups,
    PacketId.CAR_TELEMETRY: decode_car_telemetry,
    PacketId.CAR_STATUS: decode_car_status,
    PacketId.FINAL_CLASSIFICATION: decode_final_classification,
    PacketId.LOBBY_INFO: decode_lobby_info,
    PacketId.CAR_DAMAGE: decode_car_damage,
    PacketId.SESSION_HISTORY: decode_session_history,
    PacketId.TYRE_SETS: decode_tyre_sets,
    PacketId.MOTION_EX: decode_motion_ex,
    PacketId.TIME_TRIAL: decode_time_trial,
    PacketId.LAP_POSITIONS: decode_lap_positions,
}


def decode_packet(data: bytes) -> DecodedPacket | None:
    """Decode a raw UDP datagram. Returns None if packet ID has no decoder."""
    header = decode_header(data)
    decoder = DECODERS.get(header.packet_id)
    if decoder is None:
        return None
    return decoder(data, header)
