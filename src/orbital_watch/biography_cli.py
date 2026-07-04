"""
The "satellite biography" entry point: punch in a NORAD ID, get launch
history + owner + plain-language maneuver timeline in one place, instead
of piecing it together from SATCAT codes, Wikipedia, and McDowell's
newsletter archive.

Usage:
    python -m orbital_watch.biography_cli --norad-id 25544 \\
        --satcat-file satcat.csv --state state.json [--out iss_bio.md]
"""
from __future__ import annotations

import argparse
import sys

from orbital_watch.biography import build_biography
from orbital_watch.satcat import fetch_satcat, parse_satcat_csv
from orbital_watch.store import JsonStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a plain-English satellite biography.")
    parser.add_argument("--norad-id", type=int, required=True)
    parser.add_argument("--satcat-file", help="Local SATCAT CSV (offline mode). Omit to fetch live.")
    parser.add_argument("--state", required=True, help="orbital-watch state.json (for maneuver history)")
    parser.add_argument("--out", help="Optional path to write the biography as markdown")
    args = parser.parse_args(argv)

    if args.satcat_file:
        with open(args.satcat_file) as f:
            records = parse_satcat_csv(f.read())
    else:
        records = fetch_satcat([args.norad_id])

    matches = [r for r in records if r.norad_id == args.norad_id]
    if not matches:
        print(f"NORAD {args.norad_id} not found in SATCAT data provided.")
        return 1

    store = JsonStore(args.state)
    maneuver_events = store.get("maneuver_events", {}).get(str(args.norad_id), [])

    biography = build_biography(matches[0], maneuver_events)
    print(biography)

    if args.out:
        with open(args.out, "w") as f:
            f.write(biography)

    return 0


if __name__ == "__main__":
    sys.exit(main())
