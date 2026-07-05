"""
Real-time distance/speed for the four human-made objects that have actually
left the inner solar system, via NASA JPL's Horizons API -- a real, free,
keyless API (confirmed live: https://ssd.jpl.nasa.gov/api/horizons.api).

These are NOT Earth-orbiting satellites: they have no NORAD ID or TLE, so
they can't be placed on the tracking globe the way the watchlist objects
are. Horizons instead numerically integrates their trajectory (from real
tracking data while contact lasted, ballistic physics afterward) and can
report a real current position/velocity relative to Earth for any moment,
including for Pioneer 10/11 which NASA lost contact with decades ago --
their whereabouts are still real, computed physics, not a guess.

Historical facts below (launch dates, milestones) were verified against
NASA/JPL and Wikipedia sources, not written from memory.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
AU_KM = 149_597_870.7  # IAU-defined astronomical unit

PROBES: dict[str, dict] = {
    "voyager_1": {
        "name": "Voyager 1",
        "command": "-31",
        "launched": "1977-09-05",
        "milestone": "First human-made object to reach interstellar space (Aug 25, 2012); the most distant human-made object from Earth.",
    },
    "voyager_2": {
        "name": "Voyager 2",
        "command": "-32",
        "launched": "1977-08-20",
        "milestone": "Reached interstellar space Nov 5, 2018; the only spacecraft to have visited all four giant planets (Jupiter, Saturn, Uranus, Neptune).",
    },
    "pioneer_10": {
        "name": "Pioneer 10",
        "command": "-23",
        "launched": "1972-03-02",
        "milestone": "First spacecraft to cross the asteroid belt and fly by Jupiter. Last signal received in January 2003; still coasting, silently, outward.",
    },
    "pioneer_11": {
        "name": "Pioneer 11",
        "command": "-24",
        "launched": "1973-04-05",
        "milestone": "First spacecraft to fly by Saturn. Last contact in 1995; still coasting, silently, outward.",
    },
}


@dataclass
class ProbeStatus:
    key: str
    name: str
    launched: str
    milestone: str
    epoch: str
    distance_from_earth_km: float
    distance_from_earth_au: float
    speed_km_s: float


def _parse_horizons_vectors(result_text: str) -> dict:
    """Horizons' JSON response wraps its classic fixed-width text table in
    one big "result" string -- there's no structured per-field JSON, so this
    parses the first $$SOE/$$EOE record (closest to the requested start
    time) out of that text."""
    block_match = re.search(r"\$\$SOE(.*?)\$\$EOE", result_text, re.S)
    if not block_match:
        raise ValueError("Horizons response had no $$SOE/$$EOE vector block")

    record_match = re.search(
        r"A\.D\.\s+(?P<epoch>[\w\-:. ]+?)\s+TDB.*?"
        r"VX\s*=\s*(?P<vx>[-\d.Ee+]+)\s+VY\s*=\s*(?P<vy>[-\d.Ee+]+)\s+VZ\s*=\s*(?P<vz>[-\d.Ee+]+).*?"
        r"RG\s*=\s*(?P<rg>[-\d.Ee+]+)\s+RR\s*=\s*(?P<rr>[-\d.Ee+]+)",
        block_match.group(1),
        re.S,
    )
    if not record_match:
        raise ValueError("Could not parse a vector record out of Horizons response")

    vx, vy, vz = (float(record_match[k]) for k in ("vx", "vy", "vz"))
    return {
        "epoch": record_match["epoch"].strip(),
        "distance_km": float(record_match["rg"]),
        "speed_km_s": math.sqrt(vx * vx + vy * vy + vz * vz),
    }


def fetch_probe_status(key: str, session=None, when: datetime | None = None) -> ProbeStatus:
    probe = PROBES[key]
    when = when or datetime.now(timezone.utc)
    # A tight 10-minute window (not a single instant) because Horizons
    # requires START_TIME < STOP_TIME; we only ever use the first returned
    # record, so this is effectively "now" to within a few minutes.
    start = when.strftime("%Y-%m-%d %H:%M")
    stop = (when + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
    params = {
        "format": "json",
        "EPHEM_TYPE": "VECTORS",
        "OBJ_DATA": "NO",
        "VEC_TABLE": "3",
        "COMMAND": probe["command"],
        "CENTER": "@399",  # Earth body center
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": "10m",
    }
    resp = (session or requests).get(HORIZONS_API_URL, params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"Horizons API error for {probe['name']}: {payload['error']}")

    parsed = _parse_horizons_vectors(payload["result"])
    return ProbeStatus(
        key=key,
        name=probe["name"],
        launched=probe["launched"],
        milestone=probe["milestone"],
        epoch=parsed["epoch"],
        distance_from_earth_km=parsed["distance_km"],
        distance_from_earth_au=parsed["distance_km"] / AU_KM,
        speed_km_s=parsed["speed_km_s"],
    )


def fetch_all_probes(session=None, when: datetime | None = None) -> list[ProbeStatus]:
    return [fetch_probe_status(key, session=session, when=when) for key in PROBES]
