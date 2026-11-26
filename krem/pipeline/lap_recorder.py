
"""Bounded, exact-frame lap recording. Called under LiveState's lock.

No interpolation or stale-packet substitution happens here. Missing telemetry
is explicit; distance resampling belongs to the later comparison layer.
"""

from __future__ import annotations

from collections import deque
import math
import time
from typing import Any

from krem.core import PacketId, TYRE_COMPOUND_NAMES, TYRE_VISUAL_NAMES
from krem.ingest import DecodedPacket


def number(value: Any) -> float | None:
    result = float(value)
    return result if math.isfinite(result) else None


def split(car: Any, sector: int) -> int | None:
    value = (
        int(car[f"sector{sector}TimeMinutesPart"]) * 60000
        + int(car[f"sector{sector}TimeMSPart"])
    )
    return value or None


class LapRecorder:
    REORDER_FRAMES = 8
    REORDER_SECONDS = 0.25
    MAX_SAMPLES = 30000

    def __init__(self) -> None:
        self.records: deque[dict[str, Any]] = deque(maxlen=16)
        self.identity: tuple[int, int] | None = None
        self.epoch = 0
        self.track_id: int | None = None
        self.track_length: float | None = None
        self.pending: dict[int, dict[str, Any]] = {}
        self.high_frame = -1
        self.processed_frame = -1
        self.current: dict[str, Any] | None = None
        self.last_time: float | None = None
        self.history_packet: DecodedPacket | None = None
        self.last_event_frame = -1
        self.latest_damage: DecodedPacket | None = None
        self.latest_status: DecodedPacket | None = None
        self.latest_motion: DecodedPacket | None = None

        # Optional background persistence writer.
        self.storage_writer = None

    def reset(self, identity: tuple[int, int]) -> None:
        self.identity = identity
        self.track_id = self.track_length = None
        self._invalidate()
        self.high_frame = self.processed_frame = self.last_event_frame = -1

    def _invalidate(self) -> None:
        # Conservative policy: discard the old timeline rather than compare a
        # post-flashback lap with superseded records from that timeline.
        self.epoch += 1
        self.records.clear()
        self.pending.clear()
        self.current = None
        self.last_time = None
        self.history_packet = None
        self.latest_damage = None
        self.latest_status = None
        self.latest_motion = None

    def ingest(self, packet: DecodedPacket) -> None:
        h = packet.header
        identity = (int(h.session_uid), int(h.player_car_index))

        if identity != self.identity:
            self.reset(identity)

        pid = h.packet_id
        frame = int(h.overall_frame_identifier)

        if pid == PacketId.SESSION:
            self.track_id = int(packet.data["trackId"])
            length = float(packet.data["trackLength"])
            self.track_length = length if length > 0 else None

        elif pid == PacketId.EVENT and packet.data.get("code") == "FLBK":
            if frame > self.last_event_frame:
                self._invalidate()
                self.last_event_frame = frame
                self.processed_frame = max(self.processed_frame, frame - 1)
                self.high_frame = max(self.high_frame, frame)

        elif pid == PacketId.SESSION_HISTORY:
            if (
                int(packet.data["carIdx"]) == identity[1]
                and frame >= self.processed_frame
            ):
                self.history_packet = packet
                self._apply_history()

        elif pid in (
            PacketId.LAP_DATA,
            PacketId.CAR_TELEMETRY,
            PacketId.CAR_DAMAGE,
            PacketId.CAR_STATUS,
            PacketId.MOTION,
        ):
            if not 0 <= identity[1] < len(packet.data["cars"]):
                return

            if frame <= self.processed_frame:
                return  # duplicate or outside the bounded reorder window

            entry = self.pending.setdefault(
                frame, {"received": time.monotonic()}
            )
            entry[pid] = packet
            self.high_frame = max(self.high_frame, frame)
            self.flush()

    def flush(self, force: bool = False) -> None:
        """Drain ordered frames once the reorder window closes (also on read)."""
        now = time.monotonic()

        for frame in sorted(self.pending):
            entry = self.pending.get(frame)
            if entry is None:
                continue

            if (
                not force
                and frame > self.high_frame - self.REORDER_FRAMES
                and now - entry["received"] < self.REORDER_SECONDS
            ):
                break

            self.pending.pop(frame)
            self.processed_frame = frame

            if PacketId.CAR_DAMAGE in entry:
                self.latest_damage = entry[PacketId.CAR_DAMAGE]
            if PacketId.CAR_STATUS in entry:
                self.latest_status = entry[PacketId.CAR_STATUS]
            if PacketId.MOTION in entry:
                self.latest_motion = entry[PacketId.MOTION]

            lap = entry.get(PacketId.LAP_DATA)
            if lap is not None:
                self._consume(
                    lap,
                    entry.get(PacketId.CAR_TELEMETRY),
                    self.latest_damage,
                    self.latest_status,
                    self.latest_motion,
                )

        self._apply_history()

    def _consume(
        self,
        packet: DecodedPacket,
        telemetry: DecodedPacket | None,
        damage: DecodedPacket | None = None,
        status: DecodedPacket | None = None,
        motion: DecodedPacket | None = None,
    ) -> None:
        h = packet.header
        car = packet.data["cars"][h.player_car_index]

        lap_num = int(car["currentLapNum"])
        elapsed = int(car["currentLapTimeInMS"])
        distance = number(car["lapDistance"])
        session_time = number(h.session_time)

        car_position = None
        try:
            pos_val = int(car["carPosition"])
            if pos_val > 0:
                car_position = pos_val
        except Exception:
            pass

        car_sector = None
        try:
            sec_val = int(car["sector"])
            if 0 <= sec_val <= 2:
                car_sector = sec_val
        except Exception:
            pass

        if session_time is None or distance is None:
            if self.current:
                self.current["reasons"].add("non_finite_position")
            return

        current = self.current

        rewind = (
            self.last_time is not None
            and session_time < self.last_time - 0.05
        )

        if current:
            elapsed_drop = current["lastElapsed"] - elapsed
            rewind |= (
                lap_num < current["lap"]
                or (
                    lap_num == current["lap"]
                    and elapsed_drop > 0
                    and (
                        elapsed_drop > 50
                        or distance < current["lastDistance"] - 1.0
                    )
                )
            )

        if rewind:
            self._invalidate()
            current = None

        self.last_time = session_time

        if lap_num <= 0:
            self.current = None
            return

        if current and lap_num != current["lap"]:
            sequential = lap_num == current["lap"] + 1
            self._finish(
                int(car["lastLapTimeInMS"]) if sequential else None,
                sequential,
            )
            current = None

        if current is None:
            current = self.current = {
                "lap": lap_num,
                "samples": [],
                "invalid": False,
                "sectors": [None, None],
                "reasons": set(),
                "lastElapsed": elapsed,
                "lastDistance": distance,
                "startedNearLine": (
                    0 <= distance <= 25
                    and elapsed <= 250
                    and not rewind
                ),
            }

            if not current["startedNearLine"]:
                current["reasons"].add("partial_start")

        current["invalid"] |= bool(car["currentLapInvalid"])

        if (
            int(car["pitStatus"]) != 0
            or int(car["driverStatus"]) in (0, 2, 3)
        ):
            current["reasons"].add("pit_or_out_lap")

        for i in range(2):
            value = split(car, i + 1)
            if value is not None:
                current["sectors"][i] = value

        samples = current["samples"]
        # F1 25 can snap currentLapTimeInMS back a few milliseconds at sector
        # crossings while distance and session_time advance; keep elapsed monotonic.
        recorded_elapsed = max(elapsed, current["lastElapsed"]) if samples else elapsed
        gap = bool(
            samples
            and recorded_elapsed - current["lastElapsed"] > 250
        )

        if gap:
            current["reasons"].add("sample_gap")

        if samples and distance < current["lastDistance"] - 1:
            current["reasons"].add("non_monotonic_distance")
            gap = True

        current["lastElapsed"] = recorded_elapsed
        current["lastDistance"] = distance

        if len(samples) >= self.MAX_SAMPLES:
            current["reasons"].add("sample_limit")
            return

        # Require both frame identifiers and game time to agree. Arrival order
        # does not matter; a nearby frame is never silently substituted.
        aligned = (
            telemetry is not None
            and telemetry.header.frame_identifier == h.frame_identifier
            and abs(
                telemetry.header.session_time - h.session_time
            ) <= 0.02
        )

        speed = throttle = brake = None
        steer = gear = rpm = drs = suggested_gear = None
        tyres_surface = tyres_inner = tyres_pressure = brakes_temp = None

        if aligned:
            values = telemetry.data["cars"][h.player_car_index]
            speed, throttle, brake = (
                number(values[key])
                for key in ("speed", "throttle", "brake")
            )

            if (
                speed is None
                or speed < 0
                or throttle is None
                or not 0 <= throttle <= 1
                or brake is None
                or not 0 <= brake <= 1
            ):
                speed = throttle = brake = None

            try:
                steer = number(values["steer"])
            except Exception:
                pass
            try:
                gear = int(values["gear"])
            except Exception:
                pass
            try:
                rpm = int(values["engineRPM"])
            except Exception:
                pass
            try:
                drs = int(values["drs"])
            except Exception:
                pass
            try:
                suggested_gear = int(telemetry.data.get("suggestedGear", 0))
            except Exception:
                pass
            try:
                tyres_surface = [int(v) for v in values["tyresSurfaceTemperature"]]
            except Exception:
                pass
            try:
                tyres_inner = [int(v) for v in values["tyresInnerTemperature"]]
            except Exception:
                pass
            try:
                tyres_pressure = [round(float(v), 2) for v in values["tyresPressure"]]
            except Exception:
                pass
            try:
                brakes_temp = [int(v) for v in values["brakesTemperature"]]
            except Exception:
                pass

        if speed is None:
            current["reasons"].add("missing_telemetry")

        damage_dict = None
        tyres_wear = None
        tyres_dmg = None

        if damage is not None and 0 <= h.player_car_index < len(damage.data["cars"]):
            car_dmg = damage.data["cars"][h.player_car_index]
            try:
                damage_dict = {
                    "frontLeftWingDamage": int(car_dmg["frontLeftWingDamage"]),
                    "frontRightWingDamage": int(car_dmg["frontRightWingDamage"]),
                    "rearWingDamage": int(car_dmg["rearWingDamage"]),
                    "floorDamage": int(car_dmg["floorDamage"]),
                    "diffuserDamage": int(car_dmg["diffuserDamage"]),
                    "sidepodDamage": int(car_dmg["sidepodDamage"]),
                }
                tyres_wear = [round(float(v), 1) for v in car_dmg["tyresWear"]]
                tyres_dmg = [int(v) for v in car_dmg["tyresDamage"]]
            except Exception:
                pass

        actual_compound = visual_compound = age_laps = None
        actual_name = visual_name = None
        drs_allowed = ers_mode = None
        ers_store = fuel = fuel_laps = None
        if status is not None and 0 <= h.player_car_index < len(status.data["cars"]):
            st_car = status.data["cars"][h.player_car_index]
            try:
                actual_compound = int(st_car["actualTyreCompound"])
                actual_name = TYRE_COMPOUND_NAMES.get(actual_compound)
                visual_compound = int(st_car["visualTyreCompound"])
                visual_name = TYRE_VISUAL_NAMES.get(visual_compound)
                age_laps = int(st_car["tyresAgeLaps"])
            except Exception:
                pass
            try:
                drs_allowed = int(st_car["drsAllowed"])
                ers_store = number(st_car["ersStoreEnergy"])
                if ers_store is not None:
                    ers_store = round(ers_store, 0)
                ers_mode = int(st_car["ersDeployMode"])
                fuel = number(st_car["fuelInTank"])
                if fuel is not None:
                    fuel = round(fuel, 2)
                fuel_laps = number(st_car["fuelRemainingLaps"])
                if fuel_laps is not None:
                    fuel_laps = round(fuel_laps, 2)
            except Exception:
                pass

        g_lat = g_long = None
        if motion is not None and 0 <= h.player_car_index < len(motion.data["cars"]):
            mot_car = motion.data["cars"][h.player_car_index]
            try:
                lat_val = number(mot_car["gForceLateral"])
                long_val = number(mot_car["gForceLongitudinal"])
                if lat_val is not None:
                    g_lat = round(lat_val, 2)
                if long_val is not None:
                    g_long = round(long_val, 2)
            except Exception:
                pass

        tyres_dict = {
            "wheelOrder": ["RL", "RR", "FL", "FR"],
            "wearPct": tyres_wear,
            "damagePct": tyres_dmg,
            "surfaceTempC": tyres_surface,
            "innerTempC": tyres_inner,
            "pressurePsi": tyres_pressure,
            "brakeTempC": brakes_temp,
            "actualCompound": actual_compound,
            "actualCompoundName": actual_name,
            "visualCompound": visual_compound,
            "visualCompoundName": visual_name,
            "ageLaps": age_laps,
        } if (damage is not None or aligned or status is not None) else None

        samples.append({
            "elapsedTimeMs": recorded_elapsed,
            "distance": distance,
            "lapDistance": distance,
            "speed": speed,
            "throttle": throttle,
            "brake": brake,
            "steer": steer,
            "steering": steer,
            "gear": gear,
            "rpm": rpm,
            "engineRPM": rpm,
            "drs": drs,
            "drsAllowed": drs_allowed,
            "suggestedGear": suggested_gear,
            "gLat": g_lat,
            "gLong": g_long,
            "ersStore": ers_store,
            "ersMode": ers_mode,
            "fuel": fuel,
            "fuelLaps": fuel_laps,
            "frameId": int(h.frame_identifier),
            "overallFrameId": int(h.overall_frame_identifier),
            "sessionTime": session_time,
            "sessionUid": str(h.session_uid),
            "playerCarIndex": int(h.player_car_index),
            "lap": lap_num,
            "sector": car_sector,
            "position": car_position,
            "gapBefore": gap,
            "tyres": tyres_dict,
            "damage": damage_dict,
        })

    def _finish(
        self,
        lap_time: int | None,
        sequential: bool,
    ) -> None:
        current = self.current
        assert current is not None

        samples = current["samples"]
        reasons = current["reasons"]

        if not sequential:
            reasons.add("skipped_lap_boundary")

        if not lap_time or lap_time <= 0:
            lap_time = None
            reasons.add("missing_lap_time")

        if (
            not samples
            or lap_time is None
            or not 0 <= lap_time - samples[-1]["elapsedTimeMs"] <= 250
        ):
            reasons.add("partial_end")

        if self.track_length is None:
            reasons.add("unknown_track_length")
        elif (
            not samples
            or not 0 <= self.track_length - samples[-1]["distance"] <= 50
        ):
            reasons.add("partial_end")

        s1, s2 = current["sectors"]
        s3 = (
            lap_time - s1 - s2
            if lap_time and s1 and s2 and lap_time > s1 + s2
            else None
        )

        def average(key: str) -> float | None:
            values = [
                sample[key]
                for sample in samples
                if sample[key] is not None
            ]
            return (
                round(sum(values) / len(values), 3)
                if values
                else None
            )

        speeds = [
            sample["speed"]
            for sample in samples
            if sample["speed"] is not None
        ]

        record = {
            "id": (
                f"{self.identity[0]}:{self.identity[1]}:"
                f"{self.epoch}:{current['lap']}"
            ),
            "sessionUid": str(self.identity[0]),
            "playerCarIndex": self.identity[1],
            "epoch": self.epoch,
            "lap": current["lap"],
            "trackId": self.track_id,
            "trackLength": self.track_length,
            "lapTimeMs": lap_time,
            "sector1TimeMs": s1,
            "sector2TimeMs": s2,
            "sector3TimeMs": s3,
            "invalid": current["invalid"],
            "partial": bool(reasons),
            "qualityReasons": sorted(reasons),
            "sampleCount": len(samples),
            "avgSpeedKph": average("speed"),
            "maxSpeedKph": max(speeds) if speeds else None,
            "avgThrottle": average("throttle"),
            "avgBrake": average("brake"),
            "samples": samples,
        }

        self.records.append(record)

        # Persist the newly completed lap asynchronously.
        if self.storage_writer is not None:
            self.storage_writer.submit(record)

        self.current = None

    def _apply_history(self) -> None:
        packet = self.history_packet

        if packet is None:
            return

        rows = packet.data["lapHistoryData"]
        count = min(int(packet.data["numLaps"]), len(rows))

        for record in self.records:
            if not 1 <= record["lap"] <= count:
                continue

            row = rows[record["lap"] - 1]
            lap_time = int(row["lapTimeInMS"])

            if lap_time <= 0:
                continue

            # Ignore history older than this completed lap's last sample.
            if (
                record["samples"]
                and packet.header.overall_frame_identifier
                < record["samples"][-1]["overallFrameId"]
            ):
                continue

            # Capture existing metadata to detect actual corrections.
            previous = (
                record["lapTimeMs"],
                record["invalid"],
                record["sector1TimeMs"],
                record["sector2TimeMs"],
                record["sector3TimeMs"],
                record.get("sectorValid"),
            )

            record["lapTimeMs"] = lap_time
            flags = int(row["lapValidBitFlags"])
            record["invalid"] = (
                record["invalid"] or not bool(flags & 1)
            )

            for sector in (1, 2, 3):
                record[f"sector{sector}TimeMs"] = split(row, sector)

            record["sectorValid"] = [
                bool(flags & bit)
                for bit in (2, 4, 8)
            ]

            updated = (
                record["lapTimeMs"],
                record["invalid"],
                record["sector1TimeMs"],
                record["sector2TimeMs"],
                record["sector3TimeMs"],
                record.get("sectorValid"),
            )

            # Re-submit the same lap ID. The repository upserts it.
            if (
                updated != previous
                and self.storage_writer is not None
            ):
                self.storage_writer.submit(record)

            # History may repair timing, but cannot fill missing trace samples.

    def current_lap_snapshot(self) -> dict[str, Any] | None:
        if not self.current or not self.current.get("samples"):
            return None
        s1, s2 = self.current["sectors"]
        return {
            "id": f"{self.identity[0] if self.identity else 0}:{self.identity[1] if self.identity else 0}:{self.epoch}:{self.current['lap']}:in_progress",
            "sessionUid": str(self.identity[0]) if self.identity else "",
            "playerCarIndex": self.identity[1] if self.identity else 0,
            "epoch": self.epoch,
            "lap": self.current["lap"],
            "trackId": self.track_id,
            "trackLength": self.track_length,
            "lapTimeMs": self.current["lastElapsed"],
            "sector1TimeMs": s1,
            "sector2TimeMs": s2,
            "sector3TimeMs": None,
            "invalid": self.current["invalid"],
            "partial": True,
            "inProgress": True,
            "qualityReasons": sorted(self.current["reasons"]),
            "sampleCount": len(self.current["samples"]),
            "samples": self.current["samples"],
        }

    def status(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "sessionUid": (
                str(self.identity[0]) if self.identity else None
            ),
            "currentLap": (
                self.current["lap"] if self.current else None
            ),
            "currentSampleCount": (
                len(self.current["samples"]) if self.current else 0
            ),
            "completedCount": len(self.records),
            "pendingFrames": len(self.pending),
        }
