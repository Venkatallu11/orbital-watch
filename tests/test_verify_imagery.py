"""Tests the GIBS layer verification helper (offline, mocked -- GIBS isn't
reachable from every sandbox, see verify_imagery.py's docstring)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.verify_imagery import verify_layer  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, content_type, content, text=""):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.content = content
        self.text = text


class _FakeSession:
    def __init__(self, response):
        self.response = response
        self.last_url = None

    def get(self, url, timeout=None):
        self.last_url = url
        return self.response


def test_valid_image_response_is_recognized():
    session = _FakeSession(_FakeResponse(200, "image/jpeg", b"\xff\xd8fakejpegbytes"))
    check = verify_layer("MODIS_Terra_Thermal_Anomalies_All", "2026-07-04", session=session)
    assert check.is_valid_image is True
    assert check.byte_count == len(b"\xff\xd8fakejpegbytes")
    assert "LAYERS=MODIS_Terra_Thermal_Anomalies_All" in session.last_url


def test_error_xml_response_is_not_a_valid_image():
    session = _FakeSession(_FakeResponse(400, "text/xml", b"<Error/>", text="<Error>Layer not found</Error>"))
    check = verify_layer("NOT_A_REAL_LAYER", "2026-07-04", session=session)
    assert check.is_valid_image is False
    assert check.body_preview == "<Error>Layer not found</Error>"
