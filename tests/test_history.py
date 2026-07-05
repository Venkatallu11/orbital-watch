"""
Tests against a REAL temporary git repo with real commits -- not mocked --
since the whole point of history.py is walking real git history via
subprocess `git log`/`git show`. A fake/mocked git would just prove the
mock works, not that the actual git commands are right.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.history import build_all_satellites_history, build_satellite_history, format_history  # noqa: E402

NORAD_ID = 25544


def _git(repo_path, *args):
    subprocess.run(["git", "-C", str(repo_path), *args], check=True, capture_output=True)


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _commit_state(repo, state: dict, message: str):
    (repo / "state.json").write_text(json.dumps(state))
    _git(repo, "add", "state.json")
    _git(repo, "commit", "-q", "-m", message)


def test_reconstructs_a_growing_residual_history(tmp_path):
    repo = _init_repo(tmp_path)

    _commit_state(repo, {"baseline_history": {"25544": [1.0]}}, "hop 1")
    _commit_state(repo, {"baseline_history": {"25544": [1.0, 1.2]}}, "hop 2")
    _commit_state(repo, {"baseline_history": {"25544": [1.0, 1.2, 0.9]}}, "hop 3")

    points = build_satellite_history(str(repo), NORAD_ID)

    assert len(points) == 3
    assert points[0].latest_residual_km_per_day == 1.0
    assert points[1].latest_residual_km_per_day == 1.2
    assert points[2].latest_residual_km_per_day == 0.9
    # Oldest first, chronological -- git's author-date resolution is 1
    # second, so rapid-fire test commits can tie; <= (not <) checks
    # ordering without assuming distinct timestamps.
    assert points[0].commit_time <= points[1].commit_time <= points[2].commit_time


def test_new_maneuver_events_appear_only_once_at_the_commit_they_were_added(tmp_path):
    repo = _init_repo(tmp_path)

    _commit_state(repo, {"maneuver_events": {"25544": []}}, "hop 1: quiet")
    _commit_state(
        repo,
        {"maneuver_events": {"25544": [{"timestamp": "t1", "reason": "big jump", "residual_km": 5, "z_score": 4}]}},
        "hop 2: maneuver detected",
    )
    _commit_state(
        repo,
        {
            "maneuver_events": {"25544": [
                {"timestamp": "t1", "reason": "big jump", "residual_km": 5, "z_score": 4},
            ]},
            "baseline_history": {"25544": [1.0]},  # unrelated change so this commit has an actual diff
        },
        "hop 3: still quiet, same event count",
    )

    points = build_satellite_history(str(repo), NORAD_ID)

    assert points[0].new_maneuver_events == []
    assert len(points[1].new_maneuver_events) == 1
    assert points[1].new_maneuver_events[0]["reason"] == "big jump"
    assert points[2].new_maneuver_events == []  # not re-reported at hop 3
    assert points[2].cumulative_maneuver_count == 1  # but the running total is still correct


def test_object_not_in_a_given_commit_yields_none_residual_not_a_crash(tmp_path):
    repo = _init_repo(tmp_path)

    _commit_state(repo, {"baseline_history": {"99999": [1.0]}}, "different satellite only")
    _commit_state(repo, {"baseline_history": {"25544": [2.0], "99999": [1.0]}}, "now ours shows up")

    points = build_satellite_history(str(repo), NORAD_ID)

    assert points[0].latest_residual_km_per_day is None
    assert points[1].latest_residual_km_per_day == 2.0


def test_format_history_renders_maneuvers_and_residuals(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_state(repo, {"baseline_history": {"25544": [1.0]}}, "quiet hop")
    _commit_state(
        repo,
        {
            "baseline_history": {"25544": [1.0, 50.0]},
            "maneuver_events": {"25544": [{"timestamp": "t1", "reason": "big jump", "residual_km": 50, "z_score": 6}]},
        },
        "maneuver hop",
    )

    points = build_satellite_history(str(repo), NORAD_ID)
    text = format_history("ISS (ZARYA)", points)

    assert "History for ISS (ZARYA)" in text
    assert "residual 1.00 km/day" in text
    assert "residual 50.00 km/day" in text
    assert "**MANEUVER**: big jump" in text


def test_build_all_satellites_history_matches_per_satellite_calls(tmp_path):
    repo = _init_repo(tmp_path)
    _commit_state(repo, {"baseline_history": {"25544": [1.0], "20580": [2.0]}}, "hop 1")
    _commit_state(repo, {"baseline_history": {"25544": [1.0, 1.2], "20580": [2.0, 2.5]}}, "hop 2")

    all_points = build_all_satellites_history(str(repo), [25544, 20580])

    assert [p.latest_residual_km_per_day for p in all_points[25544]] == [1.0, 1.2]
    assert [p.latest_residual_km_per_day for p in all_points[20580]] == [2.0, 2.5]


def test_build_all_satellites_history_caps_to_max_points(tmp_path):
    repo = _init_repo(tmp_path)
    for i in range(5):
        _commit_state(repo, {"baseline_history": {"25544": [float(i)]}}, f"hop {i}")

    all_points = build_all_satellites_history(str(repo), [25544], max_points=2)

    assert len(all_points[25544]) == 2
    assert all_points[25544][-1].latest_residual_km_per_day == 4.0  # most recent kept


def test_empty_history_is_explained_not_blank(tmp_path):
    repo = _init_repo(tmp_path)
    _git(repo, "commit", "--allow-empty", "-q", "-m", "unrelated commit, state.json never existed")

    points = build_satellite_history(str(repo), NORAD_ID)
    text = format_history("NORAD 25544", points)

    assert points == []
    assert "No history found" in text
