import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch import biography_cli  # noqa: E402

SAMPLE_CSV = (
    "OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,"
    "LAUNCH_DATE,LAUNCH_SITE,DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,"
    "RCS,DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE\n"
    "VANGUARD 1,1958-002B,5,PAYLOAD,+,US,1958-03-17,AFETR,,132.71,34.25,"
    "3800,650,,,EA,IMP\n"
)


def test_generates_biography_from_offline_satcat_and_state(tmp_path, capsys):
    satcat_path = tmp_path / "satcat.csv"
    satcat_path.write_text(SAMPLE_CSV)

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "maneuver_events": {
            "5": [
                {
                    "timestamp": "2026-06-01T00:00:00+00:00",
                    "residual_km": 40.0,
                    "z_score": 5.0,
                    "reason": "residual is 5.0 sigma above baseline",
                }
            ]
        }
    }))

    out_path = tmp_path / "bio.md"

    exit_code = biography_cli.main([
        "--norad-id", "5",
        "--satcat-file", str(satcat_path),
        "--state", str(state_path),
        "--out", str(out_path),
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "VANGUARD 1" in captured.out
    assert "2026-06-01" in captured.out
    assert out_path.exists()
    assert "VANGUARD 1" in out_path.read_text()


def test_missing_norad_id_reports_error_not_crash(tmp_path, capsys):
    satcat_path = tmp_path / "satcat.csv"
    satcat_path.write_text(SAMPLE_CSV)
    state_path = tmp_path / "state.json"
    state_path.write_text("{}")

    exit_code = biography_cli.main([
        "--norad-id", "99999",
        "--satcat-file", str(satcat_path),
        "--state", str(state_path),
    ])

    assert exit_code == 1
    assert "not found" in capsys.readouterr().out
