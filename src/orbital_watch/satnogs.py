"""
SatNOGS cross-check.

Honest scope note: a full Doppler-curve cross-check (comparing SatNOGS'
observed frequency shift against what the current TLE predicts) needs
signal processing over raw IQ/waterfall data, which is a separate project
on its own. That's NOT what this does.

What this DOES do, which is still a genuinely useful independent signal:
tracks each object's SatNOGS observation *success rate* over time. SatNOGS
ground stations point using the object's current TLE -- if a satellite
that's normally reliably observed suddenly gets a run of failed/bad
observations, that's an independent physical hint that something about the
object changed (attitude, or the TLE no longer matches where it actually
is), separate from and corroborating the TLE-residual signal.

NOTE ON TESTING: `summarize_observations` (the actual logic) is tested
against a fixture matching the REAL schema, confirmed by reading
satnogs-network's actual source on GitLab (network/api/serializers.py,
filters.py, pagination.py -- librespacefoundation/satnogs/satnogs-network),
since network.satnogs.org itself blocks automated fetches (403) the same
way celestrak.org does. This caught two real mistakes in an earlier draft:
  - The field is `status`, not `vetted_status` (that name doesn't exist in
    the current API). Values are "good" / "bad" / "failed" / "unknown" /
    "future" (scheduled, hasn't happened yet).
  - The query param to filter by satellite is `norad_cat_id`, not
    `satellite__norad_cat_id`.
  - Pagination is cursor-based with a fixed page_size=25 and no client
    -adjustable page size param -- there is no `limit` param, so it isn't
    sent as one anymore.
`fetch_observations`'s live HTTP call is still untested here (network.
satnogs.org itself is unreachable from this sandbox), but the request shape
now matches the real API rather than a guess.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

SATNOGS_OBSERVATIONS_URL = "https://network.satnogs.org/api/observations/"

GOOD_STATUSES = {"good"}
BAD_STATUSES = {"bad", "failed"}
PENDING_STATUSES = {"unknown", "future"}  # not yet vetted, or scheduled but not yet observed


@dataclass
class ObservationHealth:
    norad_id: int
    total_observations: int
    good_count: int
    bad_count: int
    unvetted_count: int
    success_rate: float | None  # good / (good + bad), None if nothing vetted yet
    is_degraded: bool
    reason: str


def summarize_observations(norad_id: int, observations: list[dict], degraded_threshold: float = 0.5) -> ObservationHealth:
    """`observations` is a list of SatNOGS API observation dicts, each with
    a `status` field in {"good", "bad", "failed", "unknown", "future"} --
    confirmed against satnogs-network's actual source, see module
    docstring. Most recent observations should be first (the API's own
    default ordering is -start, -end)."""
    good = sum(1 for o in observations if o.get("status") in GOOD_STATUSES)
    bad = sum(1 for o in observations if o.get("status") in BAD_STATUSES)
    unvetted = sum(1 for o in observations if o.get("status") in PENDING_STATUSES)

    vetted_total = good + bad
    success_rate = (good / vetted_total) if vetted_total > 0 else None

    is_degraded = success_rate is not None and success_rate < degraded_threshold and vetted_total >= 3
    if is_degraded:
        reason = (
            f"only {good}/{vetted_total} recent vetted observations were good "
            f"({success_rate:.0%}) -- worth checking against the TLE-residual signal"
        )
    elif success_rate is None:
        reason = "not enough vetted observations yet to judge"
    else:
        reason = f"{good}/{vetted_total} recent vetted observations were good ({success_rate:.0%})"

    return ObservationHealth(
        norad_id=norad_id,
        total_observations=len(observations),
        good_count=good,
        bad_count=bad,
        unvetted_count=unvetted,
        success_rate=success_rate,
        is_degraded=is_degraded,
        reason=reason,
    )


def fetch_observations(norad_id: int) -> list[dict]:
    """Returns up to 25 observations (the API's fixed page size), most
    recent first. Page further with the `next` cursor URL in the response
    if you need more -- not implemented here since 25 recent observations
    is plenty for a health-check signal."""
    resp = requests.get(
        SATNOGS_OBSERVATIONS_URL,
        params={"norad_cat_id": norad_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
