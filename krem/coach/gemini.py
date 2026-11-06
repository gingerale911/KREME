"""KREM Coach Gemini API client and prompt builder.

Formats deterministic telemetry deltas into prompt context and calls
the Google GenAI API to produce direct, corner-by-corner race engineer advice.
"""

from __future__ import annotations

import os
import re
import json
import logging
from pathlib import Path
from typing import Any
from dotenv import load_dotenv, set_key

from krem.coach.benchmarks import TrackBenchmark
from krem.coach.comparator import CornerDelta

logger = logging.getLogger("krem.coach")


def get_gemini_api_key() -> str | None:
    """Retrieve GEMINI_API_KEY from environment or search parent directories for .env."""
    key = os.environ.get("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()

    # Search likely .env locations
    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / "KREME" / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    for cand in candidates:
        if cand.is_file():
            try:
                load_dotenv(cand, override=True)
                key = os.environ.get("GEMINI_API_KEY")
                if key and key.strip():
                    return key.strip()
            except Exception:
                pass
    return None


def persist_gemini_api_key(key: str) -> None:
    """Save GEMINI_API_KEY in environment and persist to .env files."""
    cleaned = key.strip()
    os.environ["GEMINI_API_KEY"] = cleaned

    targets = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for p in targets:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.is_file():
                p.write_text(f"GEMINI_API_KEY={cleaned}\n", encoding="utf-8")
            else:
                set_key(str(p), "GEMINI_API_KEY", cleaned)
        except Exception as e:
            logger.warning("Could not persist key to %s: %s", p, e)


def _sort_corners(corners: list[CornerDelta]) -> list[CornerDelta]:
    """Sort corners in natural turn order (e.g. 1, 2, 3, 10, 11)."""
    def turn_sort_key(c: CornerDelta):
        digits = "".join(filter(str.isdigit, str(c.turn)))
        return int(digits) if digits else 999

    return sorted(corners, key=turn_sort_key)


def build_coach_prompt(
    track: TrackBenchmark,
    player_lap_time_ms: int,
    corner_deltas: list[CornerDelta],
    focus_sector: int | None = None,
    last_lap_num: int | None = None,
) -> str:
    """Construct a clean structured prompt focused strictly corner-by-corner on the upcoming sector."""
    if focus_sector is not None:
        target_corners = [c for c in corner_deltas if c.sector == focus_sector]
        sector_str = f"SECTOR {focus_sector}"
    else:
        target_corners = corner_deltas
        sector_str = "NEXT SECTOR"

    target_corners = _sort_corners(target_corners)

    observations = [c.to_dict() for c in target_corners]
    return f"""You are a concise race engineer. Coach only {sector_str} on {track.track_name}.
Evaluated lap: {last_lap_num}; lap time: {player_lap_time_ms} ms.
These are measured brake-on, brake-release and throttle-pickup timestamps from that previous lap,
with absolute lap distances and differences against configured coaching targets.
Targets are heuristic guidance, not a measured ideal lap. Do not claim an exact time gain or loss.
Brake threshold: 15%; throttle pickup threshold: 85%. Timestamps are milliseconds from lap start.
Positive brake_delta_m means early braking; positive throttle_delta_m means late throttle.
OBSERVATIONS: {json.dumps(observations)}
Return exactly one plain-text line per supplied turn: Turn <id>: <status>. <one actionable correction>.
Use the supplied status, including insufficient_data. Never call missing data on pace.
Mention the measured input timing and a practical braking/throttle adjustment where available.
No generic summary, invented corners, braking boards, or unmeasured timings. No markdown.
"""


def format_fallback_corner_advice(target_corners: list[CornerDelta]) -> str:
    return "\n".join(f"Turn {c.turn}: {c.diagnosis}." for c in _sort_corners(target_corners))


def clean_gemini_corner_advice(raw_text: str, fallback_corners: list[CornerDelta]) -> str:
    """Clean markdown asterisks, remove ### headers, and normalize into single lines per turn."""
    if not raw_text or not raw_text.strip():
        return format_fallback_corner_advice(fallback_corners)

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    turns: list[tuple[str, str]] = []
    current_turn: str | None = None
    current_parts: list[str] = []

    def flush():
        nonlocal current_turn, current_parts
        if current_turn:
            text = " ".join(p for p in current_parts if p.strip()).strip()
            text = re.sub(r"^[#*•\s-]+", "", text).strip()
            if text:
                turns.append((current_turn, text))
        current_turn = None
        current_parts = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        line = line.replace("**", "").replace("__", "")
        line_clean = re.sub(r"^[#\s]+", "", line).strip()

        # Discard generic headers, empty notes, and section markers
        if re.match(r"^(?:sector\s*\d+\s*(?:summary|fixes)?|summary|corner-by-corner\s*fixes|fixes|notes?)\b", line_clean, re.IGNORECASE):
            continue

        # Match Turn with or without colon: "Turn 15 (Name): advice" or "Turn 15 (Name)"
        turn_match = re.match(r"^(?:[-*•\s]*)(Turns?\s+[\d–-]+(?:\s*\([^)]+\))?)\s*(?::\s*(.*))?$", line_clean, re.IGNORECASE)
        if turn_match:
            flush()
            current_turn = turn_match.group(1).strip()
            after_colon = (turn_match.group(2) or "").strip()
            if after_colon:
                current_parts.append(after_colon)
            continue

        if current_turn:
            sub_m = re.match(r"^(?:[-*•\s]*)([^:]+):\s*(.*)$", line_clean)
            if sub_m and sub_m.group(1).lower().strip() in [
                "braking", "braking/entry", "entry", "apex speed", "apex speed & gear",
                "apex speed and gear", "apex", "exit throttle", "throttle", "exit", "gear", "line"
            ]:
                current_parts.append(sub_m.group(2).strip())
            else:
                current_parts.append(line_clean.lstrip("-*•# "))

    flush()

    if not turns:
        return format_fallback_corner_advice(fallback_corners)

    by_turn = {}
    for turn, advice in turns:
        match = re.match(r"Turn\s+(\d+[A-Za-z]?)\b", turn, re.IGNORECASE)
        if match:
            by_turn[match.group(1)] = advice
    return "\n".join(f"Turn {c.turn}: {by_turn.get(str(c.turn), c.diagnosis)}" for c in _sort_corners(fallback_corners))


def generate_coach_advice(
    track: TrackBenchmark,
    player_lap_time_ms: int,
    corner_deltas: list[CornerDelta],
    focus_sector: int | None = None,
    last_lap_num: int | None = None,
) -> str:
    """Call Google GenAI SDK with automatic fallback to stable models."""
    target_corners = [
        c for c in corner_deltas if focus_sector is None or c.sector == focus_sector
    ]
    # Missing telemetry requires recording guidance, never speculative driving advice.
    measured_corners = [c for c in target_corners if c.status != 'insufficient_data']

    api_key = get_gemini_api_key()
    if not measured_corners or not api_key:
        return format_fallback_corner_advice(target_corners)

    MODELS_TO_TRY = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = build_coach_prompt(track, player_lap_time_ms, measured_corners, focus_sector, last_lap_num)

        last_error = None
        for model_name in MODELS_TO_TRY:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return clean_gemini_corner_advice(response.text.strip(), target_corners)
            except Exception as model_err:
                last_error = model_err
                logger.warning("Model %s failed: %s. Trying next...", model_name, model_err)
                continue

        raise last_error or Exception("All Gemini model endpoints failed.")

    except Exception as e:
        logger.exception("Failed to generate coach advice with Gemini API: %s", e)
        return format_fallback_corner_advice(target_corners)
