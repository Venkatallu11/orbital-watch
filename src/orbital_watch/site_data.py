"""
Builds the small JSON snapshot the static website (docs/) reads. Generated
fresh after every scheduled run and committed alongside state.json/digest.md
-- the site itself does no server-side work, it just reads this file.

IMAGERY MAPPING: honestly scoped, not "every satellite gets a pretty
picture." Confirmed via research, not assumed:
  - Terra, Aqua, Suomi NPP, NOAA-20: NASA GIBS provides real daily true-color
    tile layers (MODIS/VIIRS instruments) -- these are actual current Earth
    imagery from that specific satellite's instrument, freely tiled, no key.
  - Landsat 8: GIBS only has an ANNUAL composite for Landsat (WELD product),
    not a daily layer like the others -- labeled as such, not claimed to be
    "live" when it isn't.
  - Hubble: no simple keyless image-archive API (HubbleSite's own v3 API
    gates behind a free-account key per their docs). Using NASA's APOD
    (Astronomy Picture of the Day) instead, honestly labeled as "today's
    NASA astronomy picture" -- often Hubble, not guaranteed to be.
  - ISS, NOAA-19, Starlink: no straightforward public per-satellite imagery
    API for these. Marked "none" rather than faking a picture.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# GIBS WMTS layer identifiers, confirmed against NASA's own Worldview
# configuration and GIBS documentation.
_GIBS_LAYERS: dict[int, dict] = {
    25994: {"layer": "MODIS_Terra_CorrectedReflectance_TrueColor", "cadence": "daily"},   # Terra
    27424: {"layer": "MODIS_Aqua_CorrectedReflectance_TrueColor", "cadence": "daily"},     # Aqua
    37849: {"layer": "VIIRS_SNPP_CorrectedReflectance_TrueColor", "cadence": "daily"},     # Suomi NPP
    43013: {"layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "cadence": "daily"},   # NOAA-20
    39084: {"layer": "Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual", "cadence": "annual"},  # Landsat 8
}
_APOD_NORAD_IDS = {20580}  # Hubble Space Telescope

# Human-readable labels for categories.json's category keys -- kept here
# (not hardcoded in the frontend) so adding a new category is a one-place
# change. "uncategorized" is the fallback for any watchlist entry missing
# from categories.json, not a real category a satellite is picked for.
CATEGORY_LABELS: dict[str, str] = {
    "earth_observation": "Earth Observation & Weather",
    "space_telescopes": "Space Telescopes (Deep-Space & Solar Observers)",
    "asteroid_watch": "Asteroid & Near-Earth Object Watchers",
    "space_stations": "Space Stations & Human Spaceflight",
    "navigation": "Navigation (GNSS)",
    "communications": "Communications Megaconstellations",
    "amateur": "Amateur Radio & CubeSats",
    "uncategorized": "Other",
}


def imagery_descriptor(norad_id: int) -> dict:
    if norad_id in _GIBS_LAYERS:
        info = _GIBS_LAYERS[norad_id]
        return {"kind": "gibs", "layer": info["layer"], "cadence": info["cadence"]}
    if norad_id in _APOD_NORAD_IDS:
        return {"kind": "apod"}
    return {"kind": "none"}


@dataclass
class SiteSatellite:
    norad_id: int
    name: str
    line1: str
    line2: str
    tle_age_days: float | None
    object_type: str | None
    imagery: dict
    latest_maneuver: dict | None
    satnogs_health: dict | None
    category: str


@dataclass
class SiteData:
    generated_at: str
    satellites: list[SiteSatellite] = field(default_factory=list)


def build_site_data(
    generated_at: str,
    watchlist: list[int],
    object_names: dict[int, str],
    previous_tles: dict[str, dict],
    tle_ages_days: dict[int, float],
    maneuver_events: dict[str, list],
    satnogs_healths_by_id: dict[int, dict],
    object_types: dict[int, str] | None = None,
    categories: dict[int, str] | None = None,
) -> dict:
    """Pure function, no I/O -- takes already-loaded data (from state.json,
    watchlist.json, etc.) and shapes it into the JSON the website expects.
    Kept separate from any file reading so it's trivially testable."""
    object_types = object_types or {}
    categories = categories or {}
    satellites = []

    for norad_id in sorted(watchlist):
        norad_key = str(norad_id)
        tle = previous_tles.get(norad_key)

        events = maneuver_events.get(norad_key, [])
        latest_maneuver = events[-1] if events else None

        satellites.append(
            SiteSatellite(
                norad_id=norad_id,
                name=object_names.get(norad_id, f"NORAD {norad_id}"),
                line1=tle["line1"] if tle else "",
                line2=tle["line2"] if tle else "",
                tle_age_days=tle_ages_days.get(norad_id),
                object_type=object_types.get(norad_id),
                imagery=imagery_descriptor(norad_id),
                latest_maneuver=latest_maneuver,
                satnogs_health=satnogs_healths_by_id.get(norad_id),
                category=categories.get(norad_id, "uncategorized"),
            )
        )

    return {
        "generated_at": generated_at,
        "category_labels": CATEGORY_LABELS,
        "satellites": [
            {
                "norad_id": s.norad_id,
                "name": s.name,
                "line1": s.line1,
                "line2": s.line2,
                "tle_age_days": s.tle_age_days,
                "object_type": s.object_type,
                "imagery": s.imagery,
                "latest_maneuver": s.latest_maneuver,
                "satnogs_health": s.satnogs_health,
                "category": s.category,
            }
            for s in satellites
        ],
    }
