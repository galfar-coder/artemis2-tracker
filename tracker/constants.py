"""
tracker/constants.py
All fixed constants: NAIF IDs, URLs, physical values, crew, mission phases.

Artemis II Live Tracker — created by galfar.exe
"""

from datetime import datetime, timezone

# ── Horizons / NASA identifiers ──────────────────────────────────────────────
ORION_NAIF_ID      = "-1024"   # Artemis II Orion 'Integrity' spacecraft
MOON_NAIF_ID       = "301"     # Moon (Luna)
HORIZONS_API       = "https://ssd.jpl.nasa.gov/api/horizons.api"

# ── NASA content URLs ─────────────────────────────────────────────────────────
NASA_LIVE_BLOG_URL = (
    "https://www.nasa.gov/blogs/missions/2026/04/01/live-artemis-ii-launch-day-updates/"
)
NASA_TRACK_URL     = "nasa.gov/trackartemis"

# ── Mission timeline (UTC) ────────────────────────────────────────────────────
# Launch: April 1 2026 at 22:35:00 UTC  (6:35 PM EDT)
LAUNCH_TIME     = datetime(2026, 4,  1, 22, 35, 0, tzinfo=timezone.utc)
# Estimated splashdown: April 11 2026 ~22:00 UTC
SPLASHDOWN_TIME = datetime(2026, 4, 11, 22,  0, 0, tzinfo=timezone.utc)
MISSION_DURATION_DAYS = 10.0

# ── Physical constants ────────────────────────────────────────────────────────
EARTH_RADIUS_KM      = 6_371.0
MOON_RADIUS_KM       = 1_737.4
EARTH_MOON_MEAN_KM   = 384_400.0   # mean Earth–Moon distance
KM_TO_MILES          = 0.621_371
KM_S_TO_MPH          = 2_236.936

# ── Crew manifest ─────────────────────────────────────────────────────────────
# (name, agency, role)
CREW = [
    ("Cdr. Reid Wiseman",   "NASA", "Commander"),
    ("Plt. Victor Glover",  "NASA", "Pilot"),
    ("MS  Christina Koch",  "NASA", "Mission Specialist"),
    ("MS  Jeremy Hansen",   "CSA",  "Mission Specialist"),
]

# ── Mission phases ────────────────────────────────────────────────────────────
# (day_start, day_end, label, rich_color)
MISSION_PHASES = [
    (0.000, 0.125, "🔴 LAUNCH & ASCENT",             "red"),
    (0.125, 1.000, "🔵 EARTH ORBIT — SYSTEM CHECKS",  "blue"),
    (1.000, 1.500, "🟡 TRANSLUNAR INJECTION BURN",    "yellow"),
    (1.500, 5.000, "🟠 TRANSLUNAR COAST",             "dark_orange"),
    (5.000, 6.000, "🌕 LUNAR SPHERE OF INFLUENCE",    "bright_yellow"),
    (6.000, 6.500, "🌙 LUNAR FLYBY",                  "bright_white"),
    (6.500, 9.000, "🟣 RETURN COAST",                 "purple"),
    (9.000, 9.500, "🔵 REENTRY PREP",                 "bright_cyan"),
    (9.500, 10.50, "💧 REENTRY & SPLASHDOWN",         "bright_green"),
]