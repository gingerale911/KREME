"""KREM Coach Package.

Provides track benchmarks, telemetry comparison, and Gemini AI race coaching.
"""

from __future__ import annotations

from krem.coach.benchmarks import BenchmarkRegistry, CornerBenchmark, TrackBenchmark
from krem.coach.comparator import CornerDelta, compare_lap_to_benchmark
from krem.coach.gemini import (
    generate_coach_advice,
    build_coach_prompt,
    get_gemini_api_key,
    persist_gemini_api_key,
)

__all__ = [
    "BenchmarkRegistry",
    "TrackBenchmark",
    "CornerBenchmark",
    "CornerDelta",
    "compare_lap_to_benchmark",
    "generate_coach_advice",
    "build_coach_prompt",
    "get_gemini_api_key",
    "persist_gemini_api_key",
]
