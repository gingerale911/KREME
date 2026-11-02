"""KREM raw recorder — writes incoming datagrams to .f1udp capture files."""

from __future__ import annotations

import logging
import math
import struct
import threading
import time
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Final

_MAGIC: Final[bytes] = b"F1UDP\x01\x00\x00"
_RECORD_HEADER_FMT: Final[str] = "<Id"
_RECORD_HEADER_SIZE: Final[int] = struct.calcsize(_RECORD_HEADER_FMT)
_MAX_DATAGRAM_SIZE: Final[int] = 65_507

logger = logging.getLogger("krem.recorder")


class Recorder:
    """Threaded raw UDP capture writer.

    Record timestamps are captured when datagrams enter the queue, not when
    the writer thread eventually flushes them.
    """

    def __init__(self, captures_dir: str | Path, queue_maxsize: int = 10_000) -> None:
        if queue_maxsize < 1:
            raise ValueError("queue_maxsize must be positive")
        self._captures_dir = Path(captures_dir)
        self._captures_dir.mkdir(parents=True, exist_ok=True)
        self._queue: Queue[tuple[float, bytes] | None] = Queue(maxsize=queue_maxsize)
        self._thread: threading.Thread | None = None
        self._filepath: Path | None = None
        self._packet_count = 0
        self._bytes_written = 0
        self._dropped_packets = 0
        self._start_time = 0.0
        self._writer_error: Exception | None = None
        self._overflow_logged = False

    @property
    def filepath(self) -> Path | None:
        return self._filepath

    @property
    def packet_count(self) -> int:
        return self._packet_count

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def dropped_packets(self) -> int:
        return self._dropped_packets

    def start(self, session_uid: int = 0) -> Path:
        """Start recording to a new capture file. Returns the file path."""
        if self._thread is not None:
            self.stop()

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{timestamp}_{session_uid:016x}.f1udp"
        self._filepath = self._captures_dir / filename
        self._packet_count = 0
        self._bytes_written = 0
        self._dropped_packets = 0
        self._writer_error = None
        self._overflow_logged = False
        self._start_time = time.monotonic()

        self._thread = threading.Thread(
            target=self._writer_loop,
            args=(self._filepath,),
            name="krem-recorder",
            daemon=True,
        )
        self._thread.start()
        return self._filepath

    def write(self, datagram: bytes) -> bool:
        """Enqueue a datagram without blocking; return false if the queue is full."""
        if self._thread is None:
            raise RuntimeError("Recorder must be started before writing")
        if len(datagram) > _MAX_DATAGRAM_SIZE:
            raise ValueError(f"UDP datagram exceeds {_MAX_DATAGRAM_SIZE} bytes")

        record = (time.monotonic() - self._start_time, bytes(datagram))
        try:
            self._queue.put_nowait(record)
        except Full:
            self._dropped_packets += 1
            if not self._overflow_logged:
                logger.warning("Capture queue full; dropping incoming datagrams")
                self._overflow_logged = True
            return False
        return True

    def stop(self) -> None:
        """Flush and stop the writer, raising if it could not finish cleanly."""
        thread = self._thread
        if thread is None:
            return

        if thread.is_alive():
            try:
                self._queue.put(None, timeout=5.0)
            except Full:
                thread.join(timeout=5.0)
                if thread.is_alive():
                    raise TimeoutError("Recorder writer did not stop")
            else:
                thread.join(timeout=5.0)
                if thread.is_alive():
                    raise TimeoutError("Recorder writer did not stop")

        self._thread = None
        if self._writer_error is not None:
            raise RuntimeError("Recorder writer failed") from self._writer_error

    def _writer_loop(self, filepath: Path) -> None:
        try:
            with filepath.open("wb") as file:
                file.write(_MAGIC)
                while True:
                    try:
                        record = self._queue.get(timeout=1.0)
                    except Empty:
                        continue
                    if record is None:
                        break
                    timestamp, datagram = record
                    file.write(struct.pack(_RECORD_HEADER_FMT, len(datagram), timestamp))
                    file.write(datagram)
                    self._packet_count += 1
                    self._bytes_written += _RECORD_HEADER_SIZE + len(datagram)
                    if self._packet_count % 100 == 0:
                        file.flush()
        except Exception as exc:
            self._writer_error = exc
            logger.exception("Capture writer failed for %s", filepath)


class ReplayReader:
    """Read validated .f1udp records as (timestamp, datagram) pairs."""

    def __init__(self, filepath: str | Path) -> None:
        self._filepath = Path(filepath)
        if not self._filepath.exists():
            raise FileNotFoundError(f"Capture file not found: {self._filepath}")

    def __iter__(self):
        previous_timestamp = -1.0
        with self._filepath.open("rb") as file:
            if file.read(len(_MAGIC)) != _MAGIC:
                raise ValueError(f"Not a supported .f1udp file: {self._filepath}")

            while True:
                header_bytes = file.read(_RECORD_HEADER_SIZE)
                if not header_bytes:
                    return
                if len(header_bytes) != _RECORD_HEADER_SIZE:
                    raise ValueError(f"Truncated record header in {self._filepath}")

                length, timestamp = struct.unpack(_RECORD_HEADER_FMT, header_bytes)
                if length > _MAX_DATAGRAM_SIZE:
                    raise ValueError(f"Invalid UDP datagram length {length}")
                if not math.isfinite(timestamp) or timestamp < previous_timestamp:
                    raise ValueError(f"Invalid capture timestamp {timestamp}")

                datagram = file.read(length)
                if len(datagram) != length:
                    raise ValueError(f"Truncated datagram in {self._filepath}")
                previous_timestamp = timestamp
                yield timestamp, datagram

    def packets(self) -> list[tuple[float, bytes]]:
        """Load all packets into memory. Useful for tests and replay."""
        return list(self)
