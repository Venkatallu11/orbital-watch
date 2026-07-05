"""
Writes docs/history.json -- one file with every watched satellite's
residual/maneuver timeline, reconstructed from git's own commit history of
state.json (see history.py). Lets the website show a "View history"
timeline without needing a database or a separate always-growing log file:
every scheduled run already commits state.json, so the history was already
there one commit per hour.

Usage:
    python -m orbital_watch.site_history_cli --watchlist watchlist.json \\
        --repo . --out docs/history.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from orbital_watch.history import build_all_satellites_history


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate docs/history.json for the static website.")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--repo", default=".", help="Path to the git repo (default: current directory)")
    parser.add_argument("--max-points", type=int, default=200, help="Cap on history points kept per satellite")
    parser.add_argument("--out", required=True, help="Path to write history.json, e.g. docs/history.json")
    args = parser.parse_args(argv)

    with open(args.watchlist) as f:
        watchlist = json.load(f)

    history_by_id = build_all_satellites_history(args.repo, watchlist, max_points=args.max_points)

    serializable = {
        str(norad_id): [
            {
                "commit_time": point.commit_time.isoformat(),
                "commit_hash": point.commit_hash,
                "latest_residual_km_per_day": point.latest_residual_km_per_day,
                "cumulative_maneuver_count": point.cumulative_maneuver_count,
                "new_maneuver_events": point.new_maneuver_events,
            }
            for point in points
        ]
        for norad_id, points in history_by_id.items()
    }

    with open(args.out, "w") as f:
        json.dump(serializable, f, indent=2)

    total_points = sum(len(points) for points in history_by_id.values())
    print(f"Wrote history for {len(history_by_id)} satellite(s), {total_points} total point(s), to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
