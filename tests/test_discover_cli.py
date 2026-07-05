import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import discover_cli  # noqa: E402
from orbital_watch.discover import CatalogEntry  # noqa: E402


def test_main_prints_and_saves_sample(tmp_path, monkeypatch, capsys):
    def fake_fetch_group(group, session=None):
        return [CatalogEntry(norad_id=i, name=f"{group.upper()}-{i}") for i in range(1, 21)]

    monkeypatch.setattr(discover_cli, "fetch_group", fake_fetch_group)

    out_path = tmp_path / "candidates.json"
    rc = discover_cli.main([
        "--groups", "stations,science",
        "--limit-per-group", "5",
        "--out", str(out_path),
    ])

    assert rc == 0
    captured = capsys.readouterr()
    assert "stations" in captured.out
    assert "science" in captured.out

    data = json.loads(out_path.read_text())
    assert len(data["group:stations"]) == 5
    assert len(data["group:science"]) == 5
    assert data["group:stations"][0]["name"] == "STATIONS-1"


def test_names_search_reports_matches(tmp_path, monkeypatch, capsys):
    def fake_fetch_by_name(name, session=None):
        return [CatalogEntry(norad_id=99, name=f"{name} CORE OBSERVATORY")]

    monkeypatch.setattr(discover_cli, "fetch_by_name", fake_fetch_by_name)

    out_path = tmp_path / "candidates.json"
    rc = discover_cli.main(["--names", "GPM", "--out", str(out_path)])

    assert rc == 0
    captured = capsys.readouterr()
    assert "GPM CORE OBSERVATORY" in captured.out

    data = json.loads(out_path.read_text())
    assert data["name:GPM"][0]["norad_id"] == 99


def test_requires_at_least_one_of_groups_or_names():
    import pytest

    with pytest.raises(SystemExit):
        discover_cli.main([])
