import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import reentry_cli  # noqa: E402

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"


def test_prints_honest_summary_and_writes_geojson(tmp_path, capsys):
    tle_path = tmp_path / "object.tle"
    tle_path.write_text(f"{LINE1}\n{LINE2}\n")
    geojson_path = tmp_path / "corridor.geojson"

    exit_code = reentry_cli.main([
        "--tle-file", str(tle_path),
        "--nominal-time", "2000-06-28T12:00:00Z",
        "--uncertainty-hours", "2",
        "--geojson-out", str(geojson_path),
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "ANYWHERE" in captured.out
    assert "Wrote" in captured.out

    geojson = json.loads(geojson_path.read_text())
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"][0]["geometry"]["coordinates"]) > 0
