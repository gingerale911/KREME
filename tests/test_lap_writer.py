
import threading

import pytest

from krem.storage.lap_writer import LapStorageWriter


class FakeRepository:
    def __init__(self):
        self.saved = []
        self.lock = threading.Lock()

    def save_lap(self, record):
        with self.lock:
            self.saved.append(record)
        return record["id"]


def make_record(lap_time=90000):
    return {
        "id": "123:0:0:1",
        "sessionUid": "123",
        "playerCarIndex": 0,
        "epoch": 0,
        "lap": 1,
        "lapTimeMs": lap_time,
        "samples": [],
    }


def test_writer_persists_submitted_record():
    repository = FakeRepository()
    writer = LapStorageWriter(repository)

    writer.submit(make_record())
    writer.flush()
    writer.close()

    assert len(repository.saved) == 1
    assert repository.saved[0]["lapTimeMs"] == 90000


def test_writer_snapshots_record_before_queueing():
    repository = FakeRepository()
    writer = LapStorageWriter(repository)

    record = make_record()
    writer.submit(record)

    # Simulate a later history repair.
    record["lapTimeMs"] = 85000

    writer.flush()
    writer.close()

    assert repository.saved[0]["lapTimeMs"] == 90000


def test_writer_persists_later_record_update():
    repository = FakeRepository()
    writer = LapStorageWriter(repository)

    writer.submit(make_record(90000))
    writer.submit(make_record(85000))

    writer.flush()
    writer.close()

    assert len(repository.saved) == 2
    assert repository.saved[0]["lapTimeMs"] == 90000
    assert repository.saved[1]["lapTimeMs"] == 85000


def test_writer_rejects_submit_after_close():
    repository = FakeRepository()
    writer = LapStorageWriter(repository)
    writer.close()

    with pytest.raises(RuntimeError):
        writer.submit(make_record())


def test_writer_rejects_invalid_queue_size():
    repository = FakeRepository()

    with pytest.raises(ValueError):
        LapStorageWriter(repository, max_queue_size=0)
