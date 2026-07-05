"""
Real-time US volcano alert status from USGS's public, keyless Volcano
Notification Service API (confirmed live via the research-probe workflow:
https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes).

SCOPE, HONESTLY: this is USGS data, covering only US-monitored volcanoes
(Alaska/Hawaii/Cascades/etc observatories) -- not global. It's also only
the LATEST notice per volcano; the API has no endpoint we found for a
queryable date-range history, so this reports a real current snapshot
("as of <real timestamp>"), not a fabricated "checked in the last 7 days"
log for any specific satellite.

Attached to the website's real thermal-imaging Earth observation
satellites (Terra/Aqua/Suomi NPP/NOAA-20 -- see site_data.py) as
supporting real-world context for what that class of satellite is used
for, not a claim that this pipeline's own satellite processing produced
the alert level.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

ELEVATED_VOLCANOES_URL = "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes"


@dataclass
class VolcanoAlert:
    volcano_name: str
    observatory: str
    alert_level: str
    color_code: str
    sent_utc: str
    notice_url: str


def fetch_elevated_volcanoes(session=None) -> list[VolcanoAlert]:
    """US volcanoes currently above NORMAL/GREEN status, per USGS. An empty
    list is a real, valid result (no US volcano is elevated right now), not
    a failure."""
    resp = (session or requests).get(ELEVATED_VOLCANOES_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [
        VolcanoAlert(
            volcano_name=v["volcano_name"],
            observatory=v.get("obs_fullname", ""),
            alert_level=v.get("alert_level", ""),
            color_code=v.get("color_code", ""),
            sent_utc=v.get("sent_utc", ""),
            notice_url=v.get("notice_url", ""),
        )
        for v in data
    ]
