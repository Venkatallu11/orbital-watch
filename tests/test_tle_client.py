"""
Tests the TLE text parser, plus CelesTrakClient.fetch_by_norad_ids' request
construction (mocked -- no real network involved). Confirmed on a real
GitHub Actions run (2026-07-04) that a single comma-joined CATNR query for
multiple IDs silently returns 0 results rather than erroring, so
fetch_by_norad_ids now issues one request per ID -- these tests lock that
behavior in.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import requests  # noqa: E402

from orbital_watch.tle_client import CelesTrakClient, _parse_tle_text  # noqa: E402

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def test_parses_bare_two_line_format():
    records = _parse_tle_text(f"{LINE1}\n{LINE2}\n")
    assert len(records) == 1
    assert records[0].norad_id == 5
    assert records[0].line1 == LINE1
    assert records[0].line2 == LINE2


def test_parses_three_line_format_with_name():
    text = f"VANGUARD 1\n{LINE1}\n{LINE2}\n"
    records = _parse_tle_text(text)
    assert len(records) == 1
    assert records[0].norad_id == 5


def test_parses_multiple_records():
    text = f"VANGUARD 1\n{LINE1}\n{LINE2}\n{LINE1}\n{LINE2}\n"
    records = _parse_tle_text(text)
    assert len(records) == 2


def test_ignores_blank_lines():
    text = f"\n\n{LINE1}\n{LINE2}\n\n"
    records = _parse_tle_text(text)
    assert len(records) == 1


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_by_norad_ids_issues_one_request_per_id():
    calls = []

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            calls.append(params["CATNR"])
            return _FakeResponse(f"{LINE1}\n{LINE2}\n")

    client = CelesTrakClient()
    client._session = FakeSession()

    records = client.fetch_by_norad_ids([5, 25544, 20580])

    assert calls == [5, 25544, 20580]  # one request per ID, not one batched request
    assert len(records) == 3  # each request's TLE combined into one result list


class _FakeHTTPErrorResponse:
    def __init__(self, norad_id):
        self._norad_id = norad_id

    def raise_for_status(self):
        raise requests.exceptions.HTTPError(f"404 Client Error for CATNR={self._norad_id}")


def test_one_decayed_satellite_404_does_not_lose_the_others(capsys):
    """Confirmed on a real run (2026-07-04): a Starlink launched in 2020
    404'd (plausibly deorbited since) while 9 other satellites in the same
    watchlist fetched fine. One bad ID must not discard the other 9."""

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            if params["CATNR"] == 46356:
                return _FakeHTTPErrorResponse(46356)
            return _FakeResponse(f"{LINE1}\n{LINE2}\n")

    client = CelesTrakClient()
    client._session = FakeSession()

    records = client.fetch_by_norad_ids([5, 46356, 25544])

    assert len(records) == 2  # the two good ones, not zero
    captured = capsys.readouterr()
    assert "46356" in captured.out


def test_connection_level_failure_still_propagates_not_swallowed():
    """A 404 for one bad ID is routine and should be skipped (see above),
    but a connection-level failure (the whole site unreachable, like the
    real celestrak.org timeout seen on run #3) means every other request
    would fail too -- that must still raise so the caller's Space-Track
    fallback (see cli.py) actually engages instead of silently returning
    an empty list."""

    class FakeSession:
        def get(self, url, params=None, timeout=None):
            raise requests.exceptions.ConnectTimeout("simulated celestrak.org timeout")

    client = CelesTrakClient()
    client._session = FakeSession()

    try:
        client.fetch_by_norad_ids([25544])
        assert False, "expected ConnectTimeout to propagate"
    except requests.exceptions.ConnectTimeout:
        pass
