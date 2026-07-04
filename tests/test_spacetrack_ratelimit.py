"""
Confirms SpaceTrackClient actually consults its rate limiter before every
network call (login and query), rather than just constructing one and
never using it. HTTP calls are stubbed out entirely -- no network involved.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.tle_client import SpaceTrackClient  # noqa: E402

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


class FakeResponse:
    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, data=None, timeout=None):
        self.calls.append(("POST", url))
        return FakeResponse()

    def get(self, url, timeout=None):
        self.calls.append(("GET", url))
        return FakeResponse(text=f"{LINE1}\n{LINE2}\n")


class FakeRateLimiter:
    def __init__(self):
        self.acquire_count = 0

    def acquire(self):
        self.acquire_count += 1


def test_rate_limiter_is_consulted_before_login_and_query():
    fake_limiter = FakeRateLimiter()
    client = SpaceTrackClient(username="u", password="p", rate_limiter=fake_limiter)
    client._session = FakeSession()

    client.fetch_tles([5])

    # One acquire() for login, one for the query -- not zero, not skipped
    assert fake_limiter.acquire_count == 2


def test_second_fetch_does_not_repeat_login_but_still_rate_limits_the_query():
    fake_limiter = FakeRateLimiter()
    client = SpaceTrackClient(username="u", password="p", rate_limiter=fake_limiter)
    client._session = FakeSession()

    client.fetch_tles([5])
    client.fetch_tles([5])

    # 1 login + 2 queries = 3 total acquire() calls, not 4 (no re-login)
    assert fake_limiter.acquire_count == 3
    assert client._session.calls.count(("POST", "https://www.space-track.org/ajaxauth/login")) == 1
