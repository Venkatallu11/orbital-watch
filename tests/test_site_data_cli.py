import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import site_data_cli  # noqa: E402

LINE1 = "1 25544U 98067A   26185.47597407  .00009720  00000-0  18499-3 0  9997"
LINE2 = "2 25544  51.6423 339.8145 0005423  86.9741 273.1685 15.49867112456789"
NORAD_ID = 25544


def test_generates_data_json_from_a_real_state_file(tmp_path, capsys):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))

    names_path = tmp_path / "names.json"
    names_path.write_text(json.dumps({str(NORAD_ID): "ISS (ZARYA)"}))

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "previous_tles": {str(NORAD_ID): {"line1": LINE1, "line2": LINE2}},
        "maneuver_events": {str(NORAD_ID): [{"timestamp": "t1", "reason": "big jump"}]},
        "satnogs_health": {str(NORAD_ID): {"reason": "8/9 good", "is_degraded": False}},
    }))

    out_path = tmp_path / "data.json"

    exit_code = site_data_cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--object-names", str(names_path),
        "--out", str(out_path),
    ])

    assert exit_code == 0
    data = json.loads(out_path.read_text())
    sat = data["satellites"][0]
    assert sat["norad_id"] == NORAD_ID
    assert sat["name"] == "ISS (ZARYA)"
    assert sat["line1"] == LINE1
    assert sat["tle_age_days"] is not None and sat["tle_age_days"] > 0
    assert sat["latest_maneuver"]["reason"] == "big jump"
    assert sat["satnogs_health"]["reason"] == "8/9 good"
    assert sat["imagery"] == {"kind": "none"}  # ISS has no imagery source
    assert sat["category"] == "uncategorized"  # no --categories-file given


def test_categories_file_attaches_category_per_satellite(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "previous_tles": {str(NORAD_ID): {"line1": LINE1, "line2": LINE2}},
    }))
    categories_path = tmp_path / "categories.json"
    categories_path.write_text(json.dumps({str(NORAD_ID): "space_stations"}))
    out_path = tmp_path / "data.json"

    site_data_cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--categories-file", str(categories_path),
        "--out", str(out_path),
    ])

    data = json.loads(out_path.read_text())
    assert data["satellites"][0]["category"] == "space_stations"
    assert data["category_labels"]["space_stations"] == "Space Stations & Human Spaceflight"


def test_instruments_file_attaches_instrument_info_per_satellite(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "previous_tles": {str(NORAD_ID): {"line1": LINE1, "line2": LINE2}},
    }))
    instruments_path = tmp_path / "instruments.json"
    instruments_path.write_text(json.dumps({
        str(NORAD_ID): {"instruments": [], "data_products": ["crew research"], "description": "It's the ISS."}
    }))
    out_path = tmp_path / "data.json"

    site_data_cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--instruments-file", str(instruments_path),
        "--out", str(out_path),
    ])

    data = json.loads(out_path.read_text())
    assert data["satellites"][0]["instruments"]["description"] == "It's the ISS."


def test_achievements_file_attaches_achievement_per_satellite(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "previous_tles": {str(NORAD_ID): {"line1": LINE1, "line2": LINE2}},
    }))
    achievements_path = tmp_path / "achievements.json"
    achievements_path.write_text(json.dumps({
        str(NORAD_ID): {"headline": "Test milestone", "detail": "..."},
    }))
    out_path = tmp_path / "data.json"

    site_data_cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--achievements-file", str(achievements_path),
        "--out", str(out_path),
    ])

    data = json.loads(out_path.read_text())
    assert data["satellites"][0]["achievement"]["headline"] == "Test milestone"


def test_conjunctions_and_crew_are_read_from_state_json(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "previous_tles": {str(NORAD_ID): {"line1": LINE1, "line2": LINE2}},
        "conjunctions": [{
            "norad_id_1": NORAD_ID, "name_1": "ISS (ZARYA)",
            "norad_id_2": 99999, "name_2": "RANDOM DEBRIS",
            "time_of_closest_approach": "2026-07-10T00:00:00",
            "min_range_km": 1.2, "max_probability": 0.001,
        }],
        "crew_by_craft": {"ISS": ["Jane Doe"]},
        "deep_space_probes": [{
            "key": "voyager_1", "name": "Voyager 1", "pseudo_norad_id": -31,
            "launched": "1977-09-05", "milestone_headline": "h", "milestone_detail": "d",
            "instruments": [], "data_products": [], "description": "desc",
            "epoch": "2026-Jul-05 00:00:00.0000", "distance_from_earth_km": 2.5e10,
            "distance_from_earth_au": 167.0, "speed_km_s": 37.5,
        }],
    }))
    out_path = tmp_path / "data.json"

    site_data_cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--out", str(out_path),
    ])

    data = json.loads(out_path.read_text())
    by_id = {s["norad_id"]: s for s in data["satellites"]}
    sat = by_id[NORAD_ID]
    assert sat["conjunctions"][0]["other_name"] == "RANDOM DEBRIS"
    assert sat["crew_aboard"] == ["Jane Doe"]
    # Voyager 1 shows up as a real selectable satellite entry, not a
    # separate top-level section
    assert by_id[-31]["name"] == "Voyager 1"
    assert by_id[-31]["category"] == "deep_space_probes"


def test_satellite_never_fetched_yet_still_appears_with_nulls(tmp_path):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([99999]))
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({}))
    out_path = tmp_path / "data.json"

    site_data_cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--out", str(out_path),
    ])

    data = json.loads(out_path.read_text())
    sat = data["satellites"][0]
    assert sat["line1"] == ""
    assert sat["tle_age_days"] is None
