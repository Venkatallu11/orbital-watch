"""
Satellite history entry point: reconstructs a timeline from git's own
commit history of state.json, rather than requiring you to dig through
raw `git log`/`git show` by hand.

Usage:
    python -m orbital_watch.history_cli --norad-id 25544 --repo . --object-name "ISS (ZARYA)"
"""
from __future__ import annotations

import argparse
import sys

from orbital_watch.history import build_satellite_history, format_history


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Show a satellite's history reconstructed from git's own commits of state.json."
    )
    parser.add_argument("--norad-id", type=int, required=True)
    parser.add_argument("--repo", default=".", help="Path to the git repo containing state.json")
    parser.add_argument("--state-file", default="state.json")
    parser.add_argument("--object-name", help="Friendly name for the header (defaults to 'NORAD <id>')")
    parser.add_argument("--out", help="Optional path to write the history as markdown")
    args = parser.parse_args(argv)

    points = build_satellite_history(args.repo, args.norad_id, args.state_file)
    name = args.object_name or f"NORAD {args.norad_id}"
    history_text = format_history(name, points)
    print(history_text)

    if args.out:
        with open(args.out, "w") as f:
            f.write(history_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
