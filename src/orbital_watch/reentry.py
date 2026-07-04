"""
Honest reentry uncertainty visualization.

This deliberately does NOT try to predict *when* an object will reenter --
that requires atmospheric density modeling (solar activity, drag, attitude/
tumbling) and even the best models carry ~+/-20% timing uncertainty on the
remaining orbital lifetime (see README). Reimplementing that is a much
bigger project, and a worse one to fake.

What this DOES do: given a nominal reentry time estimate and its
uncertainty window (both provided by you -- e.g. from Aerospace Corp's or
CelesTrak's public decay predictions), propagate the actual TLE across the
*entire* uncertainty window and report every ground-track point the object
passes over. That whole set of points *is* the corridor -- every one of
them is a place the object could physically be when it comes down, because
we don't know which orbit within the window is the real one. This is a
communication fix (stop showing a single pin/time as if it were precise),
not a prediction upgrade.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from skyfield.api import EarthSatellite, load, wgs84

_TS = load.timescale(builtin=True)


@dataclass
class TrackPoint:
    time_utc: datetime
    latitude_deg: float
    longitude_deg: float


def compute_ground_track_corridor(
    line1: str,
    line2: str,
    nominal_reentry_utc: datetime,
    uncertainty_hours: float,
    step_seconds: int = 60,
) -> list[TrackPoint]:
    """Every ground-track point from (nominal - uncertainty) to
    (nominal + uncertainty), at `step_seconds` resolution. Plot/list all of
    them as the "corridor" -- resist the urge to pick just one."""
    if nominal_reentry_utc.tzinfo is None:
        nominal_reentry_utc = nominal_reentry_utc.replace(tzinfo=timezone.utc)

    sat = EarthSatellite(line1, line2, "OBJECT", _TS)

    window_start = nominal_reentry_utc - timedelta(hours=uncertainty_hours)
    window_end = nominal_reentry_utc + timedelta(hours=uncertainty_hours)

    points: list[TrackPoint] = []
    current = window_start
    while current <= window_end:
        t = _TS.utc(
            current.year, current.month, current.day,
            current.hour, current.minute, current.second + current.microsecond / 1e6,
        )
        subpoint = wgs84.subpoint(sat.at(t))
        points.append(
            TrackPoint(
                time_utc=current,
                latitude_deg=subpoint.latitude.degrees,
                longitude_deg=subpoint.longitude.degrees,
            )
        )
        current += timedelta(seconds=step_seconds)

    return points


def summarize_corridor(points: list[TrackPoint]) -> str:
    """Plain-language summary instead of a false-precision single point."""
    if not points:
        return "No corridor computed."

    lats = [p.latitude_deg for p in points]
    lons = [p.longitude_deg for p in points]

    return (
        f"Reentry corridor spans {points[0].time_utc.isoformat()} to "
        f"{points[-1].time_utc.isoformat()} ({len(points)} track points).\n"
        f"The object could come down ANYWHERE within this corridor -- not at "
        f"a single point -- because the timing uncertainty is larger than "
        f"one orbital period.\n"
        f"Latitude range covered: {min(lats):.1f} deg to {max(lats):.1f} deg "
        f"(bounded by the object's inclination -- it physically cannot reenter "
        f"outside this band).\n"
        f"Longitude range covered: {min(lons):.1f} deg to {max(lons):.1f} deg "
        f"(effectively spans most/all longitudes if the window covers "
        f"multiple orbits, since Earth rotates underneath the orbit each pass)."
    )


def to_geojson(points: list[TrackPoint]) -> dict:
    """A LineString FeatureCollection -- drop straight into any map viewer
    that reads GeoJSON (geojson.io, Leaflet, kepler.gl, etc.) instead of
    building a bespoke map renderer."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[p.longitude_deg, p.latitude_deg] for p in points],
                },
                "properties": {
                    "start_utc": points[0].time_utc.isoformat() if points else None,
                    "end_utc": points[-1].time_utc.isoformat() if points else None,
                    "point_count": len(points),
                },
            }
        ],
    }
