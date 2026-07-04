import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.biography import build_biography  # noqa: E402
from orbital_watch.satcat import SatcatRecord  # noqa: E402


def _record(**overrides):
    defaults = dict(
        norad_id=25544,
        object_name="ISS (ZARYA)",
        object_type="PAYLOAD",
        owner="ISS",
        launch_date="1998-11-20",
        launch_site="TYMSC",
        decay_date=None,
        period_minutes=92.68,
        inclination_deg=51.64,
        apogee_km=420.0,
        perigee_km=417.0,
    )
    defaults.update(overrides)
    return SatcatRecord(**defaults)


def test_biography_includes_identity_and_launch_info():
    bio = build_biography(_record(), [])
    assert "ISS (ZARYA)" in bio
    assert "NORAD 25544" in bio
    assert "1998-11-20" in bio
    assert "ISS" in bio


def test_decayed_object_says_so_instead_of_still_in_orbit():
    bio = build_biography(_record(decay_date="2031-01-15"), [])
    assert "Reentered/decayed on 2031-01-15" in bio
    assert "Still in orbit" not in bio


def test_active_object_says_still_in_orbit():
    bio = build_biography(_record(), [])
    assert "Still in orbit" in bio


def test_no_events_reports_none_detected_rather_than_empty_section():
    bio = build_biography(_record(), [])
    assert "No maneuvers detected yet" in bio


def test_events_are_listed_in_the_timeline():
    events = [
        {
            "timestamp": "2026-07-01T00:00:00Z",
            "residual_km": 12.5,
            "z_score": 4.2,
            "reason": "residual is 4.2 sigma above baseline",
        }
    ]
    bio = build_biography(_record(), events)
    assert "2026-07-01T00:00:00Z" in bio
    assert "12.50 km" in bio
    assert "4.2 sigma" in bio


def test_debris_object_gets_plain_english_type_not_raw_code():
    bio = build_biography(_record(object_type="DEBRIS", owner="", launch_date=None, launch_site=None), [])
    assert "a piece of orbital debris" in bio
