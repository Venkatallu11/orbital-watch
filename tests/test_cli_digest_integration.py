"""
End-to-end test of the unified digest through the actual CLI, with
SOCRATES/SatNOGS network calls monkeypatched out (their live-endpoint
assumptions are unverified -- see socrates.py/satnogs.py docstrings; this
test proves the CLI wiring/digest assembly, not that the live APIs match
these shapes).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import cli  # noqa: E402
from orbital_watch.socrates import Conjunction  # noqa: E402

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
NORAD_ID = 5


def test_digest_combines_socrates_and_satnogs_via_the_real_cli(tmp_path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    names_path = tmp_path / "names.json"
    names_path.write_text(json.dumps({str(NORAD_ID): "VANGUARD 1"}))
    state_path = tmp_path / "state.json"
    tle_path = tmp_path / "seed.tle"
    tle_path.write_text(f"{LINE1}\n{LINE2}\n")
    digest_path = tmp_path / "digest.md"

    fake_conjunction = Conjunction(
        norad_id_1=NORAD_ID, name_1="VANGUARD 1",
        norad_id_2=99999, name_2="RANDOM DEBRIS",
        time_of_closest_approach=datetime(2026, 7, 10, 0, 0, 0),
        min_range_km=1.2, relative_speed_km_s=8.0,
        max_probability=0.001, dilution=0.1,
        days_since_epoch_1=0.5, days_since_epoch_2=1.5,
    )
    monkeypatch.setattr("orbital_watch.socrates.fetch_conjunctions", lambda: [fake_conjunction])
    monkeypatch.setattr(
        "orbital_watch.satnogs.fetch_observations",
        lambda norad_id: [{"status": "good"}] * 3 + [{"status": "bad"}] * 5,
    )

    cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "file",
        "--tle-file", str(tle_path),
        "--object-names", str(names_path),
        "--include-socrates",
        "--include-satnogs",
        "--digest-out", str(digest_path),
    ])

    captured = capsys.readouterr()
    assert "Orbital Watch Digest" in captured.out
    assert "VANGUARD 1" in captured.out
    assert "RANDOM DEBRIS" in captured.out

    digest_text = digest_path.read_text()
    assert "VANGUARD 1" in digest_text
    assert "DEGRADED" in digest_text  # 3/8 good = 37.5%, below the 50% default threshold
