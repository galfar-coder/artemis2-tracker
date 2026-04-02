#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   🚀 ARTEMIS II LIVE MISSION TRACKER                        ║
║   Tracking Orion 'Integrity' in real-time                   ║
║                                                             ║
║   Created by galfar.exe                                     ║
║   Data:  JPL Horizons API (NAIF -1024)                      ║
║          NASA Artemis II Mission Blog                       ║
╚══════════════════════════════════════════════════════════════╝

Usage
-----
  python main.py                         # use config.toml
  python main.py --key YOUR_KEY          # override API key
  python main.py --refresh 60            # override refresh interval
  python main.py --config my_cfg.toml    # use a different config file

Setup
-----
  pip install -r requirements.txt
  cp config.example.toml config.toml
  # edit config.toml with your NASA API key (optional)
"""

import sys
import time
import argparse
import threading
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.live import Live

from tracker.horizons   import fetch_orbital_data
from tracker.blog       import fetch_mission_updates
from tracker.dashboard  import build_dashboard
from tracker.constants  import ORION_NAIF_ID


# ── Config file loading ───────────────────────────────────────────────────────

def _load_toml(path: Path) -> dict:
    """
    Load a TOML config file.
    Uses the built-in tomllib (Python ≥ 3.11) or the 'tomli' back-port.
    Returns an empty dict if neither is available or the file is missing.
    """
    try:
        import tomllib                          # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib             # pip install tomli
        except ImportError:
            return {}

    if not path.exists():
        return {}

    with open(path, "rb") as f:
        return tomllib.loads(f.read().decode())


def load_config(config_path: Path) -> dict:
    """
    Merge config.toml values with safe built-in defaults.
    Returns a flat dict with keys: nasa_key, refresh_interval, blog_refresh_every.
    """
    defaults = {
        "nasa_key":           "DEMO_KEY",
        "refresh_interval":   60,
        "blog_refresh_every": 4,
    }
    raw = _load_toml(config_path)

    return {
        "nasa_key":           raw.get("api",     {}).get("nasa_key",           defaults["nasa_key"]),
        "refresh_interval":   raw.get("tracker", {}).get("refresh_interval",   defaults["refresh_interval"]),
        "blog_refresh_every": raw.get("tracker", {}).get("blog_refresh_every", defaults["blog_refresh_every"]),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="artemis2_tracker",
        description="🚀 Artemis II Live Mission Tracker — created by galfar.exe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Config file (config.toml) takes precedence over built-in defaults.\n"
            "CLI flags override both.\n\n"
            "Get a free NASA API key at: https://api.nasa.gov\n"
            "(DEMO_KEY works but is rate-limited to 30 req/hour)\n"
        ),
    )
    p.add_argument(
        "--config", default=f"config.toml", metavar="FILE",
        help="path to TOML config file  (default: config.toml)",
    )
    p.add_argument(
        "--key", default=None, metavar="KEY",
        help="NASA API key  (overrides config.toml)",
    )
    p.add_argument(
        "--refresh", type=int, default=None, metavar="SECS",
        help="orbital data refresh interval in seconds  (overrides config.toml)",
    )
    return p.parse_args()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    console = Console()
    args    = parse_args()

    # ── Load config then apply CLI overrides ──────────────────────────────────
    cfg = load_config(Path(args.config))

    if args.key is not None:
        cfg["nasa_key"] = args.key
    if args.refresh is not None:
        cfg["refresh_interval"] = args.refresh

    refresh_s         = cfg["refresh_interval"]
    blog_refresh_s    = refresh_s * cfg["blog_refresh_every"]

    # ── Startup banner ────────────────────────────────────────────────────────
    console.print()
    console.print("[bold bright_white on navy_blue]  🚀  ARTEMIS II LIVE TRACKER  🌙  [/]")
    console.print(f"[dim]  Config:   {args.config}[/dim]")
    console.print(f"[dim]  NASA key: {'*' * max(0, len(cfg['nasa_key'])-4) + cfg['nasa_key'][-4:]}[/dim]")
    console.print(f"[dim]  NAIF ID:  {ORION_NAIF_ID}  (Orion 'Integrity')[/dim]")
    console.print(f"[dim]  Orbital refresh: every {refresh_s}s  |  Blog refresh: every {blog_refresh_s}s[/dim]")
    console.print("[dim]  Connecting…[/dim]")
    console.print()
    time.sleep(1)

    # ── Shared state (lock-protected; written by threads, read by display) ────
    _lock              = threading.Lock()
    _orbital: dict          = {}
    _blog:    list[str]     = ["Connecting to NASA mission blog…"]
    _last_fetch: str        = "—"
    _fetching_orbital: bool = False

    # ── Background thread: orbital data ───────────────────────────────────────
    # Fetches from JPL Horizons, then sleeps refresh_s before repeating.
    # Never blocks the display thread.
    def orbital_worker() -> None:
        nonlocal _orbital, _last_fetch, _fetching_orbital
        while True:
            with _lock:
                _fetching_orbital = True
            try:
                now  = datetime.now(timezone.utc)
                data = fetch_orbital_data(now)
                ts   = now.strftime("%H:%M:%S UTC")
            except Exception as e:
                data = {"error": str(e)}
                ts   = _last_fetch
            with _lock:
                _orbital          = data
                _last_fetch       = ts
                _fetching_orbital = False
            time.sleep(refresh_s)

    # ── Background thread: NASA mission blog ──────────────────────────────────
    def blog_worker() -> None:
        nonlocal _blog
        while True:
            try:
                updates = fetch_mission_updates()
            except Exception as e:
                updates = [f"⚠  Blog error: {e}"]
            with _lock:
                _blog = updates
            time.sleep(blog_refresh_s)

    threading.Thread(target=orbital_worker, daemon=True, name="orbital-fetch").start()
    threading.Thread(target=blog_worker,    daemon=True, name="blog-fetch").start()

    # ── Display loop (main thread only — never touches the network) ───────────
    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            with _lock:
                snap_orbital  = dict(_orbital)
                snap_blog     = list(_blog)
                snap_ts       = _last_fetch
                snap_fetching = _fetching_orbital

            dashboard = build_dashboard(
                orbital    = snap_orbital,
                updates    = snap_blog,
                now        = datetime.now(timezone.utc),
                last_fetch = snap_ts,
                refresh_s  = refresh_s,
                fetching   = snap_fetching,
            )
            live.update(dashboard)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("  👋  Mission tracking stopped. Godspeed, Artemis II crew! 🚀🌙")
        print("  Created by galfar.exe")
        sys.exit(0)