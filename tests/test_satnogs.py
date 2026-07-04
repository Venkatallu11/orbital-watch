"""
Tests `summarize_observations` only, against a fixture matching the REAL
satnogs-network API schema (`status` field, values good/bad/failed/unknown/
future) confirmed by reading the actual source on GitLab -- see satnogs.py
docstring for what this corrected from an earlier, wrong guess
(`vetted_status`). No network involved here; this is a success-rate proxy,
not a full Doppler cross-check.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.satnogs import summarize_observations  # noqa: E402


def _obs(status):
    return {"status": status}


def test_healthy_object_is_not_flagged_degraded():
    observations = [_obs("good")] * 8 + [_obs("bad")] * 1
    health = summarize_observations(25544, observations)
    assert health.is_degraded is False
    assert health.success_rate == 8 / 9


def test_mostly_failing_object_is_flagged_degraded():
    observations = [_obs("bad")] * 6 + [_obs("good")] * 2
    health = summarize_observations(25544, observations)
    assert health.is_degraded is True
    assert health.success_rate == 2 / 8


def test_too_few_vetted_observations_is_not_flagged_even_if_all_bad():
    """Two bad observations isn't enough signal to call it 'degraded' --
    avoid false alarms from a thin sample."""
    observations = [_obs("bad"), _obs("bad")]
    health = summarize_observations(25544, observations)
    assert health.is_degraded is False


def test_all_unvetted_observations_report_no_success_rate_not_zero():
    observations = [_obs("unknown")] * 5
    health = summarize_observations(25544, observations)
    assert health.success_rate is None
    assert health.is_degraded is False
    assert health.unvetted_count == 5


def test_mixed_vetted_and_unvetted_counts_are_all_correct():
    observations = [_obs("good"), _obs("good"), _obs("bad"), _obs("unknown"), _obs("failed")]
    health = summarize_observations(25544, observations)
    assert health.total_observations == 5
    assert health.good_count == 2
    assert health.bad_count == 2  # "bad" and "failed" both count
    assert health.unvetted_count == 1


def test_future_scheduled_observations_count_as_pending_not_bad():
    """"future" means the pass hasn't happened yet -- it must not be
    counted as a failure just because it isn't "good"."""
    observations = [_obs("good"), _obs("good"), _obs("future"), _obs("future")]
    health = summarize_observations(25544, observations)
    assert health.bad_count == 0
    assert health.unvetted_count == 2
    assert health.success_rate == 1.0
