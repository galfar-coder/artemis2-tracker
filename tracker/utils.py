"""
tracker/utils.py
Formatting helpers, unit converters, and mission-phase logic.

Artemis II Live Tracker — created by galfar.exe
"""

import math
from datetime import datetime

from .constants import (
    KM_TO_MILES, KM_S_TO_MPH,
    LAUNCH_TIME, SPLASHDOWN_TIME, MISSION_DURATION_DAYS,
    MISSION_PHASES,
)


# ── Unit / value formatters ───────────────────────────────────────────────────

def fmt_km(km: float | None, show_miles: bool = True) -> str:
    """Format a kilometre distance, optionally with miles in parentheses."""
    if km is None:
        return "—"
    s = f"{km:,.0f} km"
    if show_miles:
        s += f"  ({km * KM_TO_MILES:,.0f} mi)"
    return s


def fmt_speed(km_s: float | None) -> str:
    """Format a speed in km/s with mph conversion."""
    if km_s is None:
        return "—"
    return f"{km_s:.3f} km/s  ({km_s * KM_S_TO_MPH:,.0f} mph)"


def fmt_vec(value: float | None) -> str:
    """Format a single velocity-vector component."""
    if value is None:
        return "—"
    color = "green" if value >= 0 else "red"
    return f"[{color}]{value:+10.4f}[/]  km/s"


def elapsed_hms(seconds: float) -> str:
    """Convert a duration in seconds to  Xd HH:MM:SS  string."""
    seconds = max(0, int(seconds))
    d =  seconds // 86_400
    h = (seconds %  86_400) // 3_600
    m = (seconds %   3_600) // 60
    s =  seconds %      60
    return f"{d}d {h:02d}h {m:02d}m {s:02d}s"


def progress_bar(fraction: float, width: int = 28) -> str:
    """Return a unicode block progress bar string."""
    fraction = max(0.0, min(1.0, fraction))
    filled   = int(fraction * width)
    return "█" * filled + "░" * (width - filled)


# ── Mission phase ─────────────────────────────────────────────────────────────

def get_mission_phase(now: datetime) -> tuple[str, str, float]:
    """
    Return (phase_label, rich_color, elapsed_days) for the current time.
    elapsed_days may be negative (pre-launch) or > 10 (post-mission).
    """
    elapsed = (now - LAUNCH_TIME).total_seconds() / 86_400.0

    for day_start, day_end, label, color in MISSION_PHASES:
        if day_start <= elapsed < day_end:
            return label, color, elapsed

    if elapsed >= MISSION_DURATION_DAYS:
        return "✅ MISSION COMPLETE", "bright_green", elapsed
    if elapsed < 0:
        return "⏳ PRE-LAUNCH", "dim", elapsed

    # Fallback (should never hit)
    return "🔴 LAUNCH & ASCENT", "red", elapsed


def mission_progress(elapsed_days: float) -> float:
    """Return mission progress as a 0.0–1.0 fraction."""
    return max(0.0, min(1.0, elapsed_days / MISSION_DURATION_DAYS))


def remaining_seconds(now: datetime) -> float:
    """Seconds until estimated splashdown (can be negative if past)."""
    return (SPLASHDOWN_TIME - now).total_seconds()