"""
Parser tests only, using a fixture built from CelesTrak's documented SATCAT
CSV schema -- no network involved. See satcat.py docstring: the live fetch
itself is untested here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.satcat import norad_ids_matching_owners, parse_satcat_csv  # noqa: E402

SAMPLE_CSV = (
    "OBJECT_NAME,OBJECT_ID,NORAD_CAT_ID,OBJECT_TYPE,OPS_STATUS_CODE,OWNER,"
    "LAUNCH_DATE,LAUNCH_SITE,DECAY_DATE,PERIOD,INCLINATION,APOGEE,PERIGEE,"
    "RCS,DATA_STATUS_CODE,ORBIT_CENTER,ORBIT_TYPE\n"
    "ISS (ZARYA),1998-067A,25544,PAYLOAD,+,ISS,1998-11-20,TYMSC,,92.68,"
    "51.64,420,417,,,EA,IMP\n"
    "VANGUARD 1,1958-002B,5,PAYLOAD,,US,1958-03-17,AFETR,,132.71,34.25,"
    "3800,650,,,EA,IMP\n"
    "COSMOS 2251 DEB,1993-036CG,34427,DEBRIS,,CIS,,,2010-03-01,,,,,,,EA,IMP\n"
)


def test_parses_multiple_records():
    records = parse_satcat_csv(SAMPLE_CSV)
    assert len(records) == 3


def test_parses_payload_fields_correctly():
    records = parse_satcat_csv(SAMPLE_CSV)
    iss = next(r for r in records if r.norad_id == 25544)
    assert iss.object_name == "ISS (ZARYA)"
    assert iss.object_type == "PAYLOAD"
    assert iss.owner == "ISS"
    assert iss.launch_date == "1998-11-20"
    assert iss.decay_date is None
    assert iss.period_minutes == 92.68
    assert iss.inclination_deg == 51.64


def test_handles_debris_with_missing_orbital_fields():
    records = parse_satcat_csv(SAMPLE_CSV)
    debris = next(r for r in records if r.norad_id == 34427)
    assert debris.object_type == "DEBRIS"
    assert debris.decay_date == "2010-03-01"
    assert debris.period_minutes is None  # blank field -> None, not a crash


def test_skips_rows_with_unparseable_norad_id():
    text = SAMPLE_CSV + "BAD ROW,,not-a-number,PAYLOAD,,US,,,,,,,,,,,\n"
    records = parse_satcat_csv(text)
    assert len(records) == 3  # the bad row is skipped, not raised


def test_matches_only_the_given_owner():
    records = parse_satcat_csv(SAMPLE_CSV)
    matched = norad_ids_matching_owners(records, {"CIS"})
    assert matched == {34427}


def test_owner_matching_is_case_insensitive():
    records = parse_satcat_csv(SAMPLE_CSV)
    matched = norad_ids_matching_owners(records, {"cis"})
    assert 34427 in matched


def test_no_owners_given_matches_nothing():
    records = parse_satcat_csv(SAMPLE_CSV)
    matched = norad_ids_matching_owners(records, set())
    assert matched == set()


def test_an_object_missing_from_satcat_data_is_never_matched():
    """A watchlist ID that SATCAT doesn't have a record for must not be
    silently dropped by exclusion logic that never saw it."""
    records = parse_satcat_csv(SAMPLE_CSV)
    matched = norad_ids_matching_owners(records, {"CIS"})
    assert 999999 not in matched  # not in SATCAT at all -- must not match
