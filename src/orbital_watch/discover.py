"""
Fetches CelesTrak's GROUP catalogs to discover real, currently-active
satellites by category (e.g. "stations", "starlink", "science") -- for
curating watchlist.json/names.json/categories.json with real objects
instead of hand-typed/guessed NORAD IDs.

Not part of the hourly pipeline. Run manually (locally, or via the
discover-candidates GitHub Actions workflow, since this sandbox's outbound
network doesn't reach celestrak.org) when expanding the watchlist.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"


@dataclass
class CatalogEntry:
    norad_id: int
    name: str


def fetch_group(group: str, session=None) -> list[CatalogEntry]:
    """One CelesTrak "GROUP" (e.g. stations, weather, science, gps-ops,
    starlink, oneweb, iridium-NEXT, geo, amateur) as a list of (norad_id,
    name) pairs. An unknown group name returns an empty list rather than
    erroring -- same behavior CelesTrak's API has for bad CATNR values."""
    resp = (session or requests).get(
        CELESTRAK_GP_URL, params={"GROUP": group, "FORMAT": "tle"}, timeout=30
    )
    resp.raise_for_status()
    return _parse_named_tle_text(resp.text)


def _parse_named_tle_text(text: str) -> list[CatalogEntry]:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    entries = []
    i = 0
    while i < len(lines):
        if i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            name = lines[i].strip()
            line1 = lines[i + 1]
            norad_id = int(line1[2:7])
            entries.append(CatalogEntry(norad_id=norad_id, name=name))
            i += 3
        else:
            i += 1
    return entries
