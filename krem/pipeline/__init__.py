"""KREM live state — maintains the latest state for each packet type.

This is the in-memory representation of the current game state,
updated on every decoded packet. All UI frames read from here.

Design (plan §4.1, §4.3):
- Latest per packet type (no history, just the current frame)
- Ring buffers for time-series data (player car)
- Thread-safe reads for the WebSocket frame builder
"""

from __future__ import annotations

import math
import copy
from uuid import uuid4
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from krem.core import (
    MAX_CARS,
    TRACK_NAMES,
    TYRE_COMPOUND_NAMES,
    TYRE_VISUAL_NAMES,
    PacketId,
)
from krem.ingest import DecodedPacket
from krem.pipeline.lap_recorder import LapRecorder
from krem.pipeline.sector_timing import SectorTiming


@dataclass
class SessionInfo:
    """Current session metadata extracted from Session packets."""
    game_paused: bool = False
    session_uid: int = 0
    track_id: int = -1
    track_name: str = "Unknown"
    track_length: int = 0
    session_type: int = 0
    formula: int = 0
    weather: int = 0
    track_temperature: int = 0
    air_temperature: int = 0
    total_laps: int = 0
    safety_car_status: int = 0
    network_game: int = 0
    sector2_start: float = 0.0
    sector3_start: float = 0.0
    session_time_left: int = 0
    speed_units: int = 1  # 0=MPH, 1=KPH
    temp_units: int = 0   # 0=Celsius, 1=Fahrenheit
    is_spectating: int = 0
    spectator_car_index: int = 0
    game_mode: int = 0
    ai_difficulty: int = 0


@dataclass
class PlayerState:
    """Snapshot of the player car's key telemetry values."""
    speed: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    steer: float = 0.0
    gear: int = 0
    rpm: int = 0
    drs: int = 0
    ers_store: float = 0.0
    ers_deploy_mode: int = 0
    fuel_in_tank: float = 0.0
    fuel_remaining_laps: float = 0.0
    lap_distance: float = 0.0
    total_distance: float = 0.0
    last_lap_time_ms: int = 0
    current_lap_time_ms: int = 0
    current_lap_num: int = 0
    sector1_time_ms: int = 0
    sector2_time_ms: int = 0
    sector: int = 0
    car_position: int = 0
    current_lap_invalid: int = 0
    pit_status: int = 0
    driver_status: int = 0
    penalties: int = 0
    g_force_lat: float = 0.0
    g_force_long: float = 0.0
    tyre_compound_actual: int = 0
    tyre_compound_visual: int = 0
    tyre_age_laps: int = 0
    suggested_gear: int = 0
    drs_allowed: int = 0


@dataclass
class LiveState:
    """Central live state container. Updated by the protocol callback.

    Thread safety: reads happen on the WebSocket frame builder thread;
    writes happen on the asyncio event loop. We use a simple lock for
    the snapshot reads (which are fast copies).
    """
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # Session
    session: SessionInfo = field(default_factory=SessionInfo)
    player_car_index: int = 0

    # Latest decoded packets (raw numpy arrays / dicts)
    latest_motion: DecodedPacket | None = None
    latest_lap_data: DecodedPacket | None = None
    latest_telemetry: DecodedPacket | None = None
    latest_status: DecodedPacket | None = None
    latest_damage: DecodedPacket | None = None
    latest_motion_ex: DecodedPacket | None = None
    latest_participants: DecodedPacket | None = None
    latest_session_history: dict[int, DecodedPacket] = field(default_factory=dict)
    latest_tyre_sets: dict[int, DecodedPacket] = field(default_factory=dict)

    # Derived player state (fast access for UI)
    player: PlayerState = field(default_factory=PlayerState)

    # Events log (last N events)
    events: deque = field(default_factory=lambda: deque(maxlen=100))

    # Recorder owns completed and in-progress laps. Guarded by _lock.
    lap_recorder: LapRecorder = field(default_factory=LapRecorder)
    sector_timing: SectorTiming = field(default_factory=SectorTiming)

    # Frame tracking
    last_update_time: float = 0.0
    frame_count: int = 0
    session_time: float = 0.0
    overall_frame_id: int = 0

    # Monotonic receipt times: freshness must not depend on game/replay time.
    _packet_times: dict[int, float] = field(default_factory=dict, repr=False)
    _active_uid: int | None = field(default=None, repr=False)
    _stream_id: str = field(default_factory=lambda: uuid4().hex, repr=False)

    def _reset_feed(self) -> None:
        self._stream_id = uuid4().hex
        self.session = SessionInfo()
        self.player = PlayerState()
        for name in ("motion", "lap_data", "telemetry", "status", "damage",
                     "motion_ex", "participants"):
            setattr(self, f"latest_{name}", None)
        self.latest_session_history.clear()
        self.latest_tyre_sets.clear()
        self._packet_times.clear()
        self.events.clear()
        self.sector_timing = SectorTiming()

    def _freshness(self, pid: int, now: float) -> dict[str, Any]:
        received = self._packet_times.get(pid)
        timeout = 12.0 if pid == PacketId.PARTICIPANTS else 2.0
        age = None if received is None else max(0.0, now - received)
        return {"state": "missing" if age is None else "stale" if age >= timeout else "fresh",
                "ageSeconds": None if age is None else round(age, 3)}

    def update(self, packet: DecodedPacket) -> None:
        """Update live state from a decoded packet."""
        pid = packet.header.packet_id
        with self._lock:
            uid = int(packet.header.session_uid)
            if self._active_uid is not None and (
                uid != self._active_uid or self.player_car_index != packet.header.player_car_index
            ):
                self._reset_feed()
            self._active_uid = uid
            self.session.session_uid = uid
            self.player_car_index = packet.header.player_car_index
            self.last_update_time = time.monotonic()
            # The explicit game flag controls pause; silence alone is not pause.
            if pid == PacketId.SESSION:
                self.session.game_paused = bool(packet.data.get("gamePaused", 0))
            elif self.session.game_paused and pid not in (PacketId.EVENT, PacketId.SESSION_HISTORY):
                return  # retain last driving state; do not record paused repeats

            cars = packet.data.get("cars")
            if cars is None or 0 <= self.player_car_index < len(cars):
                self._packet_times[pid] = self.last_update_time
            else:
                self._packet_times.pop(pid, None)
            self.session_time = packet.header.session_time
            self.overall_frame_id = packet.header.overall_frame_identifier
            self.frame_count += 1
            self.lap_recorder.ingest(packet)

            if pid == PacketId.MOTION:
                self.latest_motion = packet
                self._update_motion(packet)

            elif pid == PacketId.SESSION:
                self._update_session(packet)

            elif pid == PacketId.LAP_DATA:
                self.latest_lap_data = packet
                self._update_lap_data(packet)

            elif pid == PacketId.EVENT:
                self._handle_event(packet)

            elif pid == PacketId.PARTICIPANTS:
                self.latest_participants = packet

            elif pid == PacketId.CAR_TELEMETRY:
                self.latest_telemetry = packet
                self._update_telemetry(packet)

            elif pid == PacketId.CAR_STATUS:
                self.latest_status = packet
                self._update_status(packet)

            elif pid == PacketId.CAR_DAMAGE:
                self.latest_damage = packet

            elif pid == PacketId.SESSION_HISTORY:
                car_idx = packet.data["carIdx"]
                self.latest_session_history[car_idx] = packet
                self.sector_timing.update(packet)

            elif pid == PacketId.TYRE_SETS:
                car_idx = packet.data["carIdx"]
                self.latest_tyre_sets[car_idx] = packet

            elif pid == PacketId.MOTION_EX:
                self.latest_motion_ex = packet

    def _update_session(self, packet: DecodedPacket) -> None:
        d = packet.data
        s = self.session
        s.session_uid = int(packet.header.session_uid)
        s.track_id = d["trackId"]
        s.track_name = TRACK_NAMES.get(d["trackId"], f"Track {d['trackId']}")
        s.track_length = d["trackLength"]
        s.session_type = d["sessionType"]
        s.formula = d["formula"]
        s.weather = d["weather"]
        s.track_temperature = d["trackTemperature"]
        s.air_temperature = d["airTemperature"]
        s.total_laps = d["totalLaps"]
        s.safety_car_status = d["safetyCarStatus"]
        s.network_game = d["networkGame"]
        s.sector2_start = d["sector2LapDistanceStart"]
        s.sector3_start = d["sector3LapDistanceStart"]
        s.session_time_left = d["sessionTimeLeft"]
        s.speed_units = d["speedUnitsLeadPlayer"]
        s.temp_units = d["temperatureUnitsLeadPlayer"]
        s.is_spectating = d["isSpectating"]
        s.spectator_car_index = d["spectatorCarIndex"]
        s.game_mode = d["gameMode"]
        s.ai_difficulty = d["aiDifficulty"]

    def _update_motion(self, packet: DecodedPacket) -> None:
        idx = self.player_car_index
        cars = packet.data["cars"]
        if 0 <= idx < len(cars):
            car = cars[idx]
            self.player.g_force_lat = float(car["gForceLateral"])
            self.player.g_force_long = float(car["gForceLongitudinal"])

    def _update_lap_data(self, packet: DecodedPacket) -> None:
        idx = self.player_car_index
        cars = packet.data["cars"]
        if 0 <= idx < len(cars):
            car = cars[idx]
            p = self.player
            p.lap_distance = float(car["lapDistance"])
            p.total_distance = float(car["totalDistance"])
            p.last_lap_time_ms = int(car["lastLapTimeInMS"])
            p.current_lap_time_ms = int(car["currentLapTimeInMS"])
            p.current_lap_num = int(car["currentLapNum"])
            p.sector1_time_ms = (                int(car["sector1TimeMinutesPart"]) * 60_000
                + int(car["sector1TimeMSPart"])
            )
            p.sector2_time_ms = (
                int(car["sector2TimeMinutesPart"]) * 60_000
                + int(car["sector2TimeMSPart"])
            )
            p.sector = int(car["sector"])
            p.car_position = int(car["carPosition"])
            p.current_lap_invalid = int(car["currentLapInvalid"])
            p.pit_status = int(car["pitStatus"])
            p.driver_status = int(car["driverStatus"])
            p.penalties = int(car["penalties"])

    def _update_telemetry(self, packet: DecodedPacket) -> None:
        idx = self.player_car_index
        cars = packet.data["cars"]
        if 0 <= idx < len(cars):
            car = cars[idx]
            p = self.player
            p.speed = int(car["speed"])
            p.throttle = float(car["throttle"])
            p.brake = float(car["brake"])
            p.steer = float(car["steer"])
            p.gear = int(car["gear"])
            p.rpm = int(car["engineRPM"])
            p.drs = int(car["drs"])
            p.suggested_gear = packet.data.get("suggestedGear", 0)

    def _update_status(self, packet: DecodedPacket) -> None:
        idx = self.player_car_index
        cars = packet.data["cars"]
        if 0 <= idx < len(cars):
            car = cars[idx]
            p = self.player
            p.ers_store = float(car["ersStoreEnergy"])
            p.ers_deploy_mode = int(car["ersDeployMode"])
            p.fuel_in_tank = float(car["fuelInTank"])
            p.fuel_remaining_laps = float(car["fuelRemainingLaps"])
            p.tyre_compound_actual = int(car["actualTyreCompound"])
            p.tyre_compound_visual = int(car["visualTyreCompound"])
            p.tyre_age_laps = int(car["tyresAgeLaps"])
            p.drs_allowed = int(car["drsAllowed"])

    def _handle_event(self, packet: DecodedPacket) -> None:
        code = packet.data.get("code", "")
        self.events.append({
            "code": code,
            "time": packet.header.session_time,
            "frame": packet.header.overall_frame_identifier,
            "details": {k: v for k, v in packet.data.items() if k != "code"},
        })

    def current_lap_snapshot(self) -> dict[str, Any] | None:
        """Return the active in-progress lap record with current samples."""
        with self._lock:
            self.lap_recorder.flush(force=True)
            lap = self.lap_recorder.current_lap_snapshot()
            return _json_safe(lap) if lap else None

    def lap_history_snapshot(self) -> list[dict[str, Any]]:
        """Return the completed lap records for this telemetry session."""
        with self._lock:
            self.lap_recorder.flush()
            return [_json_safe(item) for item in self.lap_recorder.records]

    def snapshot(self, include_laps: bool = True) -> dict[str, Any]:
        """Create a compact, JSON-safe snapshot for API and WebSocket frames."""
        with self._lock:
            if include_laps:
                self.lap_recorder.flush()
            idx = self.player_car_index
            player_name, player_number = self._driver_info(idx)
            sector3_time = None
            completed_splits = (
                self.player.sector1_time_ms + self.player.sector2_time_ms
            )
            if (
                self.player.sector == 2
                and self.player.sector1_time_ms > 0
                and self.player.sector2_time_ms > 0
                and self.player.current_lap_time_ms >= completed_splits
            ):
                sector3_time = self.player.current_lap_time_ms - completed_splits

            telemetry = self.latest_telemetry
            result = {
                "liveStreamId": self._stream_id,
                "gamePaused": self.session.game_paused,
                "telemetrySample": None if telemetry is None else {
                    "id": f"{self._stream_id}:{telemetry.header.overall_frame_identifier}",
                    "sessionTime": float(telemetry.header.session_time),
                },
                "session": {
                    "uid": self.session.session_uid,
                    "trackId": self.session.track_id,
                    "trackName": self.session.track_name,
                    "trackLength": self.session.track_length,
                    "sessionType": self.session.session_type,
                    "formula": self.session.formula,
                    "weather": self.session.weather,
                    "trackTemp": self.session.track_temperature,
                    "airTemp": self.session.air_temperature,
                    "safetyCar": self.session.safety_car_status,
                    "sector2Start": _json_number(self.session.sector2_start, 1),
                    "sector3Start": _json_number(self.session.sector3_start, 1),
                    "totalLaps": self.session.total_laps,
                    "sessionTimeLeft": self.session.session_time_left,
                    "sessionTime": _json_number(self.session_time, 2),
                    "speedUnits": self.session.speed_units,
                    "temperatureUnits": self.session.temp_units,
                    "networkGame": self.session.network_game,
                    "isSpectating": self.session.is_spectating,
                    "spectatorCarIndex": self.session.spectator_car_index,
                    "gameMode": self.session.game_mode,
                    "aiDifficulty": self.session.ai_difficulty,
                },
                "player": {
                    "speed": self.player.speed,
                    "throttle": _json_number(self.player.throttle, 3),
                    "brake": _json_number(self.player.brake, 3),
                    "steer": _json_number(self.player.steer, 3),
                    "gear": self.player.gear,
                    "rpm": self.player.rpm,
                    "drs": self.player.drs,
                    "drsAllowed": self.player.drs_allowed,
                    "ersStore": _json_number(self.player.ers_store, 0),
                    "ersMode": self.player.ers_deploy_mode,
                    "fuel": _json_number(self.player.fuel_in_tank, 2),
                    "fuelLaps": _json_number(self.player.fuel_remaining_laps, 2),
                    "fuelCapacity": self._player_status_value("fuelCapacity", 2),
                    "lapDist": _json_number(self.player.lap_distance, 1),
                    "totalDist": _json_number(self.player.total_distance, 1),
                    "lastLapTime": self.player.last_lap_time_ms,
                    "lapTime": self.player.current_lap_time_ms,
                    "lapNum": self.player.current_lap_num,
                    "sector1TimeMs": self.player.sector1_time_ms,
                    "sector2TimeMs": self.player.sector2_time_ms,
                    "sector3TimeMs": sector3_time,
                    "sector": self.player.sector,
                    "position": self.player.car_position,
                    "invalid": self.player.current_lap_invalid,
                    "pitStatus": self.player.pit_status,
                    "driverStatus": self.player.driver_status,
                    "penalties": self.player.penalties,
                    "gLat": _json_number(self.player.g_force_lat, 2),
                    "gLong": _json_number(self.player.g_force_long, 2),
                    "tyreCompound": self.player.tyre_compound_visual,
                    "tyreAge": self.player.tyre_age_laps,
                    "suggestedGear": self.player.suggested_gear,
                    "ersDeployedThisLap": self._player_status_value(
                        "ersDeployedThisLap", 0
                    ),
                    "name": player_name,
                    "driverNumber": player_number,
                    "tyres": self._player_tyres(),
                    "damage": self._player_damage(),
                },
                "cars": self._car_positions(),
                "events": [
                    _json_safe(event) for event in list(self.events)[-10:]
                ],
                "laps": (
                    [_json_safe(item) for item in self.lap_recorder.records]
                    if include_laps
                    else []
                ),
                "recorder": self.lap_recorder.status(),
                "sectorTiming": self.sector_timing.snapshot(self.player, idx, self.lap_recorder.records),
                "frameCount": self.frame_count,
                "frameId": self.overall_frame_id,
                "playerCarIndex": idx,
            }

            now = time.monotonic()
            groups = {
                "telemetry": (PacketId.CAR_TELEMETRY, "speed throttle brake steer gear rpm drs suggestedGear"),
                "status": (PacketId.CAR_STATUS, "drsAllowed ersStore ersMode fuel fuelLaps fuelCapacity tyreCompound tyreAge ersDeployedThisLap"),
                "lap": (PacketId.LAP_DATA, "lapDist totalDist lastLapTime lapTime lapNum sector1TimeMs sector2TimeMs sector3TimeMs sector position invalid pitStatus driverStatus penalties"),
                "motion": (PacketId.MOTION, "gLat gLong"),
                "damage": (PacketId.CAR_DAMAGE, ""),
                "session": (PacketId.SESSION, ""),
                "participants": (PacketId.PARTICIPANTS, "name driverNumber"),
            }
            freshness = {name: self._freshness(pid, now) for name, (pid, _) in groups.items()}
            result["freshness"] = freshness
            def mask(view: dict[str, Any], missing_only: bool) -> None:
                def unavailable(name: str) -> bool:
                    state = freshness[name]["state"]
                    return state == "missing" if missing_only else state != "fresh"
                player = view["player"]
                for name, (_, keys) in groups.items():
                    if unavailable(name):
                        for key in keys.split():
                            player[key] = None
                tyres = player["tyres"]
                if unavailable("telemetry"):
                    for key in ("surfaceTempC", "innerTempC", "pressurePsi", "brakeTempC"):
                        tyres[key] = None
                if unavailable("damage"):
                    tyres["wearPct"] = tyres["damagePct"] = None
                    player["damage"] = dict.fromkeys(player["damage"])
                if unavailable("status"):
                    for key in ("actualCompound", "actualCompoundName", "visualCompound", "visualCompoundName", "ageLaps"):
                        tyres[key] = None
                if unavailable("session"):
                    view["session"] = {key: value if key == "uid" else None
                                         for key, value in view["session"].items()}
                if unavailable("motion"):
                    view["cars"] = []
                elif unavailable("lap"):
                    for car in view["cars"]:
                        for key in ("position", "lap", "sector", "lapDistance"):
                            car[key] = None
            retained = {key: copy.deepcopy(result[key]) for key in ("player", "session", "cars")}
            mask(retained, missing_only=True)
            mask(result, missing_only=False)
            result["retainedLive"] = retained
            return result

    def events_snapshot(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Return a JSON-safe copy of recent event records."""
        with self._lock:
            events = list(self.events)
            if limit is not None:
                events = events[-limit:]
            return [_json_safe(event) for event in events]

    def _driver_info(self, index: int) -> tuple[str | None, int | None]:
        packet = self.latest_participants
        if packet is None or not 0 <= index < min(MAX_CARS, len(packet.data["cars"])):
            return None, None
        car = packet.data["cars"][index]
        raw_name = car["name"]
        if isinstance(raw_name, bytes):
            name = raw_name.split(b"\0", 1)[0].decode("utf-8", errors="replace").strip()
        else:
            name = bytes(raw_name).split(b"\0", 1)[0].decode(
                "utf-8", errors="replace"
            ).strip()
        return name or None, int(car["raceNumber"])

    def _player_tyres(self) -> dict[str, Any]:
        """Expose only the four useful per-wheel values, never packet arrays."""
        idx = self.player_car_index
        telemetry = self.latest_telemetry
        damage = self.latest_damage

        def wheel_values(
            packet: DecodedPacket | None, field_name: str, digits: int | None = None
        ) -> list[int | float | None] | None:
            if packet is None or idx >= len(packet.data["cars"]):
                return None
            values = packet.data["cars"][idx][field_name]
            return [
                _json_number(value, digits) if digits is not None else int(value)
                for value in values
            ]

        return {
            "wheelOrder": ["RL", "RR", "FL", "FR"],
            "actualCompound": self.player.tyre_compound_actual,
            "actualCompoundName": TYRE_COMPOUND_NAMES.get(
                self.player.tyre_compound_actual
            ),
            "visualCompound": self.player.tyre_compound_visual,
            "visualCompoundName": TYRE_VISUAL_NAMES.get(
                self.player.tyre_compound_visual
            ),
            "ageLaps": self.player.tyre_age_laps,
            "surfaceTempC": wheel_values(telemetry, "tyresSurfaceTemperature"),
            "innerTempC": wheel_values(telemetry, "tyresInnerTemperature"),
            "pressurePsi": wheel_values(telemetry, "tyresPressure", 2),
            "brakeTempC": wheel_values(telemetry, "brakesTemperature"),
            "wearPct": wheel_values(damage, "tyresWear", 1),
            "damagePct": wheel_values(damage, "tyresDamage"),
        }

    def _player_damage(self) -> dict[str, Any]:
        """Expose wing and aero damage metrics for the current car."""
        idx = self.player_car_index
        packet = self.latest_damage
        if packet is None or idx >= len(packet.data["cars"]):
            return {
                "frontLeftWingDamage": None,
                "frontRightWingDamage": None,
                "rearWingDamage": None,
                "floorDamage": None,
                "diffuserDamage": None,
                "sidepodDamage": None,
            }
        car = packet.data["cars"][idx]
        return {
            "frontLeftWingDamage": _json_number(car["frontLeftWingDamage"], 0),
            "frontRightWingDamage": _json_number(car["frontRightWingDamage"], 0),
            "rearWingDamage": _json_number(car["rearWingDamage"], 0),
            "floorDamage": _json_number(car["floorDamage"], 0),
            "diffuserDamage": _json_number(car["diffuserDamage"], 0),
            "sidepodDamage": _json_number(car["sidepodDamage"], 0),
        }

    def _player_status_value(self, field_name: str, digits: int) -> float | None:
        packet = self.latest_status
        idx = self.player_car_index
        if packet is None or idx >= len(packet.data["cars"]):
            return None
        return _json_number(packet.data["cars"][idx][field_name], digits)

    def _car_positions(self) -> list[dict[str, Any]]:
        motion = self.latest_motion
        if motion is None:
            return []

        participants = self.latest_participants
        if participants is not None:
            active_count = min(
                MAX_CARS,
                max(0, int(participants.data.get("numActiveCars", 0))),
                len(participants.data["cars"]),
            )
            indices = range(active_count)
        else:
            indices = range(min(MAX_CARS, len(motion.data["cars"])))

        lap_packet = self.latest_lap_data
        result = []
        for index in indices:
            if index >= len(motion.data["cars"]):
                continue
            motion_car = motion.data["cars"][index]
            world_x = _json_number(motion_car["worldPositionX"], 2)
            world_z = _json_number(motion_car["worldPositionZ"], 2)
            if (
                participants is None
                and world_x == 0
                and world_z == 0
                and index != self.player_car_index
            ):
                continue
            name, number = self._driver_info(index)
            lap_car = (
                lap_packet.data["cars"][index]
                if lap_packet is not None and index < len(lap_packet.data["cars"])
                else None
            )
            result.append({
                "index": index,
                "name": name,
                "driverNumber": number,
                "teamId": (
                    int(participants.data["cars"][index]["teamId"])
                    if participants is not None
                    else None
                ),
                "worldX": world_x,
                "worldZ": world_z,
                "heading": _json_number(motion_car["yaw"], 3),
                "position": int(lap_car["carPosition"]) if lap_car is not None else None,
                "lap": int(lap_car["currentLapNum"]) if lap_car is not None else None,
                "sector": int(lap_car["sector"]) if lap_car is not None else None,
                "lapDistance": (
                    _json_number(lap_car["lapDistance"], 1)
                    if lap_car is not None
                    else None
                ),
                "isPlayer": index == self.player_car_index,
            })
        return result


def _json_number(value: Any, digits: int | None) -> int | float | None:
    """Convert numpy and Python numbers to finite built-in JSON number types."""
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, digits) if digits is not None else number


def _json_safe(value: Any) -> Any:
    """Recursively convert event values to JSON-safe Python primitives."""
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8", errors="replace").rstrip("\0")
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return _json_number(value, None)
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    return value
