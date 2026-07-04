import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.ratelimit import CompositeRateLimiter, RateLimiter  # noqa: E402


class FakeClock:
    """Lets tests control time deterministically instead of really sleeping."""

    def __init__(self):
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_calls_within_the_limit_dont_sleep():
    clock = FakeClock()
    limiter = RateLimiter(max_calls=3, period_seconds=60, time_fn=clock.time, sleep_fn=clock.sleep)

    for _ in range(3):
        limiter.acquire()

    assert clock.now == 0.0  # no sleeping needed


def test_exceeding_the_limit_sleeps_until_the_window_clears():
    clock = FakeClock()
    limiter = RateLimiter(max_calls=2, period_seconds=60, time_fn=clock.time, sleep_fn=clock.sleep)

    limiter.acquire()  # t=0
    limiter.acquire()  # t=0, now at the limit

    limiter.acquire()  # must wait until the first call ages out at t=60
    assert clock.now == 60.0


def test_old_calls_age_out_of_the_window():
    clock = FakeClock()
    limiter = RateLimiter(max_calls=2, period_seconds=60, time_fn=clock.time, sleep_fn=clock.sleep)

    limiter.acquire()  # t=0
    clock.now = 61  # first call is now outside the 60s window
    limiter.acquire()  # should NOT need to sleep -- window already has room
    limiter.acquire()  # this one is now the 2nd call within the last 60s

    assert clock.now == 61  # no extra sleep triggered by the aging-out calls


def test_composite_limiter_enforces_the_tightest_applicable_window():
    clock = FakeClock()
    per_minute = RateLimiter(max_calls=2, period_seconds=60, time_fn=clock.time, sleep_fn=clock.sleep)
    per_hour = RateLimiter(max_calls=100, period_seconds=3600, time_fn=clock.time, sleep_fn=clock.sleep)
    composite = CompositeRateLimiter([per_minute, per_hour])

    composite.acquire()
    composite.acquire()
    composite.acquire()  # exceeds the per-minute limit, not the per-hour one

    assert clock.now == 60.0  # gated by the tighter (per-minute) window
