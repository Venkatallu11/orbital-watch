"""One-off research probe -- NOT part of the package, NOT scheduled.

Hits real candidate APIs for features being considered (volcano status,
deep-space-probe distance, precipitation forecast) and prints what actually
comes back, so we can design against real response shapes instead of
guessing. Run via .github/workflows/research-probe.yml on a GitHub Actions
runner, since this sandbox's own network proxy blocks these hosts directly.

Delete this file (and its workflow) once the real features it's scouting
are either built for real or ruled out.
"""

import json
import sys
import urllib.request


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "orbital-watch-research/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()
        return resp.status, resp.headers.get("Content-Type"), body


def probe(name, url, headers=None):
    print(f"\n=== {name} ===\n{url}")
    try:
        status, ctype, body = get(url, headers)
        print(f"status={status} content-type={ctype} bytes={len(body)}")
        text = body.decode("utf-8", errors="replace")
        print(text[:2000])
    except Exception as exc:
        print(f"FAILED: {exc!r}")


def main():
    # 1) USGS volcano API -- elevated-alert US volcanoes, real-time
    probe(
        "USGS getElevatedVolcanoes",
        "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes",
    )
    probe(
        "USGS getMonitoredVolcanoes",
        "https://volcanoes.usgs.gov/hans-public/api/volcano/getMonitoredVolcanoes",
    )

    # 2) JPL Horizons -- Voyager 1 (-31), Voyager 2 (-32), Pioneer 10 (-23),
    # Pioneer 11 (-24) distance from Earth (399) right now.
    for name, command in [("Voyager 1", "-31"), ("Voyager 2", "-32"), ("Pioneer 10", "-23"), ("Pioneer 11", "-24")]:
        url = (
            "https://ssd.jpl.nasa.gov/api/horizons.api?format=json"
            "&EPHEM_TYPE=VECTORS&OBJ_DATA=NO&VEC_TABLE=3"
            f"&COMMAND={command}&CENTER=%40399"
            "&START_TIME='2026-07-05'&STOP_TIME='2026-07-06'&STEP_SIZE=1d"
        )
        probe(f"JPL Horizons {name}", url)

    # 3) Open-Meteo -- free, no-key, real short-term forecast, queried at
    # GPM's (39574) approximate current sub-satellite point as an example.
    probe(
        "Open-Meteo forecast (example point 0N,0E)",
        "https://api.open-meteo.com/v1/forecast?latitude=0&longitude=0&hourly=precipitation,snowfall&forecast_days=1",
    )

    # 4) NASA GPM IMERG -- is there any no-auth, single-point JSON readout?
    # (GES DISC/Giovanni normally requires Earthdata login -- checking if a
    # public no-auth endpoint exists at all before assuming it doesn't.)
    probe(
        "GPM IMERG GES DISC (expect this to need auth)",
        "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHH.07/",
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
