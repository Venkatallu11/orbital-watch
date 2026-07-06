"""
Real, GLOBAL active-fire detection counts from NASA's FIRMS (Fire
Information for Resource Management System) -- confirmed real API:
https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/<SOURCE>/world/<days>

Unlike USGS's volcano feed (US-only, see volcano.py), FIRMS is genuinely
global: every VIIRS/MODIS fire detection worldwide, not just the US.

REQUIRES A FREE MAP_KEY: unlike NASA's APOD (which has a public DEMO_KEY),
FIRMS has no public shared key -- every user must sign up for their own
free MAP_KEY at https://firms.modaps.eosdis.nasa.gov/api/map_key/ (a
2-minute, no-cost signup). Without one, this feature is skipped entirely
(see cli.py's _fetch_fire_detections_safely), the same way SOCRATES/
SatNOGS/crew/deep-space are skipped when their flags aren't passed.

SOURCE options actually correspond to real satellites already on this
site's watchlist -- VIIRS_SNPP_NRT (Suomi NPP), VIIRS_NOAA20_NRT (NOAA-20),
MODIS_NRT (Terra + Aqua combined, FIRMS doesn't split MODIS by satellite).
"""
from __future__ import annotations

import csv
import io

import requests

FIRMS_AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


def fetch_global_fire_count(map_key: str, source: str = "VIIRS_SNPP_NRT", day_range: int = 1, session=None) -> int:
    """Counts real fire-detection rows in FIRMS' world CSV for the last
    `day_range` day(s) -- each row is one real satellite-detected fire
    pixel. Raises on failure (network/bad key); caller decides how to
    handle that (see cli.py's best-effort wrapper)."""
    url = f"{FIRMS_AREA_URL}/{map_key}/{source}/world/{day_range}"
    resp = (session or requests).get(url, timeout=30)
    resp.raise_for_status()

    text = resp.text
    if text.strip().lower().startswith("invalid") or "error" in text[:200].lower():
        raise RuntimeError(f"FIRMS API returned an error for source {source}: {text[:200]}")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return 0
    return max(len(rows) - 1, 0)  # minus the header row
