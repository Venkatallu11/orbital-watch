"""Tests the CelesTrak GROUP catalog parser (offline, mocked -- no real
network involved; celestrak.org isn't reachable from this sandbox, see
discover.py's docstring)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.discover import _parse_named_tle_text, fetch_by_name, fetch_group  # noqa: E402

LINE1 = "1 25544U 98067A   26185.50000000  .00016717  00000-0  10270-3 0  9008"
LINE2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.72125391123456"


def test_parses_named_entry():
    text = f"ISS (ZARYA)\n{LINE1}\n{LINE2}\n"
    entries = _parse_named_tle_text(text)
    assert len(entries) == 1
    assert entries[0].norad_id == 25544
    assert entries[0].name == "ISS (ZARYA)"


def test_parses_multiple_named_entries():
    text = f"ISS (ZARYA)\n{LINE1}\n{LINE2}\nISS (ZARYA)\n{LINE1}\n{LINE2}\n"
    entries = _parse_named_tle_text(text)
    assert len(entries) == 2


def test_skips_bare_two_line_records_without_a_name():
    # discover.py is only useful with named records; a name-less bare
    # 2-line pair has nothing worth surfacing, so it's skipped rather than
    # producing an entry with a garbage/missing name.
    text = f"{LINE1}\n{LINE2}\n"
    entries = _parse_named_tle_text(text)
    assert entries == []


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, text):
        self.text = text
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_params = params
        return _FakeResponse(self.text)


def test_fetch_group_passes_group_param_and_parses_result():
    session = _FakeSession(f"ISS (ZARYA)\n{LINE1}\n{LINE2}\n")
    entries = fetch_group("stations", session=session)
    assert session.last_params == {"GROUP": "stations", "FORMAT": "tle"}
    assert len(entries) == 1
    assert entries[0].norad_id == 25544


def test_fetch_by_name_passes_name_param_and_parses_result():
    session = _FakeSession(f"ISS (ZARYA)\n{LINE1}\n{LINE2}\n")
    entries = fetch_by_name("ISS", session=session)
    assert session.last_params == {"NAME": "ISS", "FORMAT": "tle"}
    assert len(entries) == 1
    assert entries[0].name == "ISS (ZARYA)"
