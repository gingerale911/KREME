"""KREM Coach Gemini API client and prompt builder.

Formats deterministic telemetry deltas into prompt context and calls
the Google GenAI API to produce direct, corner-by-corner race engineer advice.
"""

from __future__ import annotations

import os
import re
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

    lap_time_str = f"{player_lap_time_ms / 1000.0:.3f}s" if player_lap_time_ms > 0 else "flying lap"
    lap_num_str = f"Lap {last_lap_num}" if last_lap_num else "Last Completed Lap"

    corner_lines: list[str] = []
    for c in target_corners:
        name_str = f" ({c.name})" if c.name and c.name != f"Turn {c.turn}" else ""
        if c.time_loss_s > 0.04:
            line = (
                f"- Turn {c.turn}{name_str}: Time dropped ~{c.time_loss_s:.2f}s | "
                f"Your Apex Speed: {c.player_min_speed_kph:.0f} km/h vs Target: {c.ideal_apex_speed_kph:.0f} km/h (Gear {c.ideal_apex_gear}) | "
            )
            if c.brake_delta_m is not None:
                if c.brake_delta_m > 0:
                    line += f"Braked {c.brake_delta_m:.0f}m too early | "
                else:
                    line += f"Braked {abs(c.brake_delta_m):.0f}m late | "
            if c.throttle_delta_m is not None and c.throttle_delta_m > 0:
                line += f"Throttle pick-up delayed by {c.throttle_delta_m:.0f}m | "
            line += f"Observation: {c.diagnosis}. Reference note: {c.notes}"
        else:
            line = (
                f"- Turn {c.turn}{name_str}: On pace (+{c.time_loss_s:.2f}s). "
                f"Apex Speed: {c.player_min_speed_kph:.0f} km/h (Target: {c.ideal_apex_speed_kph:.0f} km/h in G{c.ideal_apex_gear})."
            )
        corner_lines.append(line)

    prompt = f"""You are an elite Formula 1 Performance Race Engineer delivering concise, corner-by-corner advice over the team radio.

CIRCUIT: {track.track_name}
EVALUATED LAP: {lap_num_str} (Lap Time: {lap_time_str})
FOCUS SECTOR: {sector_str} (Approaching on track now)

CORNERS IN {sector_str} FROM LAST LAP:
{chr(10).join(corner_lines)}

INSTRUCTIONS:
1. Provide your coaching strictly for every corner in {sector_str} in sequential order (Turn 1, Turn 2, etc.).
2. Do NOT output any introductory text, pleasantries, summary headers (do NOT write "SUMMARY" or "FIXES"), or conclusion paragraphs.
3. Do NOT use markdown bold asterisks (**) or bullet points. Output strictly plain text.
4. Output strictly one plain-text line per corner:
Turn <N> (<Turn Name if available>): <1-2 sentences of direct technical correction. Specify braking adjustment (in meters deeper/earlier), target apex speed (km/h) and gear, and exit throttle timing. If the driver is already on pace with no significant time loss, state "On pace — maintain entry line and carry target speed km/h in gear target gear.">

EXAMPLE OUTPUT FORMAT:
Turn 1 (Koval Hairpin): Push braking 12m deeper to the 80m board. Carry 3rd gear through the apex at 105 km/h, then get on full throttle earlier on exit.
Turn 2: On pace — commit flat through the bend in 5th gear.
"""
    return prompt


def format_fallback_corner_advice(target_corners: list[CornerDelta]) -> str:
    """Deterministic fallback formatting corner by corner."""
    target_corners = _sort_corners(target_corners)
    lines: list[str] = []
    for c in target_corners:
        name_str = f" ({c.name})" if c.name and c.name != f"Turn {c.turn}" else ""
        if c.time_loss_s > 0.05:
            advice_parts = []
            if c.brake_delta_m is not None:
                if c.brake_delta_m > 0:
                    advice_parts.append(f"move braking point {c.brake_delta_m:.0f}m deeper")
                else:
                    advice_parts.append(f"brake {abs(c.brake_delta_m):.0f}m earlier to hit apex")
            advice_parts.append(f"target {c.ideal_apex_speed_kph:.0f} km/h apex speed in gear {c.ideal_apex_gear}")
            if c.throttle_delta_m is not None and c.throttle_delta_m > 0:
                advice_parts.append(f"pick up throttle {c.throttle_delta_m:.0f}m earlier on exit")
            joined = ". ".join(p.capitalize() for p in advice_parts) + "."
            lines.append(f"Turn {c.turn}{name_str}: {joined} ({c.diagnosis})")
        else:
            lines.append(
                f"Turn {c.turn}{name_str}: On pace — maintain entry line and carry {c.ideal_apex_speed_kph:.0f} km/h in gear {c.ideal_apex_gear}."
            )
    return "\n".join(lines)


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

    return "\n".join(f"{turn}: {advice}" for turn, advice in turns)


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

    api_key = get_gemini_api_key()
    if not api_key:
        return format_fallback_corner_advice(target_corners)

    MODELS_TO_TRY = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = build_coach_prompt(track, player_lap_time_ms, corner_deltas, focus_sector, last_lap_num)

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
