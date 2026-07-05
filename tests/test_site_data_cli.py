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
