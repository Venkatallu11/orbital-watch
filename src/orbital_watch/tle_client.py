"""
Fetches TLEs from Space-Track.org (auth required, richer/faster-updated
catalog) or CelesTrak (no login, good default/fallback).

NOTE ON TESTING: this module is written against each service's documented
API, but could not be exercised against the live endpoints in this sandbox
-- outbound network here is locked to an allowlist that doesn't include
celestrak.org or space-track.org (confirmed: the proxy returns a 403 policy
denial for celestrak.org). Run `python -m orbital_watch.tle_client --selftest`
from an environment with normal internet access to verify connectivity
before relying on this in production.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from orbital_watch.ratelimit import CompositeRateLimiter, RateLimiter

SPACE_TRACK_LOGIN_URL = "https://www.space-track.org/ajaxauth/login"
SPACE_TRACK_QUERY_URL = (
    "https://www.space-track.org/basicspacedata/query/class/gp/"
    "NORAD_CAT_ID/{norad_ids}/orderby/EPOCH desc/format/tle"
)
CELESTRAK_GP_URL = "https://celestrak.org/NORAD/elements/gp.php"


@dataclass
class TleRecord:
    norad_id: int
    line1: str
    line2: str


class SpaceTrackClient:
    """Requires a free Space-Track.org account -- sign up yourself at
    https://www.space-track.org/auth/createAccount, this can't be done on
    your behalf since it's a personal registration/agreement.
    Rate limits: <30 requests/min, <300/hour (per their Spaceflight Safety
    Handbook for Satellite Operators). Both windows are enforced locally
    via `ratelimit.py` before every request -- `acquire()` blocks/sleeps
    rather than risk the account getting suspended for exceeding these.
    """

    def __init__(self, username: str | None = None, password: str | None = None, rate_limiter=None):
        self.username = username or os.environ.get("SPACETRACK_USER")
        self.password = password or os.environ.get("SPACETRACK_PASS")
        if not self.username or not self.password:
            raise ValueError(
                "Space-Track credentials missing. Set SPACETRACK_USER / "
                "SPACETRACK_PASS env vars, or pass username/password directly."
            )
        self._session = requests.Session()
        self._logged_in = False
        self._rate_limiter = rate_limiter or CompositeRateLimiter([
            RateLimiter(max_calls=30, period_seconds=60),
            RateLimiter(max_calls=300, period_seconds=3600),
        ])

    def _login(self) -> None:
        self._rate_limiter.acquire()
        resp = self._session.post(
            SPACE_TRACK_LOGIN_URL,
            data={"identity": self.username, "password": self.password},
            timeout=30,
        )
        resp.raise_for_status()
        self._logged_in = True

    def fetch_tles(self, norad_ids: list[int]) -> list[TleRecord]:
        if not self._logged_in:
            self._login()
        url = SPACE_TRACK_QUERY_URL.format(norad_ids=",".join(str(n) for n in norad_ids))
        self._rate_limiter.acquire()
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        return _parse_tle_text(resp.text)


class CelesTrakClient:
    """No account needed. Good default for public/commercial satellites;
    Space-Track is the better source for less-common or military objects."""

    def __init__(self):
        self._session = requests.Session()

    def fetch_group(self, group: str = "active") -> list[TleRecord]:
        resp = self._session.get(
            CELESTRAK_GP_URL, params={"GROUP": group, "FORMAT": "tle"}, timeout=30
        )
        resp.raise_for_status()
        return _parse_tle_text(resp.text)

    def fetch_by_norad_ids(self, norad_ids: list[int]) -> list[TleRecord]:
        resp = self._session.get(
            CELESTRAK_GP_URL,
            params={"CATNR": ",".join(str(n) for n in norad_ids), "FORMAT": "tle"},
            timeout=30,
        )
        resp.raise_for_status()
        return _parse_tle_text(resp.text)


def _parse_tle_text(text: str) -> list[TleRecord]:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    records = []
    i = 0
    while i < len(lines):
        # 3-line format (name, line1, line2) or bare 2-line -- handle both
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            line1, line2 = lines[i], lines[i + 1]
            i += 2
        elif i + 2 < len(lines) and lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            line1, line2 = lines[i + 1], lines[i + 2]
            i += 3
        else:
            i += 1
            continue
        norad_id = int(line1[2:7])
        records.append(TleRecord(norad_id=norad_id, line1=line1, line2=line2))
    return records


def load_tles_from_file(path: str) -> list[TleRecord]:
    """Offline/fixture mode -- read TLEs from a local file instead of the
    network. Useful for tests, demos, or once you've fetched a batch
    somewhere with internet access and copied it in."""
    with open(path) as f:
        return _parse_tle_text(f.read())


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        print("Testing CelesTrak connectivity...")
        client = CelesTrakClient()
        records = client.fetch_group("stations")
        print(f"OK: fetched {len(records)} TLEs (e.g. ISS should be in there)")
