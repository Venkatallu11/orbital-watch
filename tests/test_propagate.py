"""
Unit tests for compute_residual().

Building a *fully* physically-accurate "no maneuver happened" synthetic TLE
pair requires modeling J2 secular drift (argument of perigee / RAAN
precession) -- that's what SGP4 itself does internally, so hand-reconstructing
it for a fixture would just be re-deriving SGP4 badly. Instead these tests use
lightweight stub satellites with a controllable .sgp4() so we can pin down
exactly what compute_residual() sees and verify the vector math is correct.

End-to-end validation against a *real* historical maneuver (two genuine
Space-Track TLEs spanning a known burn) still needs to happen once this runs
somewhere with network access -- that's noted in the README, not faked here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datetime import datetime, timezone  # noqa: E402

from sgp4.api import Satrec  # noqa: E402

from orbital_watch.propagate import compute_residual, tle_age_days  # noqa: E402

REAL_LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
REAL_LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


class StubSatrec:
    """Duck-types just enough of Satrec for compute_residual()."""

    def __init__(self, satnum, jdsatepoch, jdsatepochF, r, v):
        self.satnum = satnum
        self.jdsatepoch = jdsatepoch
        self.jdsatepochF = jdsatepochF
        self._r = r
        self._v = v

    def sgp4(self, jd, fr):
        # Real Satrec.sgp4 ignores nothing about (jd, fr) -- for these tests
        # we just return the fixed state we were built with, since we're
        # testing compute_residual's diffing logic, not SGP4 itself.
        return 0, self._r, self._v


def test_identical_states_yield_zero_residual():
    r = (7000.0, 0.0, 0.0)
    v = (0.0, 7.5, 0.0)
    before = StubSatrec(25544, 2460000.5, 0.25, r, v)
    after = StubSatrec(25544, 2460000.5, 0.25, r, v)

    result = compute_residual(before, after)

    assert result.norad_id == 25544
    assert result.position_error_km == 0.0
    assert result.velocity_error_km_s == 0.0


def test_position_drift_is_measured_correctly():
    before = StubSatrec(25544, 2460000.5, 0.25, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    # 3-4-5 triangle in km so the distance is a clean 5.0
    after = StubSatrec(25544, 2460000.5, 0.25, (7003.0, 4.0, 0.0), (0.0, 7.5, 0.0))

    result = compute_residual(before, after)

    assert result.position_error_km == 5.0
    assert result.velocity_error_km_s == 0.0


def test_velocity_kick_is_measured_correctly():
    """Simulates an instantaneous delta-v: position hasn't diverged yet at
    the instant of the burn, but velocity has -- this is exactly the
    signature a real maneuver leaves in the residual right at the newer
    TLE's epoch."""
    before = StubSatrec(25544, 2460000.5, 0.25, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    after = StubSatrec(25544, 2460000.5, 0.25, (7000.0, 0.0, 0.0), (0.03, 7.5, 0.04))

    result = compute_residual(before, after)

    assert result.position_error_km == 0.0
    assert abs(result.velocity_error_km_s - 0.05) < 1e-9  # 3-4-5 triangle again


def test_epoch_gap_is_computed_in_days():
    before = StubSatrec(25544, 2460000.0, 0.0, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    after = StubSatrec(25544, 2460005.0, 0.5, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))

    result = compute_residual(before, after)

    assert abs(result.epoch_gap_days - 5.5) < 1e-9


def test_per_day_normalization_divides_by_the_real_gap():
    """A 10km drift over 5 days should read very differently per-day than
    the same 10km drift over 1 hour -- this is the fix for the documented
    false-positive problem where raw km alone can't be compared across
    objects/updates with different TLE gap sizes (see propagate.py docstring)."""
    before_5days = StubSatrec(25544, 2460000.0, 0.0, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    after_5days = StubSatrec(25544, 2460005.0, 0.0, (7006.0, 8.0, 0.0), (0.0, 7.5, 0.0))
    result_5days = compute_residual(before_5days, after_5days)
    assert result_5days.position_error_km == 10.0
    assert abs(result_5days.position_error_km_per_day - 2.0) < 1e-9  # 10km / 5days

    before_1hr = StubSatrec(99999, 2460000.0, 0.0, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    after_1hr = StubSatrec(99999, 2460000.0, 1 / 24.0, (7006.0, 8.0, 0.0), (0.0, 7.5, 0.0))
    result_1hr = compute_residual(before_1hr, after_1hr)
    assert result_1hr.position_error_km == 10.0
    assert abs(result_1hr.position_error_km_per_day - 240.0) < 1e-6  # 10km / (1/24)day

    # Same raw km, wildly different per-day rate -- this is the whole point.
    assert result_1hr.position_error_km_per_day > result_5days.position_error_km_per_day * 100


def test_near_zero_gap_is_floored_not_a_divide_by_zero():
    before = StubSatrec(25544, 2460000.5, 0.25, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    after = StubSatrec(25544, 2460000.5, 0.25, (7003.0, 4.0, 0.0), (0.0, 7.5, 0.0))

    result = compute_residual(before, after)

    assert result.epoch_gap_days == 0.0
    # Floored to 1 hour (1/24 day) for the per-day rate, not a ZeroDivisionError
    assert abs(result.position_error_km_per_day - (5.0 / (1 / 24.0))) < 1e-6


def test_uses_after_satellites_epoch_not_befores():
    """compute_residual must propagate `before` to `after`'s epoch -- if it
    used `before`'s own epoch instead, this test's stub would never notice,
    so we assert on the actual jd/fr values passed by inspecting a spy."""
    calls = []

    class SpySatrec(StubSatrec):
        def sgp4(self, jd, fr):
            calls.append((jd, fr))
            return super().sgp4(jd, fr)

    before = SpySatrec(25544, 2460000.5, 0.10, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
    after = SpySatrec(25544, 2460005.5, 0.40, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))

    compute_residual(before, after)

    assert calls[0] == (2460005.5, 0.40)  # `before` was queried at `after`'s epoch


def test_tle_age_days_uses_real_epoch_math():
    """REAL_LINE1/2's epoch is 2000 day 179.78495062 (~June 27.78). Using a
    real Satrec (not a stub) to prove the jday/epoch arithmetic is correct,
    not just plausible-looking."""
    sat = Satrec.twoline2rv(REAL_LINE1, REAL_LINE2)

    age = tle_age_days(sat, now=datetime(2000, 6, 30, 12, 0, 0, tzinfo=timezone.utc))

    assert abs(age - 2.715) < 0.01


def test_tle_age_days_is_zero_right_at_epoch():
    sat = Satrec.twoline2rv(REAL_LINE1, REAL_LINE2)
    epoch_as_datetime = datetime(2000, 6, 27, 18, 50, 20, tzinfo=timezone.utc)  # ~day 179.785

    age = tle_age_days(sat, now=epoch_as_datetime)

    assert abs(age) < 0.01  # within a few minutes of the TLE's own epoch
