"""
Sliding-window rate limiter for Space-Track's documented limits (<30
requests/min, <300/hour -- see their Spaceflight Safety Handbook). Time and
sleep functions are injectable so tests don't actually sleep.
"""
from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls: int, period_seconds: float, time_fn=time.monotonic, sleep_fn=time.sleep):
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._call_times: deque = deque()

    def acquire(self) -> None:
        """Blocks (via the injected sleep function) until a call is
        allowed under this window, then records the call."""
        now = self._time_fn()
        while self._call_times and now - self._call_times[0] >= self.period_seconds:
            self._call_times.popleft()

        if len(self._call_times) >= self.max_calls:
            wait_seconds = self.period_seconds - (now - self._call_times[0])
            if wait_seconds > 0:
                self._sleep_fn(wait_seconds)
            now = self._time_fn()
            while self._call_times and now - self._call_times[0] >= self.period_seconds:
                self._call_times.popleft()

        self._call_times.append(self._time_fn())


class CompositeRateLimiter:
    """Enforces multiple windows at once, e.g. Space-Track's <30/min AND
    <300/hour simultaneously."""

    def __init__(self, limiters: list[RateLimiter]):
        self._limiters = limiters

    def acquire(self) -> None:
        for limiter in self._limiters:
            limiter.acquire()
