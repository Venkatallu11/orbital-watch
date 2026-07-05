import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.digest import ManeuverAlert, generate_digest  # noqa: E402
from orbital_watch.satnogs import ObservationHealth  # noqa: E402
from orbital_watch.socrates import Conjunction  # noqa: E402

NAMES = {25544: "ISS (ZARYA)", 48274: "COSMOS 2251 DEB"}


def test_empty_digest_is_reassuring_not_blank():
    digest = generate_digest(NAMES, [], [], [])
    assert "Nothing flagged this run." in digest
    assert "No conjunctions involving your watchlist" in digest


def test_maneuver_alert_uses_friendly_name_not_bare_norad_id():
    alerts = [ManeuverAlert(norad_id=25544, residual_km=12.5, z_score=4.1, reason="big jump")]
    digest = generate_digest(NAMES, alerts, [], [])
    assert "ISS (ZARYA)" in digest
    assert "big jump" in digest
    assert "4.1 sigma" in digest


def test_unnamed_object_falls_back_to_norad_id():
    alerts = [ManeuverAlert(norad_id=99999, residual_km=1.0, z_score=3.5, reason="x")]
    digest = generate_digest({}, alerts, [], [])
    assert "NORAD 99999" in digest


def _conjunction(**overrides):
    defaults = dict(
        norad_id_1=25544, name_1="ISS",
        norad_id_2=22222, name_2="DEB A",
        time_of_closest_approach=datetime(2026, 1, 1),
        min_range_km=1.0, relative_speed_km_s=7.0,
        max_probability=0.0001, dilution=0.1,
        days_since_epoch_1=1.0, days_since_epoch_2=1.0,
    )
    defaults.update(overrides)
    return Conjunction(**defaults)


def test_conjunctions_sorted_by_probability_descending():
    # Neither 22222 nor 11111 is in NAMES, so each falls back to the name
    # SOCRATES itself supplied for that object.
    conjunctions = [
        _conjunction(norad_id_2=22222, name_2="DEB A", max_probability=0.0001),
        _conjunction(norad_id_2=11111, name_2="DEB B", max_probability=0.05),
    ]
    digest = generate_digest(NAMES, [], conjunctions, [])
    deb_b_pos = digest.index("DEB B")
    deb_a_pos = digest.index("DEB A")
    assert deb_b_pos < deb_a_pos  # higher probability (0.05) listed first


def test_degraded_satnogs_health_is_flagged_visibly():
    healths = [
        ObservationHealth(25544, 10, 2, 8, 0, 0.2, True, "only 2/10 good"),
    ]
    digest = generate_digest(NAMES, [], [], healths)
    assert "DEGRADED" in digest
    assert "only 2/10 good" in digest


def test_maneuver_alert_shows_per_day_rate_when_provided():
    alerts = [ManeuverAlert(
        norad_id=25544, residual_km=12.5, z_score=4.1, reason="big jump",
        epoch_gap_days=0.5, residual_km_per_day=25.0,
    )]
    digest = generate_digest(NAMES, alerts, [], [])
    assert "25.00 km/day" in digest
    assert "0.50 day(s) between TLEs" in digest


def test_maneuver_alert_without_per_day_data_omits_that_bit_cleanly():
    """Older/synthetic ManeuverAlerts without the new fields shouldn't
    produce a broken or misleading line."""
    alerts = [ManeuverAlert(norad_id=25544, residual_km=12.5, z_score=4.1, reason="big jump")]
    digest = generate_digest(NAMES, alerts, [], [])
    assert "km/day" not in digest


def test_freshness_section_lists_every_watched_object():
    digest = generate_digest(NAMES, [], [], [], tle_ages_days={25544: 0.3, 48274: 9.2})
    assert "Data freshness" in digest
    assert "ISS (ZARYA)" in digest
    assert "0.3 day(s) old" in digest
    assert "9.2 day(s) old" in digest


def test_stale_tle_is_flagged_visibly():
    digest = generate_digest(NAMES, [], [], [], tle_ages_days={25544: 9.2})
    assert "STALE" in digest


def test_fresh_tle_is_not_flagged():
    digest = generate_digest(NAMES, [], [], [], tle_ages_days={25544: 0.3})
    assert "STALE" not in digest


def test_no_freshness_data_omits_the_section():
    digest = generate_digest(NAMES, [], [], [])
    assert "Data freshness" not in digest
