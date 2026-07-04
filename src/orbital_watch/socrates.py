"""
CelesTrak SOCRATES conjunction (collision-risk) ingestion.

SOCRATES already runs full-catalog conjunction analysis 3x/day for free
(STK/CAT + SGP4, 7-day look-ahead, all conjunctions within 5km at closest
approach) -- see https://celestrak.org/SOCRATES/. We deliberately do NOT
reimplement conjunction analysis ourselves; we ingest their output and
filter it to a watchlist, which is the actual missing piece (nothing
currently subscribes you to it or filters it to objects you care about).

NOTE ON TESTING: a real GitHub Actions run (2026-07-04) confirmed and
corrected the endpoint path -- see history below. celestrak.org blocks
WebFetch/curl-style automated fetches outright, but the Python `requests`
client running on a real GitHub Actions runner gets through fine (it's
bot-detection on user-agent/fetch-pattern, not a wholesale block), which is
how this got tested for real despite this module being written offline.
  - Real columns: NORAD_CAT_ID_1, OBJECT_NAME_1, DSE_1, NORAD_CAT_ID_2,
    OBJECT_NAME_2, DSE_2, TCA, TCA_RANGE, TCA_RELATIVE_SPEED, MAX_PROB,
    DILUTION -- confirmed against CelesTrak's SOCRATES Format Documentation.
  - DSE_1/DSE_2 (days since [TLE] epoch) indicate how stale each object's
    TLE was when this conjunction was computed -- a large DSE means the
    prediction is less trustworthy. Surfaced but not yet acted on.
  - DILUTION and TCA_RELATIVE_SPEED are captured but not yet used in
    `generate_digest`.
  - The real endpoint is `SOCRATES/table-socrates.php`. An earlier draft
    "corrected" this to `SOCRATES-Plus/table-socrates.php` based on a
    search result that turned out to be wrong -- confirmed by a real 404
    on that exact path on the 2026-07-04 run. Reverted back to `SOCRATES/`,
    which is the original, correct path.
  - `CATNR` on that endpoint takes at most TWO catalog numbers (it's meant
    for "conjunctions involving object A", or "between object A and B" --
    not for passing an entire watchlist at once). That's why
    `fetch_conjunctions` below does NOT filter server-side by watchlist;
    it pulls the broad current result set and relies on
    `filter_to_watchlist` client-side -- which also happens to be exactly
    what CelesTrak's own docs suggest ("download the latest raw CSV
    results to search and filter using your spreadsheet software") for
    anyone who wants more than one object's results at a time.
Still genuinely unverified (the 2026-07-04 run 404'd before reaching the
CSV body, so these haven't been checked against a real response yet): the
exact TCA date format in the CSV, and whether `FORMAT=csv` is really the
right parameter name for this endpoint specifically.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime

import requests

SOCRATES_URL = "https://celestrak.org/SOCRATES/table-socrates.php"


@dataclass
class Conjunction:
    norad_id_1: int
    name_1: str
    norad_id_2: int
    name_2: str
    time_of_closest_approach: datetime
    min_range_km: float
    relative_speed_km_s: float | None
    max_probability: float
    dilution: float | None
    days_since_epoch_1: float | None
    days_since_epoch_2: float | None


def _parse_tca(value: str) -> datetime:
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    # Fallback: the human-readable HTML-table style, e.g. "2026 Jul 05 03:14:22"
    return datetime.strptime(value, "%Y %b %d %H:%M:%S")


def _to_float(value: str) -> float | None:
    try:
        return float(value) if value.strip() else None
    except (ValueError, AttributeError):
        return None


def parse_socrates_csv(text: str) -> list[Conjunction]:
    reader = csv.DictReader(io.StringIO(text))
    conjunctions = []
    for row in reader:
        try:
            conjunctions.append(
                Conjunction(
                    norad_id_1=int(row["NORAD_CAT_ID_1"]),
                    name_1=row.get("OBJECT_NAME_1", "").strip(),
                    norad_id_2=int(row["NORAD_CAT_ID_2"]),
                    name_2=row.get("OBJECT_NAME_2", "").strip(),
                    time_of_closest_approach=_parse_tca(row["TCA"]),
                    min_range_km=float(row["TCA_RANGE"]),
                    relative_speed_km_s=_to_float(row.get("TCA_RELATIVE_SPEED", "")),
                    max_probability=float(row["MAX_PROB"]),
                    dilution=_to_float(row.get("DILUTION", "")),
                    days_since_epoch_1=_to_float(row.get("DSE_1", "")),
                    days_since_epoch_2=_to_float(row.get("DSE_2", "")),
                )
            )
        except (KeyError, ValueError):
            continue  # skip malformed rows rather than crash the whole feed
    return conjunctions


def filter_to_watchlist(conjunctions: list[Conjunction], watchlist: set[int]) -> list[Conjunction]:
    """A conjunction is relevant if EITHER object is on your watchlist --
    you care if your satellite might hit debris, even if the debris itself
    isn't something you're separately tracking."""
    return [c for c in conjunctions if c.norad_id_1 in watchlist or c.norad_id_2 in watchlist]


def fetch_conjunctions(max_results: int = 1000) -> list[Conjunction]:
    """Pulls the broad current SOCRATES result set (all objects, sorted by
    collision probability, up to `max_results`) rather than querying per
    watchlist object -- see module docstring for why. Filter the result
    with `filter_to_watchlist` afterwards."""
    resp = requests.get(
        SOCRATES_URL,
        params={"NAME": ",", "ORDER": "MAXPROB", "MAX": max_results, "FORMAT": "csv"},
        timeout=30,
    )
    resp.raise_for_status()
    return parse_socrates_csv(resp.text)
