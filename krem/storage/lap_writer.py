
"""Background persistence worker for completed KREM laps."""

from __future__ import annotations

from copy import deepcopy
import queue
import threading
from typing import Any

from krem.storage.lap_repository import LapRepository


_STOP = object()


class LapStorageWriter:
    """Persist completed lap records without writing on the UDP thread.

    Records are copied when submitted. This is important because
    LapRecorder may subsequently update a record using session history.
    """

    def __init__(
        self,
        repository: LapRepository,
        max_queue_size: int = 64,
    ) -> None:
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be at least 1")

        self.repository = repository
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=max_queue_size)
        self._lock = threading.Lock()
        self._errors: list[Exception] = []
        self._closed = False

        self._thread = threading.Thread(
            target=self._run,
            name="krem-lap-storage-writer",
            daemon=False,
        )
        self._thread.start()

    def submit(self, record: dict[str, Any]) -> None:
        """Queue a snapshot of a completed lap for persistence."""
        if not isinstance(record, dict):
            raise TypeError("record must be a dictionary")

        # Copy before queuing: LapRecorder can mutate records during
        # later session-history repairs.
        snapshot = deepcopy(record)

        with self._lock:
            if self._closed:
                raise RuntimeError("LapStorageWriter is already closed")

            # This may wait if the queue is full, but submissions happen
            # only for completed laps or history repairs, not every UDP packet.
            self._queue.put(snapshot)

    def _run(self) -> None:
        while True:
            item = self._queue.get()

            try:
                if item is _STOP:
                    return

                try:
                    self.repository.save_lap(item)
                except Exception as exc:
                    with self._lock:
                        self._errors.append(exc)
            finally:
                self._queue.task_done()

    def flush(self) -> None:
        """Wait until all queued writes have finished."""
        self._queue.join()
        self._raise_write_error()

    def _raise_write_error(self) -> None:
        with self._lock:
            if self._errors:
                error = self._errors[0]
                raise RuntimeError(
                    f"Lap persistence failed: {error}"
                ) from error

    def close(self) -> None:
        """Finish pending writes and stop the worker thread."""
        with self._lock:
            if self._closed:
                return

            self._closed = True
            self._queue.put(_STOP)

        self._queue.join()
        self._thread.join()
        self._raise_write_error()

    def __enter__(self) -> "LapStorageWriter":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
