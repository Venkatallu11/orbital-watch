"""
Prints/saves a sample of real, currently-active satellites per CelesTrak
GROUP, for hand-curating watchlist.json/names.json/categories.json.

Usage:
    python -m orbital_watch.discover_cli --groups stations,weather,science \\
        --limit-per-group 15 --out candidates.json
    python -m orbital_watch.discover_cli --names "GPM,ISS" --out candidates.json
"""
from __future__ import annotations

import argparse
import json
import sys

from orbital_watch.discover import fetch_by_name, fetch_group


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Discover real satellites by CelesTrak GROUP or NAME.")
    parser.add_argument("--groups", help="Comma-separated CelesTrak GROUP names")
    parser.add_argument("--names", help="Comma-separated CelesTrak NAME substrings to search for")
    parser.add_argument("--limit-per-group", type=int, default=15)
    parser.add_argument("--out", help="Optional path to also save full JSON output")
    args = parser.parse_args(argv)

    if not args.groups and not args.names:
        parser.error("at least one of --groups or --names is required")

    results: dict[str, list[dict]] = {}

    for group in (args.groups.split(",") if args.groups else []):
        group = group.strip()
        entries = fetch_group(group)
        sample = entries[: args.limit_per_group]
        results[f"group:{group}"] = [{"norad_id": e.norad_id, "name": e.name} for e in sample]
        print(f"\n=== GROUP {group} ({len(entries)} total, showing {len(sample)}) ===")
        for e in sample:
            print(f"  {e.norad_id}\t{e.name}")

    for name in (args.names.split(",") if args.names else []):
        name = name.strip()
        entries = fetch_by_name(name)
        results[f"name:{name}"] = [{"norad_id": e.norad_id, "name": e.name} for e in entries]
        print(f"\n=== NAME \"{name}\" ({len(entries)} match(es)) ===")
        for e in entries:
            print(f"  {e.norad_id}\t{e.name}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote full candidate list to {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
