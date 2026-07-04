"""
CelesTrak SATCAT client + parser -- this is the metadata half of the
"satellite biography" (owner, launch date, object type, decay status).
The maneuver-history half comes from our own detected events (see
biography.py).

NOTE ON TESTING: parser is tested against a fixture built from CelesTrak's
documented SATCAT CSV column schema. The live fetch (`fetch_satcat`) is
untested here for the same network-policy reason as tle_client.py --
verify column names/order against a live download before depending on it.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import requests

SATCAT_CSV_URL = "https://celestrak.org/satcat/records.php"


@dataclass
class SatcatRecord:
    norad_id: int
    object_name: str
    object_type: str  # PAYLOAD, ROCKET BODY, DEBRIS, UNKNOWN
    owner: str
    launch_date: str | None
    launch_site: str | None
    decay_date: str | None
    period_minutes: float | None
    inclination_deg: float | None
    apogee_km: float | None
    perigee_km: float | None


def _to_float(value: str) -> float | None:
    try:
        return float(value) if value.strip() else None
    except (ValueError, AttributeError):
        return None


def parse_satcat_csv(text: str) -> list[SatcatRecord]:
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        try:
            norad_id = int(row["NORAD_CAT_ID"])
        except (KeyError, ValueError):
            continue
        records.append(
            SatcatRecord(
                norad_id=norad_id,
                object_name=row.get("OBJECT_NAME", "").strip(),
                object_type=row.get("OBJECT_TYPE", "").strip(),
                owner=row.get("OWNER", "").strip(),
                launch_date=row.get("LAUNCH_DATE", "").strip() or None,
                launch_site=row.get("LAUNCH_SITE", "").strip() or None,
                decay_date=row.get("DECAY_DATE", "").strip() or None,
                period_minutes=_to_float(row.get("PERIOD", "")),
                inclination_deg=_to_float(row.get("INCLINATION", "")),
                apogee_km=_to_float(row.get("APOGEE", "")),
                perigee_km=_to_float(row.get("PERIGEE", "")),
            )
        )
    return records


def norad_ids_matching_owners(records: list[SatcatRecord], owners: set[str]) -> set[int]:
    """Auto-exclude noisy constellations (e.g. all Starlink/OneWeb) from a
    watchlist by owner, instead of requiring you to hand-list every noisy
    object -- was a "next step" in earlier design discussion, now built.
    Returns the set of NORAD IDs that MATCH (so the caller subtracts them
    from a watchlist) rather than the ones to keep -- that way an object
    missing from the SATCAT data entirely is never accidentally dropped by
    a keep-list that didn't know about it. Owner comparison is
    case-insensitive since SATCAT owner codes/names aren't perfectly
    consistent about casing across entries."""
    owners_lower = {o.lower() for o in owners}
    return {r.norad_id for r in records if r.owner.lower() in owners_lower}


def fetch_satcat(norad_ids: list[int]) -> list[SatcatRecord]:
    """Endpoint and params confirmed against CelesTrak's own SATCAT Format
    Documentation (satcat-format.php): queries take the form
    `records.php?{QUERY}=VALUE[&FORMAT=VALUE]`, with CATNR accepting 1-9
    digits for a single catalog number and FORMAT=CSV for this format --
    celestrak.org itself blocks automated fetches (403), so this hasn't
    been exercised live, but the request shape matches documentation
    exactly rather than being a guess."""
    resp = requests.get(
        SATCAT_CSV_URL,
        params={"CATNR": ",".join(str(n) for n in norad_ids), "FORMAT": "CSV"},
        timeout=30,
    )
    resp.raise_for_status()
    return parse_satcat_csv(resp.text)
