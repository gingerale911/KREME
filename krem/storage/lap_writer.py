
"""Background persistence worker for completed KREM laps."""

from __future__ import annotations

from collections import deque
import queue
import threading
from typing import Any

from krem.storage.lap_repository import LapRepository


class LapStorageWriter:
    """Persist completed laps without blocking the telemetry update path.

    The bounded queue has a non-blocking overflow backlog. Completed lap
    records are submitted in order and written by a dedicated worker thread.

    LapRecorder does not modify a completed lap's samples after finishing
    it. Therefore submit() copies the record metadata but safely shares the
    completed samples list, avoiding a costly deep copy on the telemetry path.
    """

    def __init__(
        self,
        repository: LapRepository,
        max_queue_size: int = 64,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")

        self.repository = repository
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=max_queue_size
        )
        self._overflow: deque[dict[str, Any]] = deque()

        self._condition = threading.Condition()
        self._submitted = 0
        self._completed = 0
        self._errors: list[Exception] = []
        self._closed = False

        self._thread = threading.Thread(
            target=self._run,
            name="krem-lap-storage-writer",
            daemon=False,
        )
        self._thread.start()

    @staticmethod
    def _snapshot(record: dict[str, Any]) -> dict[str, Any]:
        """Copy mutable metadata while reusing the finished sample list."""
        snapshot = dict(record)

        for key in ("qualityReasons", "sectorValid"):
            value = snapshot.get(key)
            if isinstance(value, list):
                snapshot[key] = list(value)

        return snapshot

    def submit(self, record: dict[str, Any]) -> None:
        """Submit a completed lap without waiting for queue capacity."""
        if not isinstance(record, dict):
            raise TypeError("record must be a dictionary")

        snapshot = self._snapshot(record)

        with self._condition:
            if self._closed:
                raise RuntimeError("LapStorageWriter is already closed")

            # Preserve submission order: once overflow exists, newer
            # records join it rather than jumping ahead into the queue.
            if self._overflow:
                self._overflow.append(snapshot)
            else:
                try:
                    self._queue.put_nowait(snapshot)
                except queue.Full:
                    self._overflow.append(snapshot)

            self._submitted += 1
            self._condition.notify_all()

    def _next_record(self) -> dict[str, Any] | None:
        """Get the oldest queued record, or None when fully stopped."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            pass

        with self._condition:
            if self._overflow:
                return self._overflow.popleft()

            if self._closed:
                return None

            self._condition.wait(timeout=0.05)
            return {}

    def _run(self) -> None:
        while True:
            record = self._next_record()

            if record is None:
                return

            # Empty dict means the worker woke up to re-check its queues.
            if not record:
                continue

            try:
                self.repository.save_lap(record)
            except Exception as exc:
                with self._condition:
                    self._errors.append(exc)
            finally:
                with self._condition:
                    self._completed += 1
                    self._condition.notify_all()

    def flush(self) -> None:
        """Wait for all records submitted before this call to finish."""
        with self._condition:
            target = self._submitted

            while self._completed < target:
                self._condition.wait(timeout=0.1)

            self._raise_write_error()

    def _raise_write_error(self) -> None:
        if self._errors:
            error = self._errors[0]
            raise RuntimeError(
                f"Lap persistence failed: {error}"
            ) from error

    def close(self) -> None:
        """Drain pending records and stop the worker."""
        with self._condition:
            if self._closed:
                already_closed = True
            else:
                already_closed = False
                self._closed = True
                self._condition.notify_all()

        if not already_closed:
            self._thread.join()

        with self._condition:
            self._raise_write_error()

    def __enter__(self) -> "LapStorageWriter":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
