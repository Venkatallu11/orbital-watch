"""
Confirms a candidate NASA GIBS layer identifier actually returns a real
image (not an error page) before it gets hardcoded into site_data.py's
imagery mapping -- the same "verify against the live API before trusting a
guessed identifier" discipline used for satellite NORAD IDs via
discover.py, applied to GIBS layer names instead.

Not part of the hourly pipeline. Run manually (locally, or via the
verify-gibs-layers workflow, since wvs.earthdata.nasa.gov isn't reachable
from every sandbox) when adding a new imagery layer.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

SNAPSHOT_URL = "https://wvs.earthdata.nasa.gov/api/v1/snapshot"


@dataclass
class LayerCheck:
    layer: str
    date: str
    status_code: int
    content_type: str
    byte_count: int
    is_valid_image: bool
    body_preview: str | None


def verify_layer(layer: str, date: str, session=None) -> LayerCheck:
    url = (
        f"{SNAPSHOT_URL}?REQUEST=GetSnapshot&LAYERS={layer}"
        f"&CRS=EPSG:4326&TIME={date}&BBOX=-90,-180,90,180&FORMAT=image/jpeg&WIDTH=320&HEIGHT=160"
    )
    resp = (session or requests).get(url, timeout=30)
    content_type = resp.headers.get("Content-Type", "")
    is_valid_image = resp.status_code == 200 and content_type.startswith("image/")
    return LayerCheck(
        layer=layer,
        date=date,
        status_code=resp.status_code,
        content_type=content_type,
        byte_count=len(resp.content),
        is_valid_image=is_valid_image,
        body_preview=None if is_valid_image else resp.text[:300],
    )
