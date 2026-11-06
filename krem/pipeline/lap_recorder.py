
"""Bounded, exact-frame lap recording. Called under LiveState's lock.

No interpolation or stale-packet substitution happens here. Missing telemetry
is explicit; distance resampling belongs to the later comparison layer.
"""

from __future__ import annotations

from collections import deque
import math
import time
from typing import Any

from krem.core import PacketId
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

        elif pid in (PacketId.LAP_DATA, PacketId.CAR_TELEMETRY):
            if not 0 <= identity[1] < len(packet.data["cars"]):
                return

            if frame <= self.processed_frame:
                return  # duplicate or outside the bounded reorder window

            entry = self.pending.setdefault(
                frame, {"received": time.monotonic()}
            )
            entry.setdefault(pid, packet)
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

            lap = entry.get(PacketId.LAP_DATA)
            if lap is not None:
                self._consume(lap, entry.get(PacketId.CAR_TELEMETRY))

        self._apply_history()

    def _consume(
        self,
        packet: DecodedPacket,
        telemetry: DecodedPacket | None,
    ) -> None:
        h = packet.header
        car = packet.data["cars"][h.player_car_index]

        lap_num = int(car["currentLapNum"])
        elapsed = int(car["currentLapTimeInMS"])
        distance = number(car["lapDistance"])
        session_time = number(h.session_time)

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
            rewind |= (
                lap_num < current["lap"]
                or (
                    lap_num == current["lap"]
                    and elapsed < current["lastElapsed"]
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
        gap = bool(
            samples
            and elapsed - current["lastElapsed"] > 250
        )

        if gap:
            current["reasons"].add("sample_gap")

        if samples and distance < current["lastDistance"] - 1:
            current["reasons"].add("non_monotonic_distance")
            gap = True

        current["lastElapsed"] = elapsed
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
        steer = gear = rpm = drs = None

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

        if speed is None:
            current["reasons"].add("missing_telemetry")

        samples.append({
            "elapsedTimeMs": elapsed,
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
            "frameId": int(h.frame_identifier),
            "overallFrameId": int(h.overall_frame_identifier),
            "sessionTime": session_time,
            "sessionUid": str(h.session_uid),
            "playerCarIndex": int(h.player_car_index),
            "lap": lap_num,
            "gapBefore": gap,
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
