#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   🚀 ARTEMIS II LIVE MISSION TRACKER  — FurTek Systems 🐾   ║
║   Tracking Orion 'Integrity' in real-time                    ║
║   Data: JPL Horizons API (NAIF -1024) + NASA Mission Blog    ║
╚══════════════════════════════════════════════════════════════╝

Dependencies:  pip install rich requests
Usage:         python artemis2_tracker.py
               python artemis2_tracker.py --key YOUR_NASA_API_KEY
               python artemis2_tracker.py --refresh 60   (seconds between data pulls)
"""

import sys
import time
import math
import argparse
import re
import textwrap
import threading
import requests
from datetime import datetime, timezone, timedelta
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.align import Align
from rich import box

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

DEFAULT_NASA_KEY    = "DEMO_KEY"   # ← swap with your key from api.nasa.gov
ORION_NAIF_ID       = "-1024"      # Artemis II / Orion 'Integrity'  (Horizons NAIF)
MOON_NAIF_ID        = "301"        # Moon
HORIZONS_API        = "https://ssd.jpl.nasa.gov/api/horizons.api"
NASA_BLOG_URL       = "https://www.nasa.gov/blogs/missions/2026/04/01/live-artemis-ii-launch-day-updates/"
NASA_ARTEMIS_BLOG   = "https://blogs.nasa.gov/artemis/"
DEFAULT_REFRESH     = 60           # seconds between data refreshes
BLOG_REFRESH_EVERY  = 4            # refresh blog every N data cycles

# Mission timeline (UTC)
LAUNCH_TIME         = datetime(2026, 4, 1, 22, 35, 0, tzinfo=timezone.utc)   # 22:35 UTC / 18:35 EDT
SPLASHDOWN_TIME     = datetime(2026, 4, 11, 22, 0, 0, tzinfo=timezone.utc)   # ~Day 10

# Physical constants
EARTH_RADIUS_KM     = 6_371.0
MOON_RADIUS_KM      = 1_737.4
KM_TO_MILES         = 0.621_371
KM_S_TO_MPH         = 2_236.936
EARTH_MOON_DIST_KM  = 384_400.0    # mean

# Mission phases: (day_start, day_end, label, color)
MISSION_PHASES = [
    (0.000, 0.125, "🔴 LAUNCH & ASCENT",            "red"),
    (0.125, 1.000, "🔵 EARTH ORBIT — SYSTEM CHECKS", "blue"),
    (1.000, 1.500, "🟡 TRANSLUNAR INJECTION BURN",   "yellow"),
    (1.500, 5.000, "🟠 TRANSLUNAR COAST",            "dark_orange"),
    (5.000, 6.000, "🌕 LUNAR SPHERE OF INFLUENCE",   "bright_yellow"),
    (6.000, 6.500, "🌙 LUNAR FLYBY",                 "bright_white"),
    (6.500, 9.000, "🟣 RETURN COAST",                "purple"),
    (9.000, 9.500, "🔵 REENTRY PREP",                "bright_cyan"),
    (9.500, 10.5,  "💧 REENTRY & SPLASHDOWN",        "bright_green"),
]

CREW = [
    ("Cdr. Reid Wiseman",    "NASA", "Commander"),
    ("Plt. Victor Glover",   "NASA", "Pilot"),
    ("MS  Christina Koch",   "NASA", "Mission Specialist"),
    ("MS  Jeremy Hansen",    "CSA",  "Mission Specialist"),
]


# ═══════════════════════════════════════════════════════════════
#  JPL HORIZONS API
# ═══════════════════════════════════════════════════════════════

def _horizons_query(naif_id: str, now: datetime) -> str | None:
    """Raw query to JPL Horizons for state vectors. Returns response text or None."""
    # Horizons needs a small time window; we ask for just 1 step at 'now'
    t0 = now.strftime("%Y-%b-%d %H:%M:%S")
    t1 = (now + timedelta(minutes=1)).strftime("%Y-%b-%d %H:%M:%S")
    params = {
        "format":      "text",
        "COMMAND":     f"'{naif_id}'",
        "EPHEM_TYPE":  "'VECTORS'",
        "CENTER":      "'500@399'",    # Earth geocenter
        "START_TIME":  f"'{t0}'",
        "STOP_TIME":   f"'{t1}'",
        "STEP_SIZE":   "'1m'",
        "OUT_UNITS":   "'KM-S'",
        "VEC_TABLE":   "'2'",          # pos + vel + LT + range
        "CSV_FORMAT":  "'NO'",
        "OBJ_DATA":    "'NO'",
        "MAKE_EPHEM":  "'YES'",
    }
    try:
        r = requests.get(HORIZONS_API, params=params, timeout=15)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        return None


def _parse_vectors(text: str) -> dict | None:
    """
    Extract X, Y, Z, VX, VY, VZ from a Horizons VECTORS text response.

    Horizons output between $$SOE / $$EOE looks like:
        X =-2.265601534E+04 Y =-2.543489762E+04 Z = 4.235987132E+03
        VX=-1.234567890E+00 VY= 2.345678901E+00 VZ= 3.456789012E+00
    """
    match = re.search(r'\$\$SOE(.*?)\$\$EOE', text, re.DOTALL)
    if not match:
        return None
    block = match.group(1)

    # Regex handles optional spaces around = and negative signs
    NUM = r'([-+]?\d+\.?\d*[Ee][+-]?\d+)'
    xyz  = re.search(rf'X\s*=\s*{NUM}\s+Y\s*=\s*{NUM}\s+Z\s*=\s*{NUM}',  block)
    vxyz = re.search(rf'VX\s*=\s*{NUM}\s+VY\s*=\s*{NUM}\s+VZ\s*=\s*{NUM}', block)

    if not xyz or not vxyz:
        return None

    return {
        "x":  float(xyz.group(1)),  "y":  float(xyz.group(2)),  "z":  float(xyz.group(3)),
        "vx": float(vxyz.group(1)), "vy": float(vxyz.group(2)), "vz": float(vxyz.group(3)),
    }


def fetch_orbital_data(now: datetime) -> dict:
    """
    Query Horizons for both Orion and the Moon, then compute distances and speed.
    Returns a results dict; any field may be None on failure.
    """
    result = {
        "orion":          None,
        "moon":           None,
        "earth_dist_km":  None,
        "moon_dist_km":   None,
        "altitude_km":    None,
        "speed_km_s":     None,
        "error":          None,
    }

    orion_text = _horizons_query(ORION_NAIF_ID, now)
    if orion_text is None:
        result["error"] = "Horizons API unreachable"
        return result

    if "No ephemeris" in orion_text or "$$SOE" not in orion_text:
        result["error"] = "Orion not yet in Horizons (NAIF -1024 may need 1–2 hrs post-launch)"
        return result

    orion_vec = _parse_vectors(orion_text)
    if not orion_vec:
        result["error"] = "Failed to parse Horizons response"
        return result

    result["orion"] = orion_vec

    # Earth distance (geocentric distance = magnitude of position vector)
    x, y, z = orion_vec["x"], orion_vec["y"], orion_vec["z"]
    earth_dist = math.sqrt(x**2 + y**2 + z**2)
    result["earth_dist_km"] = earth_dist
    result["altitude_km"]   = earth_dist - EARTH_RADIUS_KM

    # Speed (magnitude of velocity vector)
    vx, vy, vz = orion_vec["vx"], orion_vec["vy"], orion_vec["vz"]
    result["speed_km_s"] = math.sqrt(vx**2 + vy**2 + vz**2)

    # Moon distance (query Moon position and compute relative distance)
    moon_text = _horizons_query(MOON_NAIF_ID, now)
    if moon_text and "$$SOE" in moon_text:
        moon_vec = _parse_vectors(moon_text)
        if moon_vec:
            result["moon"] = moon_vec
            dx = x - moon_vec["x"]
            dy = y - moon_vec["y"]
            dz = z - moon_vec["z"]
            result["moon_dist_km"] = math.sqrt(dx**2 + dy**2 + dz**2)

    return result


# ═══════════════════════════════════════════════════════════════
#  NASA BLOG SCRAPER
# ═══════════════════════════════════════════════════════════════

def fetch_mission_updates() -> list[str]:
    """
    Scrape the NASA Artemis II live blog for the latest mission status updates.
    Returns a list of short update strings (newest first).
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    try:
        r = requests.get(NASA_BLOG_URL, headers=headers, timeout=10)
        r.raise_for_status()
        html = r.text

        # Pull the timestamp+body pairs from the blog entries
        # NASA live blog uses <div class="wp-block-..."> structures
        # We'll grab paragraphs that look like status updates
        entries: list[str] = []

        # Try to grab bold timestamps + following text
        timestamp_pattern = re.compile(
            r'<strong[^>]*>((?:\d{1,2}:\d{2}\s*[ap]\.?m\.?|Update|T[\+\-]\d).*?)</strong>.*?<p[^>]*>(.*?)</p>',
            re.DOTALL | re.IGNORECASE
        )
        for m in timestamp_pattern.finditer(html):
            ts   = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            body = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            body = re.sub(r'\s+', ' ', body)
            if ts and body and len(body) > 10:
                entry = f"[{ts}] {body[:120]}{'…' if len(body)>120 else ''}"
                entries.append(entry)

        # Fallback: grab any <p> that looks like a mission update
        if not entries:
            paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
            for p in paras:
                clean = re.sub(r'<[^>]+>', '', p).strip()
                clean = re.sub(r'\s+', ' ', clean)
                if 40 < len(clean) < 300 and any(
                    kw in clean.lower() for kw in
                    ['orion','crew','burn','orbit','separation','maneuver','telemetry','mile','km','spacecraft']
                ):
                    entries.append(clean[:160] + ('…' if len(clean)>160 else ''))
                if len(entries) >= 6:
                    break

        return entries[:6] if entries else ["[Live blog] No structured updates found — check nasa.gov/trackartemis"]

    except requests.RequestException as e:
        return [f"⚠  NASA blog unreachable: {e}"]
    except Exception as e:
        return [f"⚠  Blog parse error: {e}"]


# ═══════════════════════════════════════════════════════════════
#  MISSION PHASE & HELPERS
# ═══════════════════════════════════════════════════════════════

def mission_phase(now: datetime) -> tuple[str, str, float]:
    """Returns (phase_label, phase_color, elapsed_days)."""
    elapsed = (now - LAUNCH_TIME).total_seconds() / 86400.0
    for start, end, label, color in MISSION_PHASES:
        if start <= elapsed < end:
            return label, color, elapsed
    if elapsed >= 10.5:
        return "✅ MISSION COMPLETE", "bright_green", elapsed
    if elapsed < 0:
        return "⏳ PRE-LAUNCH", "dim", elapsed
    return "🔴 LAUNCH & ASCENT", "red", elapsed


def progress_bar(fraction: float, width: int = 28) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(fraction * width)
    return "█" * filled + "░" * (width - filled)


def fmt_km(km: float | None, miles: bool = True) -> str:
    if km is None:
        return "—"
    s = f"{km:,.0f} km"
    if miles:
        s += f"  ({km * KM_TO_MILES:,.0f} mi)"
    return s


def fmt_speed(km_s: float | None) -> str:
    if km_s is None:
        return "—"
    return f"{km_s:.3f} km/s  ({km_s * KM_S_TO_MPH:,.0f} mph)"


def elapsed_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{d}d {h:02d}h {m:02d}m {s:02d}s"


# ═══════════════════════════════════════════════════════════════
#  RICH DASHBOARD BUILDER
# ═══════════════════════════════════════════════════════════════

def build_dashboard(
    orbital:    dict,
    updates:    list[str],
    now:        datetime,
    last_fetch: str,
    refresh_s:  int,
    fetching:   bool = False,
) -> Layout:

    phase_label, phase_color, elapsed_days = mission_phase(now)
    elapsed_sec = (now - LAUNCH_TIME).total_seconds()
    remaining   = max(0, (SPLASHDOWN_TIME - now).total_seconds())
    progress    = elapsed_days / 10.0
    orion       = orbital.get("orion")

    layout = Layout()
    layout.split_column(
        Layout(name="header",  size=4),
        Layout(name="body"),
        Layout(name="footer",  size=3),
    )
    layout["body"].split_row(
        Layout(name="left",  ratio=3),
        Layout(name="right", ratio=2),
    )
    layout["left"].split_column(
        Layout(name="orbital",   ratio=5),
        Layout(name="position",  ratio=3),
    )
    layout["right"].split_column(
        Layout(name="mission",  ratio=4),
        Layout(name="blog",     ratio=5),
    )

    # ─── HEADER ────────────────────────────────────────────────
    title = Text(justify="center")
    title.append("  🚀  ARTEMIS II  ·  ORION 'INTEGRITY'  ·  LIVE MISSION TRACKER  🌙  ",
                 style="bold bright_white on navy_blue")
    title.append(f"\n  {now.strftime('%A, %B %d, %Y  %H:%M:%S UTC')}  "
                 f"  MET {elapsed_hms(elapsed_sec)}  ",
                 style="dim cyan on navy_blue")

    layout["header"].update(
        Panel(title, box=box.HEAVY, border_style="navy_blue", padding=(0, 1))
    )

    # ─── ORBITAL DATA ──────────────────────────────────────────
    ot = Table(box=box.SIMPLE_HEAVY, expand=True, show_header=True,
               header_style="bold bright_cyan")
    ot.add_column("Parameter",         style="bold cyan",   min_width=26)
    ot.add_column("Value",             style="bright_white")
    ot.add_column("",                  style="dim",         min_width=12)  # extra context

    err = orbital.get("error")
    if err:
        ot.add_row("⚠  Data Error", f"[red]{err}[/red]", "")
    else:
        ed = orbital.get("earth_dist_km")
        md = orbital.get("moon_dist_km")
        sp = orbital.get("speed_km_s")
        al = orbital.get("altitude_km")

        # Earth distance with bar showing rough progress to Moon
        if ed is not None:
            moon_pct = min(1.0, ed / EARTH_MOON_DIST_KM)
            bar = progress_bar(moon_pct, 16)
            ot.add_row("Distance from Earth", fmt_km(ed), f"[dim]{bar} {moon_pct*100:.1f}% to Moon[/dim]")
        else:
            ot.add_row("Distance from Earth", "—", "")

        ot.add_row("Distance from Moon", fmt_km(md), "")
        ot.add_row("Altitude above surface", fmt_km(al, miles=False), "")
        ot.add_row("Speed", fmt_speed(sp), "")

        if orion:
            ot.add_row("", "", "")
            ot.add_row("[dim]── Velocity Vector (km/s) ──[/dim]", "", "")
            ot.add_row(f"  VX", f"[{'green' if orion['vx']>=0 else 'red'}]{orion['vx']:+10.4f}[/]  km/s", "")
            ot.add_row(f"  VY", f"[{'green' if orion['vy']>=0 else 'red'}]{orion['vy']:+10.4f}[/]  km/s", "")
            ot.add_row(f"  VZ", f"[{'green' if orion['vz']>=0 else 'red'}]{orion['vz']:+10.4f}[/]  km/s", "")

    layout["orbital"].update(Panel(
        ot,
        title="[bold yellow]⚡  LIVE ORBITAL DATA  (J2000 Geocentric)[/bold yellow]",
        border_style="yellow", box=box.ROUNDED, padding=(0, 1),
    ))

    # ─── POSITION ──────────────────────────────────────────────
    pt = Table(box=box.SIMPLE_HEAVY, expand=True, show_header=True,
               header_style="bold blue")
    pt.add_column("Axis", style="bold cyan", min_width=6)
    pt.add_column("Position (km)",          style="bright_white")

    if orion:
        for axis, val in [("X", orion["x"]), ("Y", orion["y"]), ("Z", orion["z"])]:
            color = "green" if val >= 0 else "red"
            pt.add_row(axis, f"[{color}]{val:+,.1f}[/]")
    else:
        pt.add_row("—", "[dim]Waiting for Horizons data…[/dim]")

    layout["position"].update(Panel(
        pt,
        title="[bold blue]📍  GEOCENTRIC POSITION VECTOR[/bold blue]",
        border_style="blue", box=box.ROUNDED, padding=(0, 1),
    ))

    # ─── MISSION STATUS ────────────────────────────────────────
    mt = Table(box=box.SIMPLE_HEAVY, expand=True, show_header=False)
    mt.add_column("Key",   style="bold cyan",    min_width=20)
    mt.add_column("Value", style="bright_white")

    mt.add_row("Current Phase",    f"[{phase_color}]{phase_label}[/]")
    mt.add_row("Mission Day",      f"Day [bold]{elapsed_days:.2f}[/bold] / ~10")
    mt.add_row("Time to Splashdown", f"[bright_cyan]{elapsed_hms(remaining)}[/bright_cyan]"
               if remaining > 0 else "[bright_green]🎉  Splashdown![/bright_green]")

    bar_str = progress_bar(progress, 22)
    mt.add_row("Mission Progress", f"[{phase_color}]{bar_str}[/]  {min(progress,1)*100:.1f}%")
    mt.add_row("", "")
    mt.add_row("Spacecraft",       "Orion 'Integrity'  🛸")
    mt.add_row("Mission",          "Free-return lunar flyby")
    mt.add_row("", "")
    for name, agency, role in CREW:
        mt.add_row(f"  {agency}", f"[bright_white]{name}[/]  [dim]{role}[/dim]")

    layout["mission"].update(Panel(
        mt,
        title="[bold green]🌙  MISSION STATUS & CREW[/bold green]",
        border_style="green", box=box.ROUNDED, padding=(0, 1),
    ))

    # ─── NASA BLOG ─────────────────────────────────────────────
    blog_text = Text()
    if updates:
        for i, entry in enumerate(updates):
            wrapped = textwrap.fill(entry, width=48)
            lines   = wrapped.split('\n')
            if i == 0:
                blog_text.append(f"▶ {lines[0]}\n", style="bright_white bold")
                for line in lines[1:]:
                    blog_text.append(f"  {line}\n", style="bright_white")
            else:
                blog_text.append(f"  {lines[0]}\n", style="dim white")
                for line in lines[1:]:
                    blog_text.append(f"  {line}\n", style="dim white")
            if i < len(updates) - 1:
                blog_text.append("  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n", style="dim")
    else:
        blog_text.append("  Fetching NASA mission blog…", style="dim")

    layout["blog"].update(Panel(
        blog_text,
        title="[bold magenta]📡  NASA LIVE MISSION BLOG[/bold magenta]",
        border_style="magenta", box=box.ROUNDED, padding=(0, 1),
    ))

    # ─── FOOTER ────────────────────────────────────────────────
    footer = Text(justify="center")
    footer.append("  Data: JPL Horizons (NAIF -1024)  │  ", style="dim cyan")
    if fetching:
        footer.append("⟳ Fetching…  │  ", style="bold yellow")
    else:
        footer.append(f"Last fetch: {last_fetch}  │  ", style="dim green")
    footer.append(f"Refresh: every {refresh_s}s  │  ", style="dim yellow")
    footer.append("nasa.gov/trackartemis  │  ", style="dim cyan")
    footer.append("Ctrl+C to exit  ", style="dim red")

    layout["footer"].update(Panel(footer, box=box.SIMPLE, border_style="grey30"))

    return layout


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="🚀 Artemis II Live Mission Tracker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Data sources:
              • Position / velocity : JPL Horizons API  (ssd.jpl.nasa.gov)
              • Mission status blog : NASA Artemis II live blog
              • NAIF ID for Orion   : -1024

            NASA API key (optional; only needed if you hit DEMO_KEY rate limits):
              Get one free at  https://api.nasa.gov
        """)
    )
    p.add_argument("--key",     default=DEFAULT_NASA_KEY,
                   help="NASA API key (default: DEMO_KEY)")
    p.add_argument("--refresh", type=int, default=DEFAULT_REFRESH,
                   help=f"Data refresh interval in seconds (default: {DEFAULT_REFRESH})")
    return p.parse_args()


def main() -> None:
    args    = parse_args()
    console = Console()

    console.print()
    console.print("[bold bright_white on navy_blue]  🚀  ARTEMIS II LIVE TRACKER  🌙  [/]")
    console.print("[dim]  Connecting to JPL Horizons and NASA feeds…[/dim]")
    console.print(f"[dim]  Orion NAIF ID: {ORION_NAIF_ID}  |  Orbital refresh: every {args.refresh}s[/dim]")
    console.print()
    time.sleep(1)

    # ── SHARED STATE (protected by a lock so background threads
    #    can write safely while the display thread reads) ─────────
    _lock          = threading.Lock()
    _orbital: dict           = {}
    _blog:    list[str]      = ["Connecting to NASA mission blog…"]
    _last_orbital_fetch: str = "—"
    _fetching_orbital:   bool = False
    _fetching_blog:       bool = False

    # ── BACKGROUND THREAD: orbital data ──────────────────────────
    # Sleeps for `args.refresh` seconds BETWEEN fetches, so the
    # display is never blocked by HTTP calls to Horizons.
    def orbital_worker() -> None:
        nonlocal _orbital, _last_orbital_fetch, _fetching_orbital
        while True:
            with _lock:
                _fetching_orbital = True
            try:
                now  = datetime.now(timezone.utc)
                data = fetch_orbital_data(now)
                ts   = now.strftime("%H:%M:%S UTC")
            except Exception as e:
                data = {"error": str(e)}
                ts   = _last_orbital_fetch
            with _lock:
                _orbital             = data
                _last_orbital_fetch  = ts
                _fetching_orbital    = False
            # Wait the full refresh interval before fetching again.
            # time.sleep() here — NOT on the display thread.
            time.sleep(args.refresh)

    # ── BACKGROUND THREAD: NASA blog ─────────────────────────────
    def blog_worker() -> None:
        nonlocal _blog, _fetching_blog
        while True:
            with _lock:
                _fetching_blog = True
            try:
                updates = fetch_mission_updates()
            except Exception as e:
                updates = [f"⚠  Blog error: {e}"]
            with _lock:
                _blog          = updates
                _fetching_blog = False
            time.sleep(args.refresh * BLOG_REFRESH_EVERY)

    # Start both workers as daemon threads (they die with the main process)
    threading.Thread(target=orbital_worker, daemon=True, name="orbital-fetch").start()
    threading.Thread(target=blog_worker,    daemon=True, name="blog-fetch").start()

    # ── DISPLAY LOOP (main thread) ────────────────────────────────
    # Runs every 1 second, just reads shared state and redraws.
    # Never touches the network itself.
    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            with _lock:
                snapshot_orbital  = dict(_orbital)
                snapshot_blog     = list(_blog)
                snapshot_ts       = _last_orbital_fetch
                snapshot_fetching = _fetching_orbital

            dashboard = build_dashboard(
                orbital    = snapshot_orbital,
                updates    = snapshot_blog,
                now        = datetime.now(timezone.utc),
                last_fetch = snapshot_ts,
                refresh_s  = args.refresh,
                fetching   = snapshot_fetching,
            )
            live.update(dashboard)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("  👋  Mission tracking stopped. Godspeed, Artemis II crew! 🚀🌙")
        sys.exit(0)