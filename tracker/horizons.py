"""
tracker/horizons.py
All communication with NASA/JPL's Horizons ephemeris API.

Horizons docs:  https://ssd-api.jpl.nasa.gov/doc/horizons.html
Orion NAIF ID:  -1024  (Artemis II spacecraft)

Artemis II Live Tracker — created by galfar.exe
"""

import math
import re
from datetime import datetime, timedelta

import requests

from .constants import (
    HORIZONS_API,
    ORION_NAIF_ID,
    MOON_NAIF_ID,
    EARTH_RADIUS_KM,
)

# Timeout for a single Horizons HTTP request (seconds)
_REQUEST_TIMEOUT = 15

# Regex for a scientific-notation float that may or may not have a leading space
_NUM = r"([-+]?\d+\.?\d*[Ee][+-]?\d+)"


def _query_horizons(naif_id: str, now: datetime) -> str | None:
    """
    Make a raw GET request to JPL Horizons for VECTOR state data at `now`.
    Returns the raw response text, or None on network error.
    """
    # Horizons needs a non-zero time window — we request 1 minute
    t0 = now.strftime("%Y-%b-%d %H:%M:%S")
    t1 = (now + timedelta(minutes=1)).strftime("%Y-%b-%d %H:%M:%S")

    params = {
        "format":     "text",
        "COMMAND":    f"'{naif_id}'",
        "EPHEM_TYPE": "'VECTORS'",
        "CENTER":     "'500@399'",   # Earth geocenter (J2000)
        "START_TIME": f"'{t0}'",
        "STOP_TIME":  f"'{t1}'",
        "STEP_SIZE":  "'1m'",
        "OUT_UNITS":  "'KM-S'",
        "VEC_TABLE":  "'2'",         # position + velocity + LT + range
        "CSV_FORMAT": "'NO'",
        "OBJ_DATA":   "'NO'",
        "MAKE_EPHEM": "'YES'",
    }

    try:
        r = requests.get(HORIZONS_API, params=params, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None


def _parse_state_vectors(text: str) -> dict | None:
    """
    Extract X, Y, Z, VX, VY, VZ from a Horizons VECTORS text block.

    The $$SOE / $$EOE section looks like:
        X =-2.265601534E+04 Y =-2.543489762E+04 Z = 4.235987132E+03
        VX=-1.234567890E+00 VY= 2.345678901E+00 VZ= 3.456789012E+00
    Note the optional space before the sign — the regex handles both.
    """
    soe = re.search(r"\$\$SOE(.*?)\$\$EOE", text, re.DOTALL)
    if not soe:
        return None

    block = soe.group(1)

    xyz  = re.search(
        rf"X\s*=\s*{_NUM}\s+Y\s*=\s*{_NUM}\s+Z\s*=\s*{_NUM}", block
    )
    vxyz = re.search(
        rf"VX\s*=\s*{_NUM}\s+VY\s*=\s*{_NUM}\s+VZ\s*=\s*{_NUM}", block
    )

    if not xyz or not vxyz:
        return None

    return {
        "x":  float(xyz.group(1)),
        "y":  float(xyz.group(2)),
        "z":  float(xyz.group(3)),
        "vx": float(vxyz.group(1)),
        "vy": float(vxyz.group(2)),
        "vz": float(vxyz.group(3)),
    }


def fetch_orbital_data(now: datetime) -> dict:
    """
    Query Horizons for both Orion and the Moon, then derive:
      - Earth distance  (km)
      - Altitude above surface  (km)
      - Speed  (km/s)
      - Moon distance  (km)

    Returns a dict; any derived value is None on failure.
    Always has an 'error' key (None = no error).
    """
    result: dict = {
        "orion":         None,
        "moon":          None,
        "earth_dist_km": None,
        "moon_dist_km":  None,
        "altitude_km":   None,
        "speed_km_s":    None,
        "error":         None,
    }

    # ── Orion ──
    orion_text = _query_horizons(ORION_NAIF_ID, now)
    if orion_text is None:
        result["error"] = "JPL Horizons unreachable — check your connection"
        return result

    if "No ephemeris" in orion_text or "$$SOE" not in orion_text:
        result["error"] = (
            "Orion (NAIF -1024) not yet in Horizons — "
            "may need 1–2 hrs after launch to propagate"
        )
        return result

    orion_vec = _parse_state_vectors(orion_text)
    if not orion_vec:
        result["error"] = "Could not parse Horizons vector block"
        return result

    result["orion"] = orion_vec

    x, y, z       = orion_vec["x"], orion_vec["y"], orion_vec["z"]
    vx, vy, vz    = orion_vec["vx"], orion_vec["vy"], orion_vec["vz"]
    earth_dist     = math.sqrt(x**2 + y**2 + z**2)

    result["earth_dist_km"] = earth_dist
    result["altitude_km"]   = earth_dist - EARTH_RADIUS_KM
    result["speed_km_s"]    = math.sqrt(vx**2 + vy**2 + vz**2)

    # ── Moon (for relative distance) ──
    moon_text = _query_horizons(MOON_NAIF_ID, now)
    if moon_text and "$$SOE" in moon_text:
        moon_vec = _parse_state_vectors(moon_text)
        if moon_vec:
            result["moon"] = moon_vec
            dx = x - moon_vec["x"]
            dy = y - moon_vec["y"]
            dz = z - moon_vec["z"]
            result["moon_dist_km"] = math.sqrt(dx**2 + dy**2 + dz**2)

    return result