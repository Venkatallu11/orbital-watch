"""
Builds the small JSON snapshot the static website (docs/) reads. Generated
fresh after every scheduled run and committed alongside state.json/digest.md
-- the site itself does no server-side work, it just reads this file.

IMAGERY MAPPING: honestly scoped, not "every satellite gets a pretty
picture." Every layer identifier below was confirmed live to return a real
image (not an error page) via verify_imagery.py/the verify-gibs-layers
workflow before being hardcoded here -- not guessed.
  - Terra & Aqua (MODIS): a whole set of real daily science layers, each
    live-verified and each genuinely a MODIS product matching what the
    instruments panel says the satellite measures -- true color, active
    fire/thermal anomalies, aerosol optical depth, land-surface temperature,
    cloud-top temperature, water vapor, and snow/ice cover -- switchable.
  - Suomi NPP, NOAA-20 (VIIRS): real daily true-color AND active fire/
    thermal-anomaly layers from their own instrument.
  - GOES-16 (ABI): real GeoColor (GOES-East). GOES-18/West is intentionally
    omitted -- at the global bounding box the site requests, the GOES-West
    disc rendered near-blank, so it's left out rather than shown empty.
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
    25994: [  # Terra -- MODIS. Every layer below was live-verified (see the
             # verify-gibs-layers workflow runs) to return a real image and
             # to be genuinely a MODIS/Terra product, matching what its
             # instruments panel says it measures.
        {"label": "True Color", "layer": "MODIS_Terra_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "MODIS_Terra_Thermal_Anomalies_All", "cadence": "daily"},
        {"label": "Aerosol Optical Depth", "layer": "MODIS_Terra_Aerosol", "cadence": "daily"},
        {"label": "Land Surface Temp (Day)", "layer": "MODIS_Terra_Land_Surface_Temp_Day", "cadence": "daily"},
        {"label": "Cloud Top Temp (Day)", "layer": "MODIS_Terra_Cloud_Top_Temp_Day", "cadence": "daily"},
        {"label": "Water Vapor", "layer": "MODIS_Terra_Water_Vapor_5km_Day", "cadence": "daily"},
        {"label": "Snow & Ice Cover", "layer": "MODIS_Terra_NDSI_Snow_Cover", "cadence": "daily"},
    ],
    27424: [  # Aqua -- MODIS (same instrument family as Terra)
        {"label": "True Color", "layer": "MODIS_Aqua_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "MODIS_Aqua_Thermal_Anomalies_All", "cadence": "daily"},
        {"label": "Aerosol Optical Depth", "layer": "MODIS_Aqua_Aerosol", "cadence": "daily"},
        {"label": "Land Surface Temp (Day)", "layer": "MODIS_Aqua_Land_Surface_Temp_Day", "cadence": "daily"},
        {"label": "Cloud Top Temp (Day)", "layer": "MODIS_Aqua_Cloud_Top_Temp_Day", "cadence": "daily"},
        {"label": "Water Vapor", "layer": "MODIS_Aqua_Water_Vapor_5km_Day", "cadence": "daily"},
        {"label": "Snow & Ice Cover", "layer": "MODIS_Aqua_NDSI_Snow_Cover", "cadence": "daily"},
    ],
    37849: [  # Suomi NPP -- VIIRS
        {"label": "True Color", "layer": "VIIRS_SNPP_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "VIIRS_SNPP_Thermal_Anomalies_375m_Day", "cadence": "daily"},
    ],
    43013: [  # NOAA-20 -- VIIRS
        {"label": "True Color", "layer": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "cadence": "daily"},
        {"label": "Active Fires & Thermal Anomalies", "layer": "VIIRS_NOAA20_Thermal_Anomalies_375m_Day", "cadence": "daily"},
    ],
    39084: [  # Landsat 8
        {"label": "True Color (Annual Composite)", "layer": "Landsat_WELD_CorrectedReflectance_TrueColor_Global_Annual", "cadence": "annual"},
    ],
    41866: [  # GOES-16 -- ABI GeoColor (GOES-East; covers the Americas/Atlantic)
        {"label": "GeoColor (GOES-East)", "layer": "GOES-East_ABI_GeoColor", "cadence": "daily"},
    ],
    39574: [  # GPM Core Observatory
        {"label": "Rain/Snowfall Rate", "layer": "IMERG_Precipitation_Rate_30min", "cadence": "realtime"},
    ],
}
_APOD_NORAD_IDS = {20580}  # Hubble Space Telescope

# Satellites that genuinely take Earth imagery, but whose imagery is sold
# commercially -- so there is no free public API for their data, and the
# imagery panel says exactly that instead of just "none". This is an honest
# explanation, not a data gap we're hiding.
_COMMERCIAL_NO_FREE_IMAGERY: dict[int, str] = {
    32382: (
        "RADARSAT-2 is a commercial radar satellite (MDA / Canada). Its all-weather "
        "SAR imagery, ship-detection, and sea-ice products are sold commercially, so "
        "there is no free public API for its own data to show here."
    ),
    38012: (
        "Pleiades 1A is a commercial very-high-resolution optical satellite (Airbus). "
        "Its sub-meter imagery is sold commercially, so there is no free public feed "
        "of its own data to show here."
    ),
}

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

# Active-fire / thermal-hotspot detection is a REAL product of these four
# satellites' own instruments (MODIS on Terra/Aqua, VIIRS on Suomi
# NPP/NOAA-20) -- and only these four. Each maps to the FIRMS "source" that
# is literally that instrument's fire product, so the site shows each
# satellite the fire count IT detected, not one generic global number.
# (MODIS_NRT is Terra+Aqua combined -- FIRMS doesn't split MODIS by
# satellite -- which is stated honestly in the UI.) These thermal sensors
# are also what detect volcanic hotspots from orbit, which is why the
# USGS volcano note is attached here and NOWHERE ELSE -- no other satellite
# on this watchlist watches for fires or volcanoes.
_FIRE_SOURCE_BY_NORAD_ID: dict[int, dict] = {
    25994: {"instrument": "MODIS", "source": "MODIS_NRT", "note": "Terra + Aqua combined, as FIRMS reports MODIS"},
    27424: {"instrument": "MODIS", "source": "MODIS_NRT", "note": "Terra + Aqua combined, as FIRMS reports MODIS"},
    37849: {"instrument": "VIIRS", "source": "VIIRS_SNPP_NRT", "note": "Suomi NPP's VIIRS instrument"},
    43013: {"instrument": "VIIRS", "source": "VIIRS_NOAA20_NRT", "note": "NOAA-20's VIIRS instrument"},
}

# Real ocean-sensing satellites, mapped to the real Open-Meteo dataset that
# actually matches their OWN instrument -- fetched client-side (see app.js)
# since these satellites orbit fast enough that a value computed once an
# hour server-side would already be stale by the time someone loads the
# page (same reasoning as the precipitation-watch ground forecast).
#   "marine" -> Open-Meteo's Marine Weather API (sea-surface temp + wave
#     height). Attached ONLY to Sentinel-3A, whose SLSTR genuinely measures
#     sea-surface temperature and whose SRAL altimeter genuinely measures
#     significant wave height -- so both numbers correspond to real
#     instruments it carries.
#   "wind" -> Open-Meteo's regular forecast wind fields. Attached ONLY to
#     Metop-B, whose ASCAT instrument's whole job is measuring ocean-surface
#     wind speed and direction.
# NOTE: RADARSAT-2 is deliberately NOT here. It's a SAR radar imager (sea-ice
# and ship detection); it does not measure sea-surface temperature or wave
# height, so showing that data would misrepresent what it does.
_OCEAN_CONTEXT_NORAD_IDS: dict[int, str] = {
    41335: "marine",  # Sentinel-3A -- SLSTR (SST) + SRAL (wave height)
    38771: "wind",     # Metop-B -- ASCAT (ocean wind)
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
    "deep_space_probes": "Deep Space Probes (Not Earth-Orbiting)",
    "uncategorized": "Other",
}


def imagery_descriptor(norad_id: int) -> dict:
    if norad_id in _GIBS_LAYERS:
        return {"kind": "gibs", "options": _GIBS_LAYERS[norad_id]}
    if norad_id in _APOD_NORAD_IDS:
        return {"kind": "apod"}
    if norad_id in _COMMERCIAL_NO_FREE_IMAGERY:
        return {"kind": "commercial", "reason": _COMMERCIAL_NO_FREE_IMAGERY[norad_id]}
    return {"kind": "none"}


def fire_detection_for(norad_id: int, fire_counts_by_source: dict[str, int] | None) -> dict | None:
    """Real active-fire detection count for this satellite's OWN instrument
    (MODIS or VIIRS), or None if this isn't one of the four fire-detecting
    satellites. `count` is None (not 0) when FIRMS_MAP_KEY isn't configured,
    so the site can distinguish "not set up" from "genuinely zero fires."""
    spec = _FIRE_SOURCE_BY_NORAD_ID.get(norad_id)
    if spec is None:
        return None
    count = None
    if fire_counts_by_source is not None:
        count = fire_counts_by_source.get(spec["source"])
    return {"instrument": spec["instrument"], "source_note": spec["note"], "count": count}


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
    achievements: list[dict] | None
    volcano_alerts: list[dict] | None
    deep_space_status: dict | None
    ocean_context: str | None
    fire_detection: dict | None


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
    deep_space_probes: list[dict] | None = None,
    achievements: dict[int, list[dict]] | None = None,
    volcano_alerts: list[dict] | None = None,
    fire_counts_by_source: dict[str, int] | None = None,
) -> dict:
    """Pure function, no I/O -- takes already-loaded data (from state.json,
    watchlist.json, etc.) and shapes it into the JSON the website expects.
    Kept separate from any file reading so it's trivially testable."""
    object_types = object_types or {}
    categories = categories or {}
    instruments = instruments or {}
    conjunctions = conjunctions or []
    crew_by_craft = crew_by_craft or {}
    deep_space_probes = deep_space_probes or []
    achievements = achievements or {}
    volcano_alerts = volcano_alerts or []
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
                achievements=achievements.get(norad_id),
                # USGS volcano context is attached ONLY to the four fire-
                # detecting satellites, since thermal sensors are what
                # actually spot volcanic hotspots -- no other satellite here
                # watches for volcanoes.
                volcano_alerts=volcano_alerts if norad_id in _FIRE_SOURCE_BY_NORAD_ID else None,
                deep_space_status=None,
                ocean_context=_OCEAN_CONTEXT_NORAD_IDS.get(norad_id),
                fire_detection=fire_detection_for(norad_id, fire_counts_by_source),
            )
        )

    # Voyager 1/2, Pioneer 10/11 are real objects but not Earth-orbiting --
    # no NORAD ID/TLE, so they can't come from watchlist.json the way the
    # other 52 do. They're appended here as ordinary SiteSatellite entries
    # (using JPL Horizons' own real, always-negative spacecraft ID as a
    # pseudo norad_id -- can never collide with a real, always-positive
    # NORAD number) so they show up in the same satellite picker/dropdown,
    # under their own "Deep Space Probes" category, instead of being a
    # separate page section a person can't select the same way.
    for probe in deep_space_probes:
        satellites.append(
            SiteSatellite(
                norad_id=probe["pseudo_norad_id"],
                name=probe["name"],
                line1="",
                line2="",
                tle_age_days=None,
                object_type="Deep space probe (not Earth-orbiting)",
                imagery={"kind": "none"},
                latest_maneuver=None,
                satnogs_health=None,
                category="deep_space_probes",
                instruments={
                    "instruments": probe["instruments"],
                    "data_products": probe["data_products"],
                    "description": probe["description"],
                },
                conjunctions=[],
                crew_aboard=None,
                achievements=[{"headline": probe["milestone_headline"], "detail": probe["milestone_detail"]}],
                volcano_alerts=None,
                deep_space_status={
                    "launched": probe["launched"],
                    "epoch": probe["epoch"],
                    "distance_from_earth_km": probe["distance_from_earth_km"],
                    "distance_from_earth_au": probe["distance_from_earth_au"],
                    "speed_km_s": probe["speed_km_s"],
                },
                ocean_context=None,
                fire_detection=None,
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
                "achievements": s.achievements,
                "volcano_alerts": s.volcano_alerts,
                "deep_space_status": s.deep_space_status,
                "ocean_context": s.ocean_context,
                "fire_detection": s.fire_detection,
            }
            for s in satellites
        ],
    }
