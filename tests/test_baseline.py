import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.baseline import PerObjectBaseline  # noqa: E402


def test_builds_baseline_before_flagging_anything():
    b = PerObjectBaseline(min_samples=4)
    for residual in [1.0, 1.1, 0.9, 1.05]:
        verdict = b.evaluate(12345, residual)
        assert verdict.is_anomalous is False
        assert verdict.z_score is None


def test_quiet_object_flags_a_sudden_jump():
    """An object with a stable, small residual history should flag a big
    jump -- this is the core 'someone maneuvered a normally-quiet satellite'
    case."""
    b = PerObjectBaseline(min_samples=4, z_threshold=3.0)
    for residual in [0.5, 0.6, 0.55, 0.52, 0.58, 0.61]:
        verdict = b.evaluate(99999, residual)
        assert verdict.is_anomalous is False

    verdict = b.evaluate(99999, 25.0)  # a real burn, not routine drift
    assert verdict.is_anomalous is True
    assert verdict.z_score > 3.0


def test_noisy_constellation_satellite_does_not_spam_alerts():
    """A Starlink-like object that maneuvers frequently should build a wide
    baseline and NOT alert on more of the same -- this is the fix for the
    'noisy objects' problem discussed earlier."""
    b = PerObjectBaseline(min_samples=4, z_threshold=3.0)
    noisy_history = [2.0, 8.0, 3.0, 9.5, 4.0, 7.0, 2.5, 8.5]
    for residual in noisy_history:
        b.evaluate(44713, residual)

    verdict = b.evaluate(44713, 9.0)  # well within this object's own normal range
    assert verdict.is_anomalous is False


def test_objects_are_tracked_independently():
    b = PerObjectBaseline(min_samples=4, z_threshold=3.0)
    for residual in [0.5, 0.55, 0.52, 0.51]:
        b.evaluate(1, residual)
    for residual in [50.0, 55.0, 52.0, 51.0]:
        b.evaluate(2, residual)

    # A residual that would be a huge anomaly for object 1 is dead normal for object 2
    verdict_1 = b.evaluate(1, 53.0)
    verdict_2 = b.evaluate(2, 53.0)
    assert verdict_1.is_anomalous is True
    assert verdict_2.is_anomalous is False
