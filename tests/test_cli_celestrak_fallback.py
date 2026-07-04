"""
Confirmed on a real GitHub Actions run (2026-07-04): celestrak.org timed
out from GitHub's shared runner IP range -- a known, documented issue
(CelesTrak's usage policy firewalls IPs exceeding its bandwidth limits,
and GitHub Actions runners share IP ranges across every workflow on
GitHub). These tests confirm the fallback-to-Space-Track behavior added
in response, without any real network calls.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import cli  # noqa: E402
from orbital_watch.tle_client import TleRecord  # noqa: E402

NORAD_ID = 25544


def test_falls_back_to_spacetrack_when_celestrak_fails_and_creds_present(tmp_path, capsys, monkeypatch):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"

    monkeypatch.setenv("SPACETRACK_USER", "someone@example.com")
    monkeypatch.setenv("SPACETRACK_PASS", "hunter2")

    def _raise(self, norad_ids):
        raise ConnectionError("simulated celestrak.org timeout")

    fake_record = TleRecord(
        norad_id=NORAD_ID,
        line1="1 25544U 98067A   26185.50000000  .00016717  00000-0  10270-3 0  9008",
        line2="2 25544  51.6400 208.9163 0006317  69.9862 25.2906 15.49560140123456",
    )

    monkeypatch.setattr("orbital_watch.tle_client.CelesTrakClient.fetch_by_norad_ids", _raise)
    monkeypatch.setattr(
        "orbital_watch.tle_client.SpaceTrackClient.__init__", lambda self, *a, **kw: None
    )
    monkeypatch.setattr(
        "orbital_watch.tle_client.SpaceTrackClient.fetch_tles", lambda self, norad_ids: [fake_record]
    )

    exit_code = cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "celestrak",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "falling back to Space-Track" in captured.out
    assert "Fetched 1 TLE(s) for 1 watched object(s)." in captured.out


def test_reports_clear_error_when_celestrak_fails_and_no_fallback_creds(tmp_path, capsys, monkeypatch):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"

    monkeypatch.delenv("SPACETRACK_USER", raising=False)
    monkeypatch.delenv("SPACETRACK_PASS", raising=False)

    def _raise(self, norad_ids):
        raise ConnectionError("simulated celestrak.org timeout")

    monkeypatch.setattr("orbital_watch.tle_client.CelesTrakClient.fetch_by_norad_ids", _raise)

    exit_code = cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "celestrak",
    ])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "no Space-Track credentials are set" in captured.out
