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

from orbital_watch.propagate import compute_residual  # noqa: E402


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
