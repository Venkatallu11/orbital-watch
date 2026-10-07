"""Tests for the God's-eye-view upgrade: element-change maneuver detection,
TLE name capture, and maneuver-history exposure in site data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sgp4.api import Satrec

from orbital_watch.propagate import compute_element_changes
from orbital_watch.tle_client import _parse_tle_text
from orbital_watch.site_data import build_site_data

# Real ISS TLE (epoch 2026) -- baseline for synthetic modifications.
ISS_L1 = "1 25544U 98067A   26007.50000000  .00016717  00000-0  10270-3 0  9000"
ISS_L2 = "2 25544  51.6416 208.9163 0006703  69.9862  25.2906 15.72125391    10"


def _set_inclination(line2: str, incl_deg: float) -> str:
    """Replace the inclination field (cols 9-16, 1-based) in TLE line 2."""
    return line2[:8] + f"{incl_deg:8.4f}" + line2[16:]


def _set_mean_motion(line2: str, mm_rev_day: float) -> str:
    """Replace the mean-motion field (cols 53-63, 1-based) in TLE line 2."""
    return line2[:52] + f"{mm_rev_day:11.8f}" + line2[63:]


def test_element_changes_detects_inclination_change():
    before = Satrec.twoline2rv(ISS_L1, ISS_L2)
    l2_after = _set_inclination(ISS_L2, 51.6516)  # +0.01 deg
    after = Satrec.twoline2rv(ISS_L1, l2_after)
    changes = compute_element_changes(before, after)
    assert abs(changes.delta_incl_deg - 0.01) < 1e-6
    assert abs(changes.delta_sma_km) < 1e-6
    assert abs(changes.delta_ecc) < 1e-9


def test_element_changes_detects_sma_change():
    before = Satrec.twoline2rv(ISS_L1, ISS_L2)
    l2_after = _set_mean_motion(ISS_L2, 15.73125391)  # +0.01 rev/day
    after = Satrec.twoline2rv(ISS_L1, l2_after)
    changes = compute_element_changes(before, after)
    # Higher mean motion -> lower orbit: delta should be negative, order of ~1 km
    assert changes.delta_sma_km < -0.5
    assert changes.delta_sma_km > -3.0
    assert abs(changes.delta_incl_deg) < 1e-6


def test_element_changes_zero_for_identical_tles():
    before = Satrec.twoline2rv(ISS_L1, ISS_L2)
    after = Satrec.twoline2rv(ISS_L1, ISS_L2)
    changes = compute_element_changes(before, after)
    assert changes.delta_sma_km == 0.0
    assert changes.delta_incl_deg == 0.0
    assert changes.delta_ecc == 0.0


def test_parse_tle_text_captures_name():
    text = f"ISS (ZARYA)\n{ISS_L1}\n{ISS_L2}\n"
    records = _parse_tle_text(text)
    assert len(records) == 1
    assert records[0].norad_id == 25544
    assert records[0].name == "ISS (ZARYA)"


def test_parse_tle_text_bare_two_line_has_no_name():
    text = f"{ISS_L1}\n{ISS_L2}\n"
    records = _parse_tle_text(text)
    assert len(records) == 1
    assert records[0].name is None


def test_site_data_exposes_maneuver_history():
    events = {
        "25544": [
            {"timestamp": "2026-10-01T00:00:00+00:00", "reason": "a", "detection": "residual"},
            {"timestamp": "2026-10-02T00:00:00+00:00", "reason": "b", "detection": "elements"},
        ]
    }
    data = build_site_data(
        generated_at="2026-10-07T00:00:00+00:00",
        watchlist=[25544],
        object_names={25544: "ISS"},
        previous_tles={"25544": {"line1": ISS_L1, "line2": ISS_L2}},
        tle_ages_days={25544: 0.5},
        maneuver_events=events,
        satnogs_healths_by_id={},
    )
    sat = data["satellites"][0]
    assert sat["maneuver_count"] == 2
    assert sat["maneuver_history"] == events["25544"]
    assert sat["latest_maneuver"] == events["25544"][-1]


def test_site_data_no_maneuvers_gives_empty_history():
    data = build_site_data(
        generated_at="2026-10-07T00:00:00+00:00",
        watchlist=[25544],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
    )
    sat = data["satellites"][0]
    assert sat["maneuver_count"] == 0
    assert sat["maneuver_history"] is None
    assert sat["latest_maneuver"] is None
