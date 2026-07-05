import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.site_data import build_site_data, imagery_descriptor  # noqa: E402


def test_gibs_satellites_get_the_confirmed_real_layer_names():
    assert imagery_descriptor(25994) == {  # Terra
        "kind": "gibs", "layer": "MODIS_Terra_CorrectedReflectance_TrueColor", "cadence": "daily",
    }
    assert imagery_descriptor(43013) == {  # NOAA-20
        "kind": "gibs", "layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "cadence": "daily",
    }


def test_landsat_is_honestly_labeled_annual_not_daily():
    result = imagery_descriptor(39084)  # Landsat 8
    assert result["kind"] == "gibs"
    assert result["cadence"] == "annual"


def test_gpm_gets_the_real_imerg_rain_rate_layer_labeled_realtime():
    result = imagery_descriptor(39574)  # GPM Core Observatory
    assert result == {"kind": "gibs", "layer": "IMERG_Precipitation_Rate_30min", "cadence": "realtime"}


def test_hubble_gets_apod_not_a_fake_guarantee():
    assert imagery_descriptor(20580) == {"kind": "apod"}


def test_objects_with_no_imagery_source_are_marked_none_not_faked():
    for norad_id in (25544, 33591, 46052, 46356):  # ISS, NOAA-19, 2x Starlink
        assert imagery_descriptor(norad_id) == {"kind": "none"}


def test_build_site_data_shapes_a_full_satellite_record():
    result = build_site_data(
        generated_at="2026-07-05T00:00:00Z",
        watchlist=[25544],
        object_names={25544: "ISS (ZARYA)"},
        previous_tles={"25544": {"line1": "L1", "line2": "L2"}},
        tle_ages_days={25544: 0.4},
        maneuver_events={"25544": [{"timestamp": "t1", "reason": "big jump"}]},
        satnogs_healths_by_id={25544: {"reason": "8/9 good", "is_degraded": False}},
        object_types={25544: "PAYLOAD"},
    )

    assert result["generated_at"] == "2026-07-05T00:00:00Z"
    sat = result["satellites"][0]
    assert sat["norad_id"] == 25544
    assert sat["name"] == "ISS (ZARYA)"
    assert sat["line1"] == "L1"
    assert sat["tle_age_days"] == 0.4
    assert sat["imagery"] == {"kind": "none"}
    assert sat["latest_maneuver"]["reason"] == "big jump"
    assert sat["satnogs_health"]["reason"] == "8/9 good"


def test_missing_data_degrades_gracefully_not_a_crash():
    """A satellite with no TLE fetched yet, no name given, no maneuver
    history, no SatNOGS data -- should produce sane defaults, not KeyError."""
    result = build_site_data(
        generated_at="2026-07-05T00:00:00Z",
        watchlist=[99999],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
    )

    sat = result["satellites"][0]
    assert sat["name"] == "NORAD 99999"
    assert sat["line1"] == ""
    assert sat["tle_age_days"] is None
    assert sat["latest_maneuver"] is None
    assert sat["satnogs_health"] is None


def test_satellites_are_sorted_by_norad_id():
    result = build_site_data(
        generated_at="x",
        watchlist=[46052, 20580, 25544],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
    )
    ids = [s["norad_id"] for s in result["satellites"]]
    assert ids == [20580, 25544, 46052]


def test_category_is_attached_when_provided():
    result = build_site_data(
        generated_at="x",
        watchlist=[25544],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
        categories={25544: "space_stations"},
    )
    assert result["satellites"][0]["category"] == "space_stations"


def test_category_defaults_to_uncategorized_not_a_crash():
    result = build_site_data(
        generated_at="x",
        watchlist=[99999],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
    )
    assert result["satellites"][0]["category"] == "uncategorized"


def test_instruments_are_attached_when_provided():
    result = build_site_data(
        generated_at="x",
        watchlist=[26407],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
        instruments={26407: {"instruments": [], "data_products": ["GPS timing & ranging signals"], "description": "broadcasts GPS signals"}},
    )
    sat = result["satellites"][0]
    assert sat["instruments"]["description"] == "broadcasts GPS signals"
    assert sat["instruments"]["instruments"] == []


def test_instruments_default_to_none_not_a_crash():
    result = build_site_data(
        generated_at="x",
        watchlist=[99999],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
    )
    assert result["satellites"][0]["instruments"] is None


def test_category_labels_are_included_at_top_level():
    result = build_site_data(
        generated_at="x",
        watchlist=[],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
    )
    assert result["category_labels"]["space_stations"] == "Space Stations & Human Spaceflight"
