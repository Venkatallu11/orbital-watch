import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import history_cli  # noqa: E402


def _git(repo_path, *args):
    subprocess.run(["git", "-C", str(repo_path), *args], check=True, capture_output=True)


def test_prints_and_writes_history_from_a_real_repo(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    (repo / "state.json").write_text(json.dumps({"baseline_history": {"25544": [1.5]}}))
    _git(repo, "add", "state.json")
    _git(repo, "commit", "-q", "-m", "first run")

    out_path = tmp_path / "history.md"
    exit_code = history_cli.main([
        "--norad-id", "25544",
        "--repo", str(repo),
        "--object-name", "ISS (ZARYA)",
        "--out", str(out_path),
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "History for ISS (ZARYA)" in captured.out
    assert "residual 1.50 km/day" in captured.out
    assert out_path.exists()
    assert "ISS (ZARYA)" in out_path.read_text()


def test_defaults_object_name_to_norad_id_when_not_given(tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "state.json").write_text(json.dumps({"baseline_history": {}}))
    _git(repo, "add", "state.json")
    _git(repo, "commit", "-q", "-m", "first run")

    history_cli.main(["--norad-id", "99999", "--repo", str(repo)])

    captured = capsys.readouterr()
    assert "History for NORAD 99999" in captured.out
