"""
tracker/dashboard.py
Builds the Rich terminal dashboard layout from current state snapshots.

Artemis II Live Tracker — created by galfar.exe
"""

import textwrap
from datetime import datetime

from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich import box

from .constants import (
    CREW, NASA_TRACK_URL,
    EARTH_MOON_MEAN_KM,
)
from .utils import (
    fmt_km, fmt_speed, fmt_vec,
    elapsed_hms, progress_bar,
    get_mission_phase, mission_progress, remaining_seconds,
    LAUNCH_TIME,
)


def build_dashboard(
    orbital:    dict,
    updates:    list[str],
    now:        datetime,
    last_fetch: str,
    refresh_s:  int,
    fetching:   bool = False,
) -> Layout:
    """
    Compose the full Rich Layout for the current tick.

    Parameters
    ----------
    orbital    : dict returned by horizons.fetch_orbital_data()
    updates    : list of blog update strings
    now        : current UTC datetime
    last_fetch : human-readable timestamp of the last successful data pull
    refresh_s  : configured refresh interval (shown in footer)
    fetching   : True while a background fetch is in progress
    """

    phase_label, phase_color, elapsed_days = get_mission_phase(now)
    elapsed_sec = (now - LAUNCH_TIME).total_seconds()
    remaining   = remaining_seconds(now)
    progress    = mission_progress(elapsed_days)
    orion       = orbital.get("orion")
    error       = orbital.get("error")

    # ── Root layout ───────────────────────────────────────────────────────────
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
        Layout(name="orbital",  ratio=5),
        Layout(name="position", ratio=3),
    )
    layout["right"].split_column(
        Layout(name="mission", ratio=4),
        Layout(name="blog",    ratio=5),
    )

    # ── HEADER ────────────────────────────────────────────────────────────────
    title = Text(justify="center")
    title.append(
        "  🚀  ARTEMIS II  ·  ORION 'INTEGRITY'  ·  LIVE MISSION TRACKER  🌙  ",
        style="bold bright_white on navy_blue",
    )
    title.append(
        f"\n  {now.strftime('%A, %B %d, %Y  %H:%M:%S UTC')}"
        f"    MET {elapsed_hms(elapsed_sec)}  ",
        style="dim cyan on navy_blue",
    )
    layout["header"].update(
        Panel(title, box=box.HEAVY, border_style="navy_blue", padding=(0, 1))
    )

    # ── ORBITAL DATA ──────────────────────────────────────────────────────────
    ot = Table(
        box=box.SIMPLE_HEAVY, expand=True,
        show_header=True, header_style="bold bright_cyan",
    )
    ot.add_column("Parameter",  style="bold cyan",    min_width=26)
    ot.add_column("Value",      style="bright_white")
    ot.add_column("",           style="dim",          min_width=12)

    if error:
        ot.add_row("⚠  Data Error", f"[red]{error}[/red]", "")
    else:
        ed = orbital.get("earth_dist_km")
        md = orbital.get("moon_dist_km")
        sp = orbital.get("speed_km_s")
        al = orbital.get("altitude_km")

        # Earth distance with a tiny bar showing how far toward the Moon
        if ed is not None:
            moon_pct = min(1.0, ed / EARTH_MOON_MEAN_KM)
            bar = progress_bar(moon_pct, 16)
            ot.add_row(
                "Distance from Earth",
                fmt_km(ed),
                f"[dim]{bar} {moon_pct*100:.1f}% to Moon[/dim]",
            )
        else:
            ot.add_row("Distance from Earth",    "—", "")

        ot.add_row("Distance from Moon",      fmt_km(md), "")
        ot.add_row("Altitude above surface",  fmt_km(al, show_miles=False), "")
        ot.add_row("Speed",                   fmt_speed(sp), "")

        if orion:
            ot.add_row("[dim]── Velocity vector ──[/dim]", "", "")
            ot.add_row("  VX", fmt_vec(orion["vx"]), "")
            ot.add_row("  VY", fmt_vec(orion["vy"]), "")
            ot.add_row("  VZ", fmt_vec(orion["vz"]), "")

    layout["orbital"].update(Panel(
        ot,
        title="[bold yellow]⚡  LIVE ORBITAL DATA  (J2000 Geocentric)[/bold yellow]",
        border_style="yellow", box=box.ROUNDED, padding=(0, 1),
    ))

    # ── POSITION VECTOR ───────────────────────────────────────────────────────
    pt = Table(
        box=box.SIMPLE_HEAVY, expand=True,
        show_header=True, header_style="bold blue",
    )
    pt.add_column("Axis", style="bold cyan", min_width=6)
    pt.add_column("Position (km)",           style="bright_white")

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

    # ── MISSION STATUS ────────────────────────────────────────────────────────
    mt = Table(
        box=box.SIMPLE_HEAVY, expand=True, show_header=False,
    )
    mt.add_column("Key",   style="bold cyan",    min_width=20)
    mt.add_column("Value", style="bright_white")

    bar_str = progress_bar(progress, 22)
    mt.add_row("Current Phase",     f"[{phase_color}]{phase_label}[/]")
    mt.add_row("Mission Day",       f"Day [bold]{elapsed_days:.2f}[/bold] / ~10")
    mt.add_row(
        "Time to Splashdown",
        f"[bright_cyan]{elapsed_hms(remaining)}[/bright_cyan]"
        if remaining > 0
        else "[bright_green]🎉  Splashdown![/bright_green]",
    )
    mt.add_row(
        "Mission Progress",
        f"[{phase_color}]{bar_str}[/]  {min(progress, 1)*100:.1f}%",
    )
    mt.add_row("", "")
    mt.add_row("Spacecraft",  "Orion 'Integrity'  🛸")
    mt.add_row("Mission",     "Free-return lunar flyby")
    mt.add_row("", "")
    for name, agency, role in CREW:
        mt.add_row(
            f"  {agency}",
            f"[bright_white]{name}[/]  [dim]{role}[/dim]",
        )

    layout["mission"].update(Panel(
        mt,
        title="[bold green]🌙  MISSION STATUS & CREW[/bold green]",
        border_style="green", box=box.ROUNDED, padding=(0, 1),
    ))

    # ── NASA BLOG ─────────────────────────────────────────────────────────────
    blog_text = Text()
    if updates:
        for i, entry in enumerate(updates):
            wrapped = textwrap.fill(entry, width=48)
            lines   = wrapped.split("\n")
            if i == 0:
                blog_text.append(f"▶ {lines[0]}\n", style="bright_white bold")
                for line in lines[1:]:
                    blog_text.append(f"  {line}\n", style="bright_white")
            else:
                for line in lines:
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

    # ── FOOTER ────────────────────────────────────────────────────────────────
    footer = Text(justify="center")
    footer.append("  Created by galfar.exe  │  ", style="bold cyan")
    footer.append("Data: JPL Horizons (NAIF -1024)  │  ", style="dim cyan")
    if fetching:
        footer.append("⟳ Fetching…  │  ", style="bold yellow")
    else:
        footer.append(f"Last fetch: {last_fetch}  │  ", style="dim green")
    footer.append(f"Refresh: {refresh_s}s  │  ", style="dim yellow")
    footer.append(f"{NASA_TRACK_URL}  │  ", style="dim cyan")
    footer.append("Ctrl+C to exit  ", style="dim red")

    layout["footer"].update(
        Panel(footer, box=box.SIMPLE, border_style="grey30")
    )

    return layout