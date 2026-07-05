"""Tests the JPL Horizons deep-space-probe fetcher (offline, mocked).

The fixture text below is a trimmed, real response body captured from a
live call to https://ssd.jpl.nasa.gov/api/horizons.api for Voyager 1 on
2026-07-05 (verified live via the research-probe workflow before writing
this module) -- not synthesized from a guess at the format.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.deep_space import (  # noqa: E402
    AU_KM,
    PROBES,
    ProbeStatus,
    _parse_horizons_vectors,
    fetch_all_probes,
    fetch_probe_status,
)

REAL_VOYAGER_1_RESULT = r"""

*******************************************************************************
Ephemeris / API_USER Sun Jul  5 08:53:25 2026 Pasadena, USA      / Horizons
*******************************************************************************
Target body name: Voyager 1 (spacecraft) (-31)    {source: Voyager_1_ST+refit2022_m}
Center body name: Earth (399)                     {source: Voyager_1_ST+refit2022_m}
*******************************************************************************
$$SOE
2461226.500000000 = A.D. 2026-Jul-05 00:00:00.0000 TDB
 X =-4.829079412725183E+09 Y =-2.021678227497343E+10 Z = 1.473470970664544E+10
 VX=-3.064960153400311E+01 VY=-2.001186739707130E+01 VZ= 9.834450913571079E+00
 LT= 8.498686624776277E+04 RG= 2.547842153013403E+10 RR= 2.737582092238698E+01
2461227.500000000 = A.D. 2026-Jul-06 00:00:00.0000 TDB
 X =-4.831722847521301E+09 Y =-2.023413828000000E+10 Z = 1.474420000000000E+10
 VX=-3.064000000000000E+01 VY=-2.000000000000000E+01 VZ= 9.830000000000000E+00
 LT= 8.500000000000000E+04 RG= 2.548500000000000E+10 RR= 2.736000000000000E+01
$$EOE
*******************************************************************************
"""


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_params = params
        return _FakeResponse(self.payload)


def test_parse_horizons_vectors_extracts_first_record():
    parsed = _parse_horizons_vectors(REAL_VOYAGER_1_RESULT)
    assert parsed["epoch"] == "2026-Jul-05 00:00:00.0000"
    assert parsed["distance_km"] == 2.547842153013403e10
    # speed = sqrt(VX^2 + VY^2 + VZ^2), not just RR (which is only the
    # radial/receding component of velocity)
    assert 37 < parsed["speed_km_s"] < 38


def test_fetch_probe_status_returns_real_fields():
    session = _FakeSession({"signature": {"source": "NASA/JPL Horizons API"}, "result": REAL_VOYAGER_1_RESULT})
    status = fetch_probe_status("voyager_1", session=session)

    assert isinstance(status, ProbeStatus)
    assert status.name == "Voyager 1"
    assert status.launched == "1977-09-05"
    assert status.distance_from_earth_km == 2.547842153013403e10
    assert status.distance_from_earth_au == status.distance_from_earth_km / AU_KM
    assert status.speed_km_s > 0
    # sanity-checks the command code sent to Horizons matches Voyager 1
    assert session.last_params["COMMAND"] == "-31"


def test_fetch_probe_status_raises_on_horizons_error():
    session = _FakeSession({"error": "Unknown target body"})
    try:
        fetch_probe_status("voyager_1", session=session)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Voyager 1" in str(exc)


def test_fetch_all_probes_covers_all_four():
    session = _FakeSession({"result": REAL_VOYAGER_1_RESULT})
    statuses = fetch_all_probes(session=session)
    assert {s.key for s in statuses} == set(PROBES.keys())
    assert len(statuses) == 4
