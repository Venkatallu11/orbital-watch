"""
The honest reentry-uncertainty entry point: given a TLE and a nominal
reentry time estimate (e.g. from Aerospace Corp's or CelesTrak's public
decay predictions -- this tool does NOT predict decay time itself, see
reentry.py), produces the full ground-track corridor across the
uncertainty window instead of a single false-precision pin/time.

Usage:
    python -m orbital_watch.reentry_cli --tle-file object.tle \\
        --nominal-time 2026-07-10T14:30:00Z --uncertainty-hours 8 \\
        --geojson-out corridor.geojson
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from orbital_watch.reentry import compute_ground_track_corridor, summarize_corridor, to_geojson
from orbital_watch.tle_client import load_tles_from_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Show the reentry uncertainty corridor for an object.")
    parser.add_argument("--tle-file", required=True)
    parser.add_argument("--nominal-time", required=True, help="ISO 8601, e.g. 2026-07-10T14:30:00Z")
    parser.add_argument("--uncertainty-hours", type=float, required=True)
    parser.add_argument("--step-seconds", type=int, default=60)
    parser.add_argument("--geojson-out", help="Optional path to write the corridor as GeoJSON")
    args = parser.parse_args(argv)

    records = load_tles_from_file(args.tle_file)
    if not records:
        print("No TLE found in file.")
        return 1
    record = records[0]

    nominal_time = datetime.fromisoformat(args.nominal_time.replace("Z", "+00:00"))
    if nominal_time.tzinfo is None:
        nominal_time = nominal_time.replace(tzinfo=timezone.utc)

    points = compute_ground_track_corridor(
        record.line1, record.line2, nominal_time, args.uncertainty_hours, args.step_seconds
    )
    print(summarize_corridor(points))

    if args.geojson_out:
        with open(args.geojson_out, "w") as f:
            json.dump(to_geojson(points), f, indent=2)
        print(f"\nWrote {len(points)}-point corridor to {args.geojson_out} "
              f"(open it at geojson.io or any GeoJSON-aware map viewer).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
