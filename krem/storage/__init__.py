
"""Persistent storage for KREM telemetry."""

from krem.storage.database import LapDatabase
from krem.storage.lap_repository import LapRepository

__all__ = ["LapDatabase", "LapRepository"]
