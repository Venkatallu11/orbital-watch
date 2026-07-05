"""Tests the USGS volcano alert fetcher (offline, mocked). The fixture data
below matches the real shape captured from a live call to
https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes via
the research-probe workflow on 2026-07-05."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.volcano import VolcanoAlert, fetch_elevated_volcanoes  # noqa: E402

REAL_SHAPE_RESPONSE = [
    {
        "obs_fullname": "Alaska Volcano Observatory",
        "obs_abbr": "avo",
        "volcano_name": "Great Sitkin",
        "vnum": "311120",
        "notice_type_cd": "DU",
        "notice_identifier": "DOI-USGS-AVO-2026-07-04T20:09:45+00:00",
        "sent_utc": "2026-07-04 20:11:15",
        "sent_unixtime": 1783195875,
        "color_code": "ORANGE",
        "alert_level": "WATCH",
        "notice_url": "https://volcanoes.usgs.gov/hans-public/notice/DOI-USGS-AVO-2026-07-04T20:09:45+00:00",
        "notice_data": "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice/DOI-USGS-AVO-2026-07-04T20:09:45+00:00",
    },
    {
        "obs_fullname": "Alaska Volcano Observatory",
        "obs_abbr": "avo",
        "volcano_name": "Shishaldin",
        "vnum": "311360",
        "notice_type_cd": "DU",
        "notice_identifier": "DOI-USGS-AVO-2026-07-04T20:09:45+00:00",
        "sent_utc": "2026-07-04 20:11:15",
        "sent_unixtime": 1783195875,
        "color_code": "YELLOW",
        "alert_level": "ADVISORY",
        "notice_url": "https://volcanoes.usgs.gov/hans-public/notice/DOI-USGS-AVO-2026-07-04T20:09:45+00:00",
        "notice_data": "https://volcanoes.usgs.gov/hans-public/api/notice/getNotice/DOI-USGS-AVO-2026-07-04T20:09:45+00:00",
    },
]


class _FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class _FakeSession:
    def __init__(self, data):
        self.data = data

    def get(self, url, timeout=None):
        return _FakeResponse(self.data)


def test_fetch_elevated_volcanoes_parses_real_response_shape():
    session = _FakeSession(REAL_SHAPE_RESPONSE)
    alerts = fetch_elevated_volcanoes(session=session)

    assert len(alerts) == 2
    assert isinstance(alerts[0], VolcanoAlert)
    assert alerts[0].volcano_name == "Great Sitkin"
    assert alerts[0].alert_level == "WATCH"
    assert alerts[0].color_code == "ORANGE"
    assert alerts[0].observatory == "Alaska Volcano Observatory"


def test_no_elevated_volcanoes_is_a_valid_empty_result():
    session = _FakeSession([])
    assert fetch_elevated_volcanoes(session=session) == []
