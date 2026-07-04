"""
Tests the TLE text parser only -- no network involved, so these run
anywhere. The actual HTTP calls in SpaceTrackClient/CelesTrakClient are
written to each service's documented API but are NOT covered by tests here,
since this sandbox can't reach celestrak.org or space-track.org (confirmed
403 policy denial at the network proxy). Verify with
`python -m orbital_watch.tle_client --selftest` from a normal-internet
environment before depending on this in production.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.tle_client import _parse_tle_text  # noqa: E402

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
