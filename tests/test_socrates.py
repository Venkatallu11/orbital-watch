"""
Parser/filter tests using a fixture matching the REAL SOCRATES CSV column
names from CelesTrak's own format documentation (OBJECT_NAME_1/_2,
TCA_RANGE, DSE_1/_2, etc.) -- corrected from an earlier draft that guessed
wrong column names. See socrates.py docstring: celestrak.org itself blocks
automated fetches (403 on every path, not a sandbox-network-policy issue),
so this is verified against documentation, not a live response.
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orbital_watch.socrates import filter_to_watchlist, parse_socrates_csv  # noqa: E402

SAMPLE_CSV = (
    "NORAD_CAT_ID_1,OBJECT_NAME_1,DSE_1,NORAD_CAT_ID_2,OBJECT_NAME_2,DSE_2,"
    "TCA,TCA_RANGE,TCA_RELATIVE_SPEED,MAX_PROB,DILUTION\n"
    "25544,ISS,1.2,48274,COSMOS 2251 DEB,3.4,2026-07-05T03:14:22,0.85,7.1,0.0021,0.15\n"
    "44713,STARLINK-1234,0.5,39084,FENGYUN 1C DEB,2.1,2026-07-06T11:02:05,2.40,10.4,0.00003,0.09\n"
    "12345,OBJECT A,0.9,67890,OBJECT B,1.1,2026-07-07T22:41:10,4.90,5.6,0.0000009,0.22\n"
)


def test_parses_all_rows():
    conjunctions = parse_socrates_csv(SAMPLE_CSV)
    assert len(conjunctions) == 3


def test_parses_fields_correctly():
    conjunctions = parse_socrates_csv(SAMPLE_CSV)
    first = conjunctions[0]
    assert first.norad_id_1 == 25544
    assert first.name_1 == "ISS"
    assert first.norad_id_2 == 48274
    assert first.min_range_km == 0.85
    assert first.relative_speed_km_s == 7.1
    assert first.max_probability == 0.0021
    assert first.dilution == 0.15
    assert first.days_since_epoch_1 == 1.2
    assert first.days_since_epoch_2 == 3.4
    assert first.time_of_closest_approach == datetime(2026, 7, 5, 3, 14, 22)


def test_parses_the_alternate_human_readable_tca_format_too():
    """The HTML table shows TCA like '2026 Jul 05 03:14:22' -- the CSV
    format is unconfirmed live, so the parser must accept both."""
    text = SAMPLE_CSV.replace("2026-07-05T03:14:22", "2026 Jul 05 03:14:22")
    conjunctions = parse_socrates_csv(text)
    assert conjunctions[0].time_of_closest_approach == datetime(2026, 7, 5, 3, 14, 22)


def test_skips_malformed_rows_without_crashing():
    text = SAMPLE_CSV + "not,a,valid,row,here,,,,,,\n"
    conjunctions = parse_socrates_csv(text)
    assert len(conjunctions) == 3


def test_filter_matches_either_object_in_the_pair():
    conjunctions = parse_socrates_csv(SAMPLE_CSV)

    # 25544 is object 1 in the first row
    matches = filter_to_watchlist(conjunctions, {25544})
    assert len(matches) == 1
    assert matches[0].norad_id_1 == 25544

    # 39084 is object 2 in the second row -- must still match
    matches = filter_to_watchlist(conjunctions, {39084})
    assert len(matches) == 1
    assert matches[0].norad_id_2 == 39084


def test_filter_returns_empty_when_nothing_on_watchlist_is_involved():
    conjunctions = parse_socrates_csv(SAMPLE_CSV)
    matches = filter_to_watchlist(conjunctions, {999999})
    assert matches == []
