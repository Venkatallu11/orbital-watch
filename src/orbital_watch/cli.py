"""
Entry point, meant to be run on a schedule (cron / GitHub Actions), e.g.
hourly. Each run:
  1. Loads the watchlist (NORAD IDs) and last-seen TLE + baseline state.
  2. Fetches current TLEs for the watchlist, computes SGP4 residuals against
     each object's own rolling baseline.
  3. Optionally pulls CelesTrak SOCRATES (conjunction/collision risk) and
     SatNOGS (observation health) for the same watchlist.
  4. Combines all of that into ONE digest instead of three separate manual
     checks, alerts (console + optional webhook) on anything anomalous, and
     persists maneuver events for the biography page (see biography_cli.py).

Usage:
    python -m orbital_watch.cli --watchlist watchlist.json --state state.json
    python -m orbital_watch.cli --watchlist watchlist.json --state state.json --source celestrak
    python -m orbital_watch.cli --watchlist watchlist.json --state state.json --source file --tle-file sample.tle
    python -m orbital_watch.cli --watchlist watchlist.json --state state.json --include-socrates --include-satnogs --include-crew --include-deep-space --digest-out digest.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from sgp4.api import Satrec

from orbital_watch.alert import format_alert, send_console, send_webhook
from orbital_watch.baseline import PerObjectBaseline
from orbital_watch.digest import ManeuverAlert, generate_digest
from orbital_watch.propagate import compute_residual, tle_age_days
from orbital_watch.store import JsonStore
from orbital_watch.tle_client import CelesTrakClient, SpaceTrackClient, load_tles_from_file


def build_satrec(record) -> Satrec:
    return Satrec.twoline2rv(record.line1, record.line2)


def _fetch_conjunctions_safely(watchlist: set[int]) -> list:
    """SOCRATES ingestion is best-effort and untested against the live
    endpoint (see socrates.py) -- a failure here shouldn't take down the
    whole run, just skip that section of the digest."""
    from orbital_watch.socrates import fetch_conjunctions, filter_to_watchlist

    try:
        return filter_to_watchlist(fetch_conjunctions(), watchlist)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"Warning: SOCRATES fetch failed ({exc}), skipping conjunction section.")
        return []


def _fetch_crew_safely() -> dict[str, list[str]]:
    """Open Notify's "people in space now" API, grouped by craft (ISS,
    Tiangong). Best-effort like the other optional fetches -- a failure
    here shouldn't take down the whole run."""
    from orbital_watch.crew import crew_by_craft, fetch_crew

    try:
        return crew_by_craft(fetch_crew())
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"Warning: Open Notify crew fetch failed ({exc}), skipping.")
        return {}


def _fetch_deep_space_probes_safely() -> list:
    """Voyager 1/2, Pioneer 10/11 real live distance/speed from JPL
    Horizons -- best-effort like the other optional fetches, since a
    third-party API being briefly down shouldn't take down the whole run."""
    from dataclasses import asdict

    from orbital_watch.deep_space import fetch_all_probes

    try:
        return [asdict(status) for status in fetch_all_probes()]
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"Warning: JPL Horizons deep-space-probe fetch failed ({exc}), skipping.")
        return []


def _fetch_global_fire_count_safely() -> int | None:
    """NASA FIRMS' real, GLOBAL (not US-only) active-fire detection count
    for the last 24h. Requires a free FIRMS_MAP_KEY (see firms.py's
    docstring for why -- unlike NASA's APOD, FIRMS has no public shared
    key). Returns None (not 0) when no key is configured, so the site can
    tell "not set up yet" apart from "genuinely zero fires detected"."""
    map_key = os.environ.get("FIRMS_MAP_KEY")
    if not map_key:
        return None

    from orbital_watch.firms import fetch_global_fire_count

    try:
        return fetch_global_fire_count(map_key)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"Warning: NASA FIRMS fire-count fetch failed ({exc}), skipping.")
        return None


def _fetch_volcano_status_safely() -> list:
    """USGS's real-time elevated-volcano alert feed (US-only) -- best-effort
    like the other optional fetches."""
    from dataclasses import asdict

    from orbital_watch.volcano import fetch_elevated_volcanoes

    try:
        return [asdict(alert) for alert in fetch_elevated_volcanoes()]
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"Warning: USGS volcano status fetch failed ({exc}), skipping.")
        return []


def _fetch_satnogs_health_safely(watchlist: set[int]) -> list:
    """Same reasoning as _fetch_conjunctions_safely -- SatNOGS API schema
    assumptions are untested here (see satnogs.py)."""
    from orbital_watch.satnogs import fetch_observations, summarize_observations

    healths = []
    for norad_id in sorted(watchlist):
        try:
            observations = fetch_observations(norad_id)
            healths.append(summarize_observations(norad_id, observations))
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
            print(f"Warning: SatNOGS fetch failed for NORAD {norad_id} ({exc}), skipping.")
    return healths


def _apply_owner_exclusions(watchlist: set[int], owners: set[str], satcat_file: str | None) -> set[int]:
    """Auto-exclude noisy constellations (e.g. Starlink) by SATCAT owner
    instead of requiring every noisy object to be hand-listed. Failure here
    (SATCAT fetch is untested live, see satcat.py) falls back to the
    unfiltered watchlist rather than aborting the whole run."""
    from orbital_watch.satcat import fetch_satcat, norad_ids_matching_owners, parse_satcat_csv

    try:
        if satcat_file:
            with open(satcat_file) as f:
                records = parse_satcat_csv(f.read())
        else:
            records = fetch_satcat(sorted(watchlist))
        excluded = norad_ids_matching_owners(records, owners)
        if excluded:
            print(f"Excluding {len(excluded)} object(s) owned by {sorted(owners)}: {sorted(excluded)}")
        return watchlist - excluded
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        print(f"Warning: owner-exclusion SATCAT fetch failed ({exc}), using unfiltered watchlist.")
        return watchlist


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Watch a satellite watchlist for unexplained maneuvers.")
    parser.add_argument("--watchlist", required=True, help="JSON file: list of NORAD IDs")
    parser.add_argument("--state", required=True, help="JSON file used to persist state between runs")
    parser.add_argument("--source", choices=["celestrak", "spacetrack", "file"], default="celestrak")
    parser.add_argument("--tle-file", help="Required when --source file")
    parser.add_argument("--webhook-url", default=os.environ.get("ALERT_WEBHOOK_URL"))
    parser.add_argument("--z-threshold", type=float, default=3.0)
    parser.add_argument("--include-socrates", action="store_true", help="Fetch CelesTrak SOCRATES conjunction data")
    parser.add_argument("--include-satnogs", action="store_true", help="Fetch SatNOGS observation health")
    parser.add_argument("--include-crew", action="store_true", help="Fetch Open Notify 'people in space now' data")
    parser.add_argument("--include-deep-space", action="store_true", help="Fetch JPL Horizons distance/speed for Voyager 1/2, Pioneer 10/11")
    parser.add_argument("--include-volcano-status", action="store_true", help="Fetch USGS real-time elevated-volcano alerts (US-only)")
    parser.add_argument("--object-names", help="Optional JSON file: {\"norad_id\": \"friendly name\"} for the digest")
    parser.add_argument("--digest-out", help="Optional path to write the combined digest as markdown")
    parser.add_argument("--exclude-owners-file", help="Optional JSON file: [\"owner\", ...] to auto-exclude by SATCAT owner")
    parser.add_argument("--satcat-file", help="Optional local SATCAT CSV for --exclude-owners-file (offline mode); omit to fetch live")
    args = parser.parse_args(argv)

    with open(args.watchlist) as f:
        watchlist = set(json.load(f))

    if args.exclude_owners_file:
        with open(args.exclude_owners_file) as f:
            owners = set(json.load(f))
        watchlist = _apply_owner_exclusions(watchlist, owners, args.satcat_file)

    object_names: dict[int, str] = {}
    if args.object_names:
        with open(args.object_names) as f:
            object_names = {int(k): v for k, v in json.load(f).items()}

    store = JsonStore(args.state)
    baseline = PerObjectBaseline.from_dict(
        store.get("baseline_history", {}), z_threshold=args.z_threshold
    )
    previous_tles: dict = store.get("previous_tles", {})
    maneuver_events: dict = store.get("maneuver_events", {})

    if args.source == "celestrak":
        try:
            records = CelesTrakClient().fetch_by_norad_ids(sorted(watchlist))
        except Exception as exc:  # noqa: BLE001 - see comment below
            # Confirmed on a real run (2026-07-04): celestrak.org timed out
            # from GitHub Actions' shared runner IP range. This is a known,
            # documented issue -- CelesTrak's usage policy firewalls IPs
            # that exceed its bandwidth limits, and GitHub Actions runners
            # share IP ranges across every workflow on GitHub, so this can
            # happen even on a well-behaved, low-frequency schedule. A
            # longer timeout or retry won't help a genuinely blocked IP, so
            # fall back to Space-Track (authenticated, not subject to the
            # same shared-IP congestion) if credentials are available.
            if os.environ.get("SPACETRACK_USER") and os.environ.get("SPACETRACK_PASS"):
                print(f"Warning: CelesTrak fetch failed ({exc}); falling back to Space-Track.")
                records = SpaceTrackClient().fetch_tles(sorted(watchlist))
            else:
                print(
                    f"CelesTrak fetch failed ({exc}) and no Space-Track credentials are set "
                    "to fall back to. Sign up for a free Space-Track account and set "
                    "SPACETRACK_USER/SPACETRACK_PASS to make this run reliably."
                )
                return 1
    elif args.source == "spacetrack":
        records = SpaceTrackClient().fetch_tles(sorted(watchlist))
    else:
        if not args.tle_file:
            parser.error("--tle-file is required when --source file")
        records = load_tles_from_file(args.tle_file)

    records = [r for r in records if r.norad_id in watchlist]
    print(f"Fetched {len(records)} TLE(s) for {len(watchlist)} watched object(s).")

    maneuver_alerts: list[ManeuverAlert] = []
    tle_ages_days: dict[int, float] = {}
    for record in records:
        norad_key = str(record.norad_id)
        after_satrec = build_satrec(record)
        tle_ages_days[record.norad_id] = tle_age_days(after_satrec)

        prev = previous_tles.get(norad_key)
        if prev is not None:
            before_satrec = Satrec.twoline2rv(prev["line1"], prev["line2"])
            if before_satrec.jdsatepoch + before_satrec.jdsatepochF < (
                after_satrec.jdsatepoch + after_satrec.jdsatepochF
            ):
                residual = compute_residual(before_satrec, after_satrec)
                # Feed the per-day rate, not raw km -- see propagate.py's
                # ACCURACY NOTE: raw km isn't comparable across objects/
                # updates with different TLE gap sizes (a Starlink updated
                # every 4h vs. an object updated weekly), which published
                # research flags as a real false-positive cause.
                verdict = baseline.evaluate(record.norad_id, residual.position_error_km_per_day)

                if verdict.is_anomalous:
                    message = format_alert(verdict, residual)
                    send_console(message)
                    if args.webhook_url:
                        send_webhook(args.webhook_url, message)

                    alert = ManeuverAlert(
                        norad_id=record.norad_id,
                        residual_km=residual.position_error_km,
                        z_score=verdict.z_score,
                        reason=verdict.reason,
                        epoch_gap_days=residual.epoch_gap_days,
                        residual_km_per_day=residual.position_error_km_per_day,
                    )
                    maneuver_alerts.append(alert)

                    events = maneuver_events.setdefault(norad_key, [])
                    events.append(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "residual_km": residual.position_error_km,
                            "residual_km_per_day": residual.position_error_km_per_day,
                            "epoch_gap_days": residual.epoch_gap_days,
                            "z_score": verdict.z_score,
                            "reason": verdict.reason,
                        }
                    )
            else:
                print(f"NORAD {record.norad_id}: no newer TLE since last run, skipping.")
        else:
            print(f"NORAD {record.norad_id}: first time seen, no baseline yet.")

        previous_tles[norad_key] = {"line1": record.line1, "line2": record.line2}

    conjunctions = _fetch_conjunctions_safely(watchlist) if args.include_socrates else []
    satnogs_healths = _fetch_satnogs_health_safely(watchlist) if args.include_satnogs else []
    crew_by_craft = _fetch_crew_safely() if args.include_crew else {}
    deep_space_probes = _fetch_deep_space_probes_safely() if args.include_deep_space else []
    volcano_alerts = _fetch_volcano_status_safely() if args.include_volcano_status else []
    # No CLI flag for this one -- gated purely by whether FIRMS_MAP_KEY is
    # set (same idea as the SPACETRACK_USER/PASS fallback above), since
    # there's nothing to configure beyond the free key itself.
    global_fire_count = _fetch_global_fire_count_safely()

    if args.include_socrates or args.include_satnogs:
        digest = generate_digest(object_names, maneuver_alerts, conjunctions, satnogs_healths, tle_ages_days)
        print("\n" + digest + "\n")
        if args.digest_out:
            with open(args.digest_out, "w") as f:
                f.write(digest)

    # Persisted so site_data_cli.py (and anything else reading state.json
    # later) has the latest SatNOGS health without needing its own live
    # fetch -- previously this was only ever printed into that run's
    # digest and then lost.
    if satnogs_healths:
        from dataclasses import asdict

        satnogs_health_state = store.get("satnogs_health", {})
        for health in satnogs_healths:
            satnogs_health_state[str(health.norad_id)] = asdict(health)
        store.set("satnogs_health", satnogs_health_state)

    # Persisted the same way -- website's collision-risk panel reads this
    # from state.json rather than needing its own live SOCRATES fetch.
    # datetime isn't JSON-serializable, so time_of_closest_approach is
    # stored as its isoformat() string.
    if conjunctions:
        from dataclasses import asdict

        store.set("conjunctions", [
            {**asdict(c), "time_of_closest_approach": c.time_of_closest_approach.isoformat()}
            for c in conjunctions
        ])

    if crew_by_craft:
        store.set("crew_by_craft", crew_by_craft)

    if deep_space_probes:
        store.set("deep_space_probes", deep_space_probes)

    if volcano_alerts:
        store.set("volcano_alerts", volcano_alerts)

    # Written whenever a real count came back, including a real 0 -- not
    # just when truthy -- so the site can tell "FIRMS_MAP_KEY isn't set up"
    # apart from "genuinely zero fires detected in the last 24h."
    if global_fire_count is not None:
        store.set("global_fire_count", global_fire_count)

    store.set("previous_tles", previous_tles)
    store.set("baseline_history", baseline.to_dict())
    store.set("maneuver_events", maneuver_events)
    store.save()

    print(f"Done. {len(maneuver_alerts)} alert(s) sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
