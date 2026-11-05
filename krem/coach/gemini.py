"""KREM Coach Gemini API client and prompt builder.

Formats deterministic telemetry deltas into prompt context and calls
the Google GenAI API to produce direct, actionable race engineer advice.
"""

from __future__ import annotations

import os
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


def build_coach_prompt(
    track: TrackBenchmark,
    player_lap_time_ms: int,
    corner_deltas: list[CornerDelta],
    focus_sector: int | None = None,
    last_lap_num: int | None = None,
) -> str:
    """Construct a clean structured prompt focused strictly on the last completed lap and next sector."""
    if focus_sector is not None:
        target_corners = [c for c in corner_deltas if c.sector == focus_sector]
        sector_str = f"SECTOR {focus_sector}"
    else:
        target_corners = corner_deltas
        sector_str = "NEXT SECTOR"

    sorted_losses = sorted(
        [c for c in target_corners if c.time_loss_s > 0.04],
        key=lambda c: c.time_loss_s,
        reverse=True,
    )
    if not sorted_losses:
        sorted_losses = target_corners[:3]

    lap_time_str = f"{player_lap_time_ms / 1000.0:.3f}s" if player_lap_time_ms > 0 else "flying lap"
    lap_num_str = f"Lap {last_lap_num}" if last_lap_num else "Last Completed Lap"

    corner_lines: list[str] = []
    for c in sorted_losses:
        line = (
            f"- Turn {c.turn} ({c.name}): Deficit ~{c.time_loss_s:.2f}s | "
            f"Your Apex Speed: {c.player_min_speed_kph:.0f} km/h (Ghost target: {c.ideal_apex_speed_kph:.0f} km/h in gear {c.ideal_apex_gear}) | "
        )
        if c.brake_delta_m is not None:
            if c.brake_delta_m > 0:
                line += f"Braked {c.brake_delta_m:.0f}m too early | "
            else:
                line += f"Braked {abs(c.brake_delta_m):.0f}m late | "
        if c.throttle_delta_m is not None and c.throttle_delta_m > 0:
            line += f"Throttle pickup delayed by {c.throttle_delta_m:.0f}m | "
        line += f"Observation: {c.diagnosis}. Reference note: {c.notes}"
        corner_lines.append(line)

    prompt = f"""You are an elite Formula 1 Performance Race Engineer delivering concise, radio-briefing coaching to your driver.

CONTEXT:
- Circuit: {track.track_name}
- Evaluated Lap: {lap_num_str} (Lap Time: {lap_time_str})
- Focus Zone: {sector_str} (Approaching now on track)

LAST COMPLETED LAP TELEMETRY DEFICITS IN {sector_str}:
{chr(10).join(corner_lines)}

INSTRUCTIONS:
1. Focus EXCLUSIVELY on {sector_str} of the upcoming lap based strictly on mistakes made in {lap_num_str}. Do not review the entire circuit.
2. For each corner in this sector where time was dropped, give concise, direct technical corrections:
   - Specific braking point adjustment (e.g. "push braking 15m deeper to the 100m board").
   - Apex speed and gear target (e.g. "carry 3rd gear through the apex at ~110 km/h").
   - Exit throttle timing.
3. Structure your response cleanly using bullet points and bold highlights:
   - **SECTOR {focus_sector or 1} SUMMARY**: 1 sentence on the key leak in this sector.
   - **CORNER-BY-CORNER FIXES**: Clear bullet points per turn.
   - **NEXT SECTOR TARGET**: Exactly 2 actionable bullet points to execute right now.

Maintain a direct, professional race-radio persona (like Bono or GP). Avoid fluffy introductions.
"""
    return prompt


def generate_coach_advice(
    track: TrackBenchmark,
    player_lap_time_ms: int,
    corner_deltas: list[CornerDelta],
    focus_sector: int | None = None,
    last_lap_num: int | None = None,
) -> str:
    """Call Google GenAI SDK with automatic fallback to stable models."""
    api_key = get_gemini_api_key()
    if not api_key:
        return (
            "⚠️ **Gemini API Key Required**\n\n"
            "To activate live AI race coaching, configure your `GEMINI_API_KEY` in `.env` or in the connection box above.\n\n"
            f"**Deterministic Deficits for Sector {focus_sector or 1} (Last Lap):**\n"
            + "\n".join(
                f"- **Turn {c.turn} ({c.name})**: {c.diagnosis} (Target: {c.ideal_apex_speed_kph} km/h in G{c.ideal_apex_gear})"
                for c in corner_deltas if focus_sector is None or c.sector == focus_sector
            )
        )

    # Use stable models that returned 200 OK
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
                    return response.text
            except Exception as model_err:
                last_error = model_err
                logger.warning("Model %s failed: %s. Trying next...", model_name, model_err)
                continue

        raise last_error or Exception("All Gemini model endpoints failed.")

    except Exception as e:
        logger.exception("Failed to generate coach advice with Gemini API: %s", e)
        sector_corners = [
            c for c in corner_deltas if focus_sector is None or c.sector == focus_sector
        ]
        top_corners = sorted(sector_corners, key=lambda c: c.time_loss_s, reverse=True)[:3]
        
        fallback_lines = [
            f"### Sector {focus_sector or 1} Telemetry Briefing (Last Completed Lap)",
            f"*Primary time leak in Sector {focus_sector or 1}: Braking and apex speed deficits vs Ideal Ghost.*\n",
        ]
        for c in top_corners:
            fallback_lines.append(
                f"- **Turn {c.turn} ({c.name})**:\n"
                f"  - **Issue**: {c.diagnosis}\n"
                f"  - **Target**: Apex speed **{c.ideal_apex_speed_kph:.0f} km/h** in **Gear {c.ideal_apex_gear}**\n"
                f"  - **Guideline**: {c.notes}"
            )
        fallback_lines.append("\n**NEXT SECTOR TARGET:**")
        fallback_lines.append("- Move braking zones deeper into heavy deceleration points.")
        fallback_lines.append("- Commit to early throttle pickup on corner exits.")
        return "\n".join(fallback_lines)
