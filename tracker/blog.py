"""
tracker/blog.py
Scrapes the NASA Artemis II live-blog for the latest mission status updates.

Artemis II Live Tracker — created by galfar.exe
"""

import re
import requests

from .constants import NASA_LIVE_BLOG_URL

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}
_REQUEST_TIMEOUT = 10
_MAX_ENTRIES     = 6
_MAX_ENTRY_LEN   = 160

# Keywords that indicate a paragraph is a mission update (not nav/boilerplate)
_MISSION_KEYWORDS = {
    "orion", "crew", "burn", "orbit", "separation", "maneuver",
    "telemetry", "spacecraft", "km", "mile", "mph", "lunar",
    "trajectory", "velocity", "altitude", "stage", "engine",
}


def _strip_tags(html: str) -> str:
    """Remove all HTML tags and collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def fetch_mission_updates() -> list[str]:
    """
    Return up to _MAX_ENTRIES mission update strings scraped from
    the NASA Artemis II live blog, newest first.
    Falls back gracefully on any network or parse error.
    """
    try:
        r = requests.get(NASA_LIVE_BLOG_URL, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        r.raise_for_status()
        html = r.text
    except requests.RequestException as e:
        return [f"⚠  NASA blog unreachable: {e}"]

    entries: list[str] = []

    # ── Strategy 1: timestamped bold headings followed by a <p> ──
    ts_pattern = re.compile(
        r"<strong[^>]*>"
        r"((?:\d{1,2}:\d{2}\s*[ap]\.?m\.?|Update|T[+\-]\d).*?)"
        r"</strong>.*?<p[^>]*>(.*?)</p>",
        re.DOTALL | re.IGNORECASE,
    )
    for m in ts_pattern.finditer(html):
        ts   = _strip_tags(m.group(1))
        body = _strip_tags(m.group(2))
        if ts and body and len(body) > 10:
            text = f"[{ts}] {body}"
            entries.append(text[:_MAX_ENTRY_LEN] + ("…" if len(text) > _MAX_ENTRY_LEN else ""))
        if len(entries) >= _MAX_ENTRIES:
            break

    # ── Strategy 2: any <p> that smells like a mission update ────
    if not entries:
        for p in re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
            clean = _strip_tags(p)
            if 40 < len(clean) < 400 and any(kw in clean.lower() for kw in _MISSION_KEYWORDS):
                entries.append(clean[:_MAX_ENTRY_LEN] + ("…" if len(clean) > _MAX_ENTRY_LEN else ""))
            if len(entries) >= _MAX_ENTRIES:
                break

    return entries if entries else [
        "No structured updates found — visit nasa.gov/trackartemis for live data"
    ]