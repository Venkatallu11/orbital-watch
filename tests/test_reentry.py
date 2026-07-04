"""
Tests run fully offline: skyfield's builtin timescale (no leap-second/
ephemeris download) plus a real TLE. This validates the corridor math
itself, not a live decay prediction (we don't do decay prediction -- see
reentry.py docstring for why).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.reentry import (  # noqa: E402
    compute_ground_track_corridor,
    summarize_corridor,
    to_geojson,
)

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
NOMINAL = datetime(2000, 6, 28, 12, 0, 0, tzinfo=timezone.utc)  # near the TLE's own epoch


def test_corridor_spans_the_full_uncertainty_window():
    points = compute_ground_track_corridor(LINE1, LINE2, NOMINAL, uncertainty_hours=1, step_seconds=300)

    assert points[0].time_utc == NOMINAL - timedelta(hours=1)
    assert points[-1].time_utc <= NOMINAL + timedelta(hours=1) + timedelta(seconds=300)
    # every point in between, not just the nominal instant
    assert len(points) > 10


def test_latitude_never_exceeds_orbital_inclination():
    # Vanguard 1's inclination is 34.27 deg -- it physically cannot be seen
    # above that latitude, so the corridor must respect that bound.
    points = compute_ground_track_corridor(LINE1, LINE2, NOMINAL, uncertainty_hours=3, step_seconds=120)
    inclination_deg = 34.2682
    for p in points:
        assert abs(p.latitude_deg) <= inclination_deg + 0.5  # small margin for numerics


def test_wider_uncertainty_window_covers_more_of_the_planet():
    narrow = compute_ground_track_corridor(LINE1, LINE2, NOMINAL, uncertainty_hours=0.25, step_seconds=60)
    wide = compute_ground_track_corridor(LINE1, LINE2, NOMINAL, uncertainty_hours=6, step_seconds=60)

    narrow_lon_spread = max(p.longitude_deg for p in narrow) - min(p.longitude_deg for p in narrow)
    wide_lon_spread = max(p.longitude_deg for p in wide) - min(p.longitude_deg for p in wide)
    assert wide_lon_spread > narrow_lon_spread


def test_summary_is_honest_about_not_being_a_single_point():
    points = compute_ground_track_corridor(LINE1, LINE2, NOMINAL, uncertainty_hours=2, step_seconds=300)
    summary = summarize_corridor(points)
    assert "ANYWHERE" in summary
    assert "not at" in summary


def test_geojson_is_a_valid_linestring_feature_collection():
    points = compute_ground_track_corridor(LINE1, LINE2, NOMINAL, uncertainty_hours=1, step_seconds=300)
    geojson = to_geojson(points)

    assert geojson["type"] == "FeatureCollection"
    feature = geojson["features"][0]
    assert feature["geometry"]["type"] == "LineString"
    assert len(feature["geometry"]["coordinates"]) == len(points)
    # GeoJSON coordinate order is [lon, lat], not [lat, lon] -- easy to get backwards
    assert feature["geometry"]["coordinates"][0] == [points[0].longitude_deg, points[0].latitude_deg]
