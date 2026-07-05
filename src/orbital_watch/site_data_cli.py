"""
Writes docs/data.json from the current state.json + watchlist -- the one
file the static website (docs/) reads. Meant to run right after
orbital-watch's main run in the same scheduled job (see the GitHub Actions
workflow), so the site always reflects the latest fetch.

Usage:
    python -m orbital_watch.site_data_cli --watchlist watchlist.json \\
        --state state.json --object-names names.json --out docs/data.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from orbital_watch.site_data import build_site_data
from orbital_watch.store import JsonStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate docs/data.json for the static website.")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--object-names", help="Optional JSON file: {\"norad_id\": \"friendly name\"}")
    parser.add_argument("--satcat-file", help="Optional local SATCAT CSV for object_type; skipped if omitted")
    parser.add_argument("--out", required=True, help="Path to write data.json, e.g. docs/data.json")
    args = parser.parse_args(argv)

    with open(args.watchlist) as f:
        watchlist = json.load(f)

    object_names: dict[int, str] = {}
    if args.object_names:
        with open(args.object_names) as f:
            object_names = {int(k): v for k, v in json.load(f).items()}

    object_types: dict[int, str] = {}
    if args.satcat_file:
        from orbital_watch.satcat import parse_satcat_csv

        with open(args.satcat_file) as f:
            records = parse_satcat_csv(f.read())
        object_types = {r.norad_id: r.object_type for r in records}

    store = JsonStore(args.state)
    previous_tles = store.get("previous_tles", {})
    maneuver_events = store.get("maneuver_events", {})

    # tle_age_days isn't persisted in state.json (it's computed fresh each
    # run relative to "now" -- see propagate.tle_age_days), so recompute it
    # here from each object's stored TLE rather than needing cli.py to pass
    # it through a second channel.
    from sgp4.api import Satrec

    from orbital_watch.propagate import tle_age_days

    tle_ages_days: dict[int, float] = {}
    for norad_id in watchlist:
        tle = previous_tles.get(str(norad_id))
        if tle:
            satrec = Satrec.twoline2rv(tle["line1"], tle["line2"])
            tle_ages_days[norad_id] = tle_age_days(satrec)

    # Persisted by cli.py's --include-satnogs path (see cli.py); empty for
    # a watchlist/run that never used --include-satnogs, which is a
    # correct "no data yet" state, not a bug.
    satnogs_health_state = store.get("satnogs_health", {})
    satnogs_healths_by_id: dict[int, dict] = {
        int(norad_id_str): health for norad_id_str, health in satnogs_health_state.items()
    }

    data = build_site_data(
        generated_at=datetime.now(timezone.utc).isoformat(),
        watchlist=watchlist,
        object_names=object_names,
        previous_tles=previous_tles,
        tle_ages_days=tle_ages_days,
        maneuver_events=maneuver_events,
        satnogs_healths_by_id=satnogs_healths_by_id,
        object_types=object_types,
    )

    with open(args.out, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote site data for {len(data['satellites'])} satellite(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
