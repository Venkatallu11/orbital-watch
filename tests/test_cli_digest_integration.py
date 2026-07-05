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
from orbital_watch.crew import CrewMember  # noqa: E402
from orbital_watch.deep_space import ProbeStatus  # noqa: E402
from orbital_watch.socrates import Conjunction  # noqa: E402
from orbital_watch.volcano import VolcanoAlert  # noqa: E402

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
    monkeypatch.setattr(
        "orbital_watch.crew.fetch_crew",
        lambda: [CrewMember(name="Jane Doe", craft="ISS")],
    )
    fake_probe = ProbeStatus(
        key="voyager_1", name="Voyager 1", launched="1977-09-05",
        milestone="test milestone", epoch="2026-Jul-05 00:00:00.0000",
        distance_from_earth_km=2.5e10, distance_from_earth_au=167.0,
        speed_km_s=37.5,
    )
    monkeypatch.setattr(
        "orbital_watch.deep_space.fetch_all_probes",
        lambda: [fake_probe],
    )
    fake_alert = VolcanoAlert(
        volcano_name="Great Sitkin", observatory="Alaska Volcano Observatory",
        alert_level="WATCH", color_code="ORANGE",
        sent_utc="2026-07-04 20:11:15", notice_url="https://example.com/notice",
    )
    monkeypatch.setattr(
        "orbital_watch.volcano.fetch_elevated_volcanoes",
        lambda: [fake_alert],
    )

    cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "file",
        "--tle-file", str(tle_path),
        "--object-names", str(names_path),
        "--include-socrates",
        "--include-satnogs",
        "--include-crew",
        "--include-deep-space",
        "--include-volcano-status",
        "--digest-out", str(digest_path),
    ])

    captured = capsys.readouterr()
    assert "Orbital Watch Digest" in captured.out
    assert "VANGUARD 1" in captured.out
    assert "RANDOM DEBRIS" in captured.out

    digest_text = digest_path.read_text()
    assert "VANGUARD 1" in digest_text
    assert "DEGRADED" in digest_text  # 3/8 good = 37.5%, below the 50% default threshold

    # SatNOGS health must be persisted to state.json, not just printed into
    # this run's digest and then lost -- site_data_cli.py depends on this.
    state = json.loads(state_path.read_text())
    assert state["satnogs_health"][str(NORAD_ID)]["good_count"] == 3
    assert state["satnogs_health"][str(NORAD_ID)]["is_degraded"] is True

    # Conjunctions must be persisted too (website's collision-risk panel
    # depends on this, same reasoning as SatNOGS health above). The
    # datetime field must survive as a JSON-serializable string.
    assert state["conjunctions"][0]["name_2"] == "RANDOM DEBRIS"
    assert state["conjunctions"][0]["time_of_closest_approach"] == "2026-07-10T00:00:00"

    # Crew data persisted for the website's "who's aboard" feature.
    assert state["crew_by_craft"]["ISS"] == ["Jane Doe"]

    # Deep-space-probe data persisted for the website's new "Deep Space
    # Probes" section.
    assert state["deep_space_probes"][0]["name"] == "Voyager 1"
    assert state["deep_space_probes"][0]["distance_from_earth_km"] == 2.5e10

    # Volcano alert data persisted for the website's volcano status card.
    assert state["volcano_alerts"][0]["volcano_name"] == "Great Sitkin"
    assert state["volcano_alerts"][0]["alert_level"] == "WATCH"
