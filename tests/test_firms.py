"""Tests the NASA FIRMS global fire-count fetcher (offline, mocked -- see
firms.py's docstring for why this can't be verified live without a
personal MAP_KEY, which this repo doesn't have)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.firms import fetch_global_fire_count  # noqa: E402

REAL_SHAPE_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-3.45,112.3,300.1,0.5,0.5,2026-07-05,0130,N,VIIRS,n,2.0NRT,290.2,5.5,N\n"
    "12.1,-70.2,310.5,0.4,0.4,2026-07-05,0130,N,VIIRS,n,2.0NRT,295.1,8.2,N\n"
)


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, text):
        self.text = text
        self.last_url = None

    def get(self, url, timeout=None):
        self.last_url = url
        return _FakeResponse(self.text)


def test_fetch_global_fire_count_counts_real_csv_rows():
    session = _FakeSession(REAL_SHAPE_CSV)
    count = fetch_global_fire_count("testkey", session=session)
    assert count == 2
    assert "testkey" in session.last_url
    assert "world" in session.last_url


def test_fetch_global_fire_count_empty_result_is_zero():
    session = _FakeSession("latitude,longitude,bright_ti4\n")
    assert fetch_global_fire_count("testkey", session=session) == 0


def test_fetch_global_fire_count_raises_on_invalid_key():
    session = _FakeSession("Invalid MAP_KEY")
    try:
        fetch_global_fire_count("badkey", session=session)
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
