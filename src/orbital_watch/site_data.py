"""
Builds the small JSON snapshot the static website (docs/) reads. Generated
fresh after every scheduled run and committed alongside state.json/digest.md
-- the site itself does no server-side work, it just reads this file.

IMAGERY MAPPING: honestly scoped, not "every satellite gets a pretty
picture." Every layer identifier below was confirmed live to return a real
image (not an error page) via verify_imagery.py/the verify-gibs-layers
workflow before being hardcoded here -- not guessed.
  - Terra, Aqua, Suomi NPP, NOAA-20: real daily true-color AND real active
    fire/thermal-anomaly layers, both from that satellite's own instrument
    (MODIS/VIIRS). Each satellite offers both as separate "options" the
    site can switch between, not just one picked for you.
  - Landsat 8: GIBS only has an ANNUAL composite for Landsat (WELD product),
    not a daily layer like the others -- labeled as such, not claimed to be
    "live" when it isn't.
  - GPM Core Observatory: GIBS' real IMERG_Precipitation_Rate_30min layer --
    an actual global rain/snowfall-rate product from GPM's GMI microwave
    imager + DPR radar, refreshed every 30 min. Labeled "realtime" (not
    "daily") and requested for today's date rather than yesterday's, since
    the underlying product is near-real-time.
  - Hubble: no simple keyless image-archive API (HubbleSite's own v3 API
    gates behind a free-account key per their docs). Using NASA's APOD
    (Astronomy Picture of the Day) instead, honestly labeled as "today's
    NASA astronomy picture" -- often Hubble, not guaranteed to be.
  - ISS, NOAA-19, Starlink, navigation, comms, etc: no straightforward
    public per-satellite imagery API for these. Marked "none" rather than
    faking a picture.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# GIBS WMTS layer identifiers -- each satellite maps to a LIST of real,
# live-verified imagery options (not just one), so the site can offer a
# choice (e.g. true-color vs. active-fire detection) where more than one
# genuinely exists for that satellite's own instrument.
_GIBS_LAYERS: dict[int, list[dict]] = {
    25994: [  # Terra
        {"label": "True Color", "layer": "MODIS_Terra_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "MODIS_Terra_Thermal_Anomalies_All", "cadence": "daily"},
    ],
    27424: [  # Aqua
        {"label": "True Color", "layer": "MODIS_Aqua_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "MODIS_Aqua_Thermal_Anomalies_All", "cadence": "daily"},
    ],
    37849: [  # Suomi NPP
        {"label": "True Color", "layer": "VIIRS_SNPP_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "VIIRS_SNPP_Thermal_Anomalies_375m_Day", "cadence": "daily"},
    ],
    43013: [  # NOAA-20
        {"label": "True Color", "layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "VIIRS_NOAA20_Thermal_Anomalies_375m_Day", "cadence": "daily"},
    ],
    39084: [  # Landsat 8
        {"label": "True Color (Annual Composite)", "layer": "Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual", "cadence": "annual"},
    ],
    39574: [  # GPM Core Observatory
        {"label": "Rain/Snowfall Rate", "layer": "IMERG_Precipitation_Rate_30min", "cadence": "realtime"},
    ],
}
_APOD_NORAD_IDS = {20580}  # Hubble Space Telescope

# Which real crewed-spacecraft "craft" name (as Open Notify's API reports
# it, see crew.py) each space-station module belongs to -- lets the
# website attach real "who's aboard" data to the right modules instead of
# guessing from the satellite name string.
_SPACE_STATION_CRAFT: dict[int, str] = {
    25544: "ISS",       # ISS (ZARYA)
    36086: "ISS",       # Poisk
    49044: "ISS",       # Nauka
    48274: "Tiangong",  # CSS (Tianhe)
    53239: "Tiangong",  # CSS (Wentian)
    54216: "Tiangong",  # CSS (Mengtian)
}

# Human-readable labels for categories.json's category keys -- kept here
# (not hardcoded in the frontend) so adding a new category is a one-place
# change. "uncategorized" is the fallback for any watchlist entry missing
# from categories.json, not a real category a satellite is picked for.
CATEGORY_LABELS: dict[str, str] = {
    "earth_observation": "Earth Observation & Weather",
    "precipitation_watch": "Precipitation & Rain/Snow Watch",
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
        return {"kind": "gibs", "options": _GIBS_LAYERS[norad_id]}
    if norad_id in _APOD_NORAD_IDS:
        return {"kind": "apod"}
    return {"kind": "none"}


def conjunctions_for(norad_id: int, all_conjunctions: list[dict]) -> list[dict]:
    """A SOCRATES conjunction always involves two objects -- this pulls out
    just the ones involving `norad_id`, described from that object's point
    of view (the *other* object's id/name), so the website can show "you
    have a close approach with X" on either object's own page."""
    results = []
    for c in all_conjunctions:
        if c["norad_id_1"] == norad_id:
            other_id, other_name = c["norad_id_2"], c["name_2"]
        elif c["norad_id_2"] == norad_id:
            other_id, other_name = c["norad_id_1"], c["name_1"]
        else:
            continue
        results.append({
            "other_norad_id": other_id,
            "other_name": other_name,
            "time_of_closest_approach": c["time_of_closest_approach"],
            "min_range_km": c["min_range_km"],
            "max_probability": c["max_probability"],
        })
    return results


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
    instruments: dict | None
    conjunctions: list[dict]
    crew_aboard: list[str] | None


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
    instruments: dict[int, dict] | None = None,
    conjunctions: list[dict] | None = None,
    crew_by_craft: dict[str, list[str]] | None = None,
) -> dict:
    """Pure function, no I/O -- takes already-loaded data (from state.json,
    watchlist.json, etc.) and shapes it into the JSON the website expects.
    Kept separate from any file reading so it's trivially testable."""
    object_types = object_types or {}
    categories = categories or {}
    instruments = instruments or {}
    conjunctions = conjunctions or []
    crew_by_craft = crew_by_craft or {}
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
                instruments=instruments.get(norad_id),
                conjunctions=conjunctions_for(norad_id, conjunctions),
                crew_aboard=crew_by_craft.get(_SPACE_STATION_CRAFT.get(norad_id, "")),
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
                "instruments": s.instruments,
                "conjunctions": s.conjunctions,
                "crew_aboard": s.crew_aboard,
            }
            for s in satellites
        ],
    }
