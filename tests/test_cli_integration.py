"""
End-to-end smoke test: drives the real CLI (fetch-from-file -> parse ->
persist state -> residual -> per-object baseline -> alert) across several
simulated "scheduled runs", using real TLE text round-tripped through
sgp4's own exporter (not hand-typed strings), so this exercises the actual
file format the tool will see in production.

The synthetic "after" states use a simple linear mean-anomaly advance
rather than full J2 secular modeling (see test_propagate.py for why), so
the absolute residual per hop isn't physically exact -- but it's *consistent*
across the quiet hops and clearly different for the injected maneuver hop,
which is exactly what the baseline is supposed to key off of. This test is
about proving the wiring end-to-end, not re-deriving orbital mechanics.
"""
import json
import sys
from math import pi
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sgp4.api import Satrec, WGS72  # noqa: E402
from sgp4.exporter import export_tle  # noqa: E402

from orbital_watch import cli  # noqa: E402

LINE1 = "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753"
LINE2 = "2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667"
NORAD_ID = 5


def _build_hop(base: Satrec, epoch_base: float, dt_minutes: float, extra_no_kozai: float = 0.0):
    sat = Satrec()
    mo_new = (base.mo + base.no_kozai * dt_minutes) % (2 * pi)
    sat.sgp4init(
        WGS72, "i", base.satnum, epoch_base + dt_minutes / 1440.0,
        base.bstar, base.ndot, base.nddot, base.ecco,
        base.argpo, base.inclo, mo_new,
        base.no_kozai + extra_no_kozai, base.nodeo,
    )
    return sat


def test_full_pipeline_flags_maneuver_but_not_routine_hops(tmp_path, capsys):
    base = Satrec.twoline2rv(LINE1, LINE2)
    epoch_base = base.jdsatepoch - 2433281.5 + base.jdsatepochF

    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps([NORAD_ID]))
    state_path = tmp_path / "state.json"

    current = base
    hop_minutes = 60

    # 5 routine hops: builds the baseline, none should alert
    for hop in range(1, 6):
        current = _build_hop(base, epoch_base, hop_minutes * hop)
        line1, line2 = export_tle(current)
        tle_path = tmp_path / f"hop_{hop}.tle"
        tle_path.write_text(f"{line1}\n{line2}\n")

        cli.main([
            "--watchlist", str(watchlist_path),
            "--state", str(state_path),
            "--source", "file",
            "--tle-file", str(tle_path),
        ])

    captured = capsys.readouterr()
    assert "[MANEUVER SUSPECTED]" not in captured.out

    # One more hop, but with an injected mean-motion bump simulating a real burn
    maneuvered = _build_hop(base, epoch_base, hop_minutes * 6, extra_no_kozai=0.0005)
    line1, line2 = export_tle(maneuvered)
    tle_path = tmp_path / "hop_6_maneuver.tle"
    tle_path.write_text(f"{line1}\n{line2}\n")

    cli.main([
        "--watchlist", str(watchlist_path),
        "--state", str(state_path),
        "--source", "file",
        "--tle-file", str(tle_path),
    ])

    captured = capsys.readouterr()
    assert f"NORAD {NORAD_ID}" in captured.out
    assert "[MANEUVER SUSPECTED]" in captured.out

    # State file should have persisted both the latest TLE and the baseline history
    state = json.loads(state_path.read_text())
    assert str(NORAD_ID) in state["previous_tles"]
    assert str(NORAD_ID) in state["baseline_history"]
    # 6 TLEs fetched total, but the very first one has no prior TLE to diff
    # against (nothing to compute a residual from yet) -- so only 5 residuals
    # ever reach the baseline.
    assert len(state["baseline_history"][str(NORAD_ID)]) == 5
