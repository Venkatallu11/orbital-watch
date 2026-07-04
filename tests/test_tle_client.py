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
