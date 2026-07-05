import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.site_data import build_site_data, conjunctions_for, imagery_descriptor  # noqa: E402


def test_gibs_satellites_get_the_confirmed_real_layer_names():
    terra = imagery_descriptor(25994)
    assert terra["kind"] == "gibs"
    labels = {opt["label"] for opt in terra["options"]}
    assert labels == {"True Color", "Active Fires & Thermal Anomalies"}
    true_color = next(o for o in terra["options"] if o["label"] == "True Color")
    assert true_color["layer"] == "MODIS_Terra_CorrectedReflectance_TrueColor"

    noaa20 = imagery_descriptor(43013)
    fire = next(o for o in noaa20["options"] if "Fire" in o["label"])
    assert fire["layer"] == "VIIRS_NOAA20_Thermal_Anomalies_375m_Day"


def test_landsat_is_honestly_labeled_annual_not_daily():
    result = imagery_descriptor(39084)  # Landsat 8
    assert result["kind"] == "gibs"
    assert result["options"][0]["cadence"] == "annual"


def test_gpm_gets_the_real_imerg_rain_rate_layer_labeled_realtime():
    result = imagery_descriptor(39574)  # GPM Core Observatory
    assert result == {
        "kind": "gibs",
        "options": [{"label": "Rain/Snowfall Rate", "layer": "IMERG_Precipitation_Rate_30min", "cadence": "realtime"}],
    }


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


def test_conjunctions_for_finds_object_regardless_of_which_side_it_was_on():
    all_conjunctions = [
        {
            "norad_id_1": 25544, "name_1": "ISS (ZARYA)",
            "norad_id_2": 99999, "name_2": "RANDOM DEBRIS",
            "time_of_closest_approach": "2026-07-10T00:00:00", "min_range_km": 1.2, "max_probability": 0.001,
        },
        {
            "norad_id_1": 88888, "name_1": "OLD ROCKET BODY",
            "norad_id_2": 25544, "name_2": "ISS (ZARYA)",
            "time_of_closest_approach": "2026-07-11T00:00:00", "min_range_km": 3.4, "max_probability": 0.0002,
        },
        {
            "norad_id_1": 1, "name_1": "UNRELATED A",
            "norad_id_2": 2, "name_2": "UNRELATED B",
            "time_of_closest_approach": "2026-07-12T00:00:00", "min_range_km": 5.0, "max_probability": 0.0001,
        },
    ]
    results = conjunctions_for(25544, all_conjunctions)
    assert len(results) == 2
    assert results[0]["other_name"] == "RANDOM DEBRIS"
    assert results[1]["other_name"] == "OLD ROCKET BODY"


def test_conjunctions_are_attached_per_satellite_in_build_site_data():
    all_conjunctions = [{
        "norad_id_1": 25544, "name_1": "ISS (ZARYA)",
        "norad_id_2": 99999, "name_2": "RANDOM DEBRIS",
        "time_of_closest_approach": "2026-07-10T00:00:00", "min_range_km": 1.2, "max_probability": 0.001,
    }]
    result = build_site_data(
        generated_at="x",
        watchlist=[25544],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
        conjunctions=all_conjunctions,
    )
    sat = result["satellites"][0]
    assert len(sat["conjunctions"]) == 1
    assert sat["conjunctions"][0]["other_name"] == "RANDOM DEBRIS"


def test_crew_aboard_is_attached_for_space_station_modules():
    result = build_site_data(
        generated_at="x",
        watchlist=[25544, 48274, 26407],  # ISS, Tiangong module, a GPS satellite
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
        crew_by_craft={"ISS": ["Jane Doe"], "Tiangong": ["Li Wei"]},
    )
    by_id = {s["norad_id"]: s for s in result["satellites"]}
    assert by_id[25544]["crew_aboard"] == ["Jane Doe"]
    assert by_id[48274]["crew_aboard"] == ["Li Wei"]
    assert by_id[26407]["crew_aboard"] is None  # GPS satellite -- not a space station


def test_deep_space_probes_are_a_separate_top_level_section_not_per_satellite():
    result = build_site_data(
        generated_at="x",
        watchlist=[25544],
        object_names={},
        previous_tles={},
        tle_ages_days={},
        maneuver_events={},
        satnogs_healths_by_id={},
        deep_space_probes=[{"key": "voyager_1", "name": "Voyager 1", "distance_from_earth_km": 2.5e10}],
    )
    assert result["deep_space_probes"] == [{"key": "voyager_1", "name": "Voyager 1", "distance_from_earth_km": 2.5e10}]
    # not attached to any individual satellite -- these aren't Earth-orbiting
    assert "deep_space_probes" not in result["satellites"][0]


def test_deep_space_probes_default_to_empty_list_not_a_crash():
    result = build_site_data(
        generated_at="x", watchlist=[], object_names={}, previous_tles={},
        tle_ages_days={}, maneuver_events={}, satnogs_healths_by_id={},
    )
    assert result["deep_space_probes"] == []


def test_achievement_is_attached_only_for_satellites_that_have_one():
    result = build_site_data(
        generated_at="x",
        watchlist=[20580, 26407],  # Hubble, a GPS satellite
        object_names={}, previous_tles={}, tle_ages_days={},
        maneuver_events={}, satnogs_healths_by_id={},
        achievements={20580: {"headline": "Took the Hubble Deep Field (1995)", "detail": "..."}},
    )
    by_id = {s["norad_id"]: s for s in result["satellites"]}
    assert by_id[20580]["achievement"]["headline"] == "Took the Hubble Deep Field (1995)"
    assert by_id[26407]["achievement"] is None  # no fabricated achievement for satellites without one


def test_volcano_alerts_attached_only_to_thermal_imaging_satellites():
    result = build_site_data(
        generated_at="x",
        watchlist=[25994, 20580],  # Terra (thermal-imaging), Hubble (not)
        object_names={}, previous_tles={}, tle_ages_days={},
        maneuver_events={}, satnogs_healths_by_id={},
        volcano_alerts=[{"volcano_name": "Great Sitkin", "alert_level": "WATCH"}],
    )
    by_id = {s["norad_id"]: s for s in result["satellites"]}
    assert by_id[25994]["volcano_alerts"] == [{"volcano_name": "Great Sitkin", "alert_level": "WATCH"}]
    assert by_id[20580]["volcano_alerts"] is None  # Hubble isn't a thermal-imaging Earth observation satellite
