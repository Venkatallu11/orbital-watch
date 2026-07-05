"""
Fetches "who's currently in space" from Open Notify -- a real, free,
keyless public API (http://api.open-notify.org/astros.json) that lists
every person currently aboard a crewed spacecraft and which craft they're
on (ISS, Tiangong, etc).

FETCHED SERVER-SIDE ON PURPOSE: Open Notify only serves this endpoint over
plain HTTP, not HTTPS (confirmed -- it has no TLS certificate for the API
host). A browser on our HTTPS-served GitHub Pages site would silently
block a client-side fetch() to an http:// URL as mixed content, so this
would never work if called from app.js. Fetching it here during the
scheduled run and baking the result into docs/data.json sidesteps that
entirely -- server-to-server HTTP has no such restriction.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

OPEN_NOTIFY_URL = "http://api.open-notify.org/astros.json"


@dataclass
class CrewMember:
    name: str
    craft: str


def fetch_crew(session=None) -> list[CrewMember]:
    resp = (session or requests).get(OPEN_NOTIFY_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return [CrewMember(name=p["name"], craft=p["craft"]) for p in data.get("people", [])]


def crew_by_craft(crew: list[CrewMember]) -> dict[str, list[str]]:
    """Groups crew member names by craft (e.g. {"ISS": [...], "Tiangong": [...]})."""
    by_craft: dict[str, list[str]] = {}
    for member in crew:
        by_craft.setdefault(member.craft, []).append(member.name)
    return by_craft
