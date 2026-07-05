"""Real temp git repo, same reasoning as test_history.py -- this proves
the CLI wiring around a real git history walk, not a mock."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import site_history_cli  # noqa: E402

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


def _commit_state(repo, state, message):
    (repo / "state.json").write_text(json.dumps(state))
    _git(repo, "add", "state.json")
    _git(repo, "commit", "-q", "-m", message)


def test_generates_history_json_from_a_real_git_repo(tmp_path, capsys):
    repo = _init_repo(tmp_path)
    _commit_state(repo, {"baseline_history": {"25544": [1.0]}}, "hop 1")
    _commit_state(repo, {"baseline_history": {"25544": [1.0, 1.2]}}, "hop 2")

    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    out_path = tmp_path / "history.json"

    exit_code = site_history_cli.main([
        "--watchlist", str(watchlist_path),
        "--repo", str(repo),
        "--out", str(out_path),
    ])

    assert exit_code == 0
    data = json.loads(out_path.read_text())
    points = data[str(NORAD_ID)]
    assert len(points) == 2
    assert points[0]["latest_residual_km_per_day"] == 1.0
    assert points[1]["latest_residual_km_per_day"] == 1.2
    assert "commit_time" in points[0]


def test_max_points_flag_is_respected(tmp_path):
    repo = _init_repo(tmp_path)
    for i in range(5):
        _commit_state(repo, {"baseline_history": {"25544": [float(i)]}}, f"hop {i}")

    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    out_path = tmp_path / "history.json"

    site_history_cli.main([
        "--watchlist", str(watchlist_path),
        "--repo", str(repo),
        "--max-points", "2",
        "--out", str(out_path),
    ])

    data = json.loads(out_path.read_text())
    assert len(data[str(NORAD_ID)]) == 2
