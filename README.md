# 🚀 Artemis II Live Mission Tracker

A real-time terminal dashboard tracking NASA's **Artemis II** mission.<br>
Humanity's first crewed lunar journey since Apollo 17 in 1972.

Built by **galfar.exe**

---

## What it shows

| Panel | Data |
|---|---|
| **Live Orbital Data** | Distance from Earth & Moon, altitude, speed (km/s & mph), velocity vector |
| **Geocentric Position** | X/Y/Z position vector in the J2000 Earth-centred frame |
| **Mission Status** | Current mission phase, elapsed time, countdown to splashdown, crew |
| **NASA Mission Blog** | Latest updates scraped from NASA's Artemis II live blog |

The display updates every second. Orbital data is fetched from **JPL Horizons**
on a configurable interval (default 60 s) on a background thread, so the
terminal never freezes while waiting for a response.

---

## Quick start

```bash
git clone https://github.com/galfar-coder/artemis2-tracker
cd artemis2-tracker

pip install -r requirements.txt

cp config.example.toml config.toml
# edit config.toml and add your NASA API key (optional — see below)

python main.py
```

---

## Configuration

Copy `config.example.toml` → `config.toml` (already in `.gitignore` so your
key stays private), then edit:

```toml
[api]
nasa_key = "YOUR_KEY_HERE"   # free key at https://api.nasa.gov

[tracker]
refresh_interval   = 60      # seconds between Horizons pulls
blog_refresh_every = 4       # blog refreshes every N orbital cycles
```

`config.toml` is **never committed** — only the safe template
`config.example.toml` is tracked by git.

### Getting a free NASA API key

1. Visit <https://api.nasa.gov>
2. Fill in the sign-up form — key arrives instantly by email
3. Paste it into `config.toml`

The default `DEMO_KEY` works fine but is shared and rate-limited to
**30 requests/hour**. With a personal key the limit rises to **1 000/hour**.

### CLI overrides

```bash
python main.py --key  YOUR_KEY        # override config.toml key
python main.py --refresh 60           # slower polling (saves API quota)
python main.py --config other.toml    # use a different config file
```

---

## Data sources

| Source | What for |
|---|---|
| [JPL Horizons API](https://ssd.jpl.nasa.gov/horizons/) | Real-time position & velocity vectors for Orion (NAIF ID **-1024**) and the Moon |
| [NASA Artemis II Live Blog](https://www.nasa.gov/blogs/missions/2026/04/01/live-artemis-ii-launch-day-updates/) | Mission status updates |

---

## Project structure

```
artemis2-tracker/
├── main.py                  ← entry point (config loading, threads, display loop)
├── config.example.toml      ← safe template — copy to config.toml
├── requirements.txt
├── .gitignore               ← config.toml excluded
└── tracker/
    ├── __init__.py
    ├── constants.py         ← NAIF IDs, URLs, physical constants, crew, phases
    ├── horizons.py          ← JPL Horizons API queries & vector parsing
    ├── blog.py              ← NASA mission blog scraper
    ├── dashboard.py         ← Rich terminal layout builder
    └── utils.py             ← formatting helpers & mission-phase logic
```

---

## Requirements

- Python **3.11+** (uses built-in `tomllib`)  
  *Python 3.9 / 3.10 also work — `tomli` back-port is auto-installed via requirements.txt*
- `rich` — terminal UI
- `requests` — HTTP

---

## License

MIT — do whatever you want with it. Credit appreciated but not required.

---

*Created by **galfar.exe***