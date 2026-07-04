"""
Drives the real CLI's --exclude-owners-file / --satcat-file path end to
end: a watchlist with two objects, one owned by an excluded owner, should
only fetch/process the other.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import cli  # noqa: E402

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
NORAD_ID = 5
EXCLUDED_NORAD_ID = 25544

SATCAT_CSV = (
    "OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,"
    "LAUNCH_DATE,LAUNCH_SITE,DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,"
    "RCS,DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE\n"
    "VANGUARD 1,1958-002B,5,PAYLOAD,,US,1958-03-17,AFETR,,132.71,34.25,"
    "3800,650,,,EA,IMP\n"
    "STARLINK-1234,2019-999A,25544,PAYLOAD,,SpaceX,2019-01-01,AFETR,,95.0,"
    "53.0,550,540,,,EA,IMP\n"
)


def test_excluded_owner_object_is_never_fetched_or_processed(tmp_path, capsys):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID, EXCLUDED_NORAD_ID]))

    satcat_path = tmp_path / "satcat.csv"
    satcat_path.write_text(SATCAT_CSV)

    owners_path = tmp_path / "excluded_owners.json"
    owners_path.write_text(json.dumps(["SpaceX"]))

    # Only NORAD_ID's TLE is in the fixture file -- if the excluded object
    # were still in the watchlist, the run wouldn't crash (it just wouldn't
    # find a matching record), so the real proof is in the printed
    # exclusion message and the fetched-object count below.
    tle_path = tmp_path / "seed.tle"
    tle_path.write_text(f"{LINE1}\n{LINE2}\n")
    state_path = tmp_path / "state.json"

    cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "file",
        "--tle-file", str(tle_path),
        "--exclude-owners-file", str(owners_path),
        "--satcat-file", str(satcat_path),
    ])

    captured = capsys.readouterr()
    assert "Excluding 1 object(s)" in captured.out
    assert str(EXCLUDED_NORAD_ID) in captured.out
    assert "Fetched 1 TLE(s) for 1 watched object(s)." in captured.out


def test_satcat_fetch_failure_falls_back_to_unfiltered_watchlist(tmp_path, capsys, monkeypatch):
    """Confirmed on a real GitHub Actions runner (2026-07-04) that
    fetch_satcat's live endpoint actually works from normal internet --
    this test originally relied on network being unavailable *in this
    sandbox* as a stand-in for "the fetch failed," which is an
    environment-dependent assumption that broke the moment it ran
    somewhere with real internet access. Mocking the failure explicitly
    is correct regardless of what environment runs this test."""
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))

    owners_path = tmp_path / "excluded_owners.json"
    owners_path.write_text(json.dumps(["SpaceX"]))

    tle_path = tmp_path / "seed.tle"
    tle_path.write_text(f"{LINE1}\n{LINE2}\n")
    state_path = tmp_path / "state.json"

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr("orbital_watch.satcat.fetch_satcat", _raise)

    # No --satcat-file given -> _apply_owner_exclusions calls the (mocked,
    # failing) live fetch_satcat; the run must still complete using the
    # unfiltered watchlist rather than crashing.
    exit_code = cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "file",
        "--tle-file", str(tle_path),
        "--exclude-owners-file", str(owners_path),
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Warning: owner-exclusion SATCAT fetch failed" in captured.out
    assert "Fetched 1 TLE(s) for 1 watched object(s)." in captured.out
