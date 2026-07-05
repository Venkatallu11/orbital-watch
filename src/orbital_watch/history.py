"""
Reconstructs a satellite's history over time from git's OWN commit history
of state.json, instead of needing a separate always-growing log file.

Every scheduled run already commits state.json back to the repo (see
cli.py's final "Commit updated state and digest" step) -- this just walks
those commits with `git show <commit>:state.json` and pulls out one
object's data at each point in time. No schema change, no new file to
maintain: the history was already sitting there, one commit per hour.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class HistoryPoint:
    commit_time: datetime
    commit_hash: str
    latest_residual_km_per_day: float | None
    cumulative_maneuver_count: int
    new_maneuver_events: list[dict] = field(default_factory=list)


def _run_git(repo_path: str, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def list_commits(repo_path: str, file_path: str) -> list[tuple[str, datetime]]:
    """Chronological (oldest first) (commit_hash, commit_time) for every
    commit that touched `file_path`. `--follow` survives the file having
    been renamed/moved."""
    output = _run_git(repo_path, ["log", "--follow", "--format=%H|%aI", "--", file_path])
    commits = []
    for line in reversed(output.strip().splitlines()):
        if not line:
            continue
        commit_hash, iso_time = line.split("|", 1)
        commits.append((commit_hash, datetime.fromisoformat(iso_time)))
    return commits


def get_file_at_commit(repo_path: str, commit_hash: str, file_path: str) -> dict:
    output = _run_git(repo_path, ["show", f"{commit_hash}:{file_path}"])
    return json.loads(output)


def build_satellite_history(repo_path: str, norad_id: int, state_file: str = "state.json") -> list[HistoryPoint]:
    """Walks every commit that touched `state_file`, oldest first, and
    extracts this object's rolling-baseline residual (as it stood at that
    commit) and any maneuver events newly recorded since the previous
    commit. Skips commits where the file doesn't parse or doesn't exist
    yet (e.g. the very first few commits in the repo's history, before
    orbital-watch existed) rather than aborting the whole walk."""
    commits = list_commits(repo_path, state_file)
    points = []
    previous_event_count = 0
    norad_key = str(norad_id)

    for commit_hash, commit_time in commits:
        try:
            state = get_file_at_commit(repo_path, commit_hash, state_file)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue

        residual_history = state.get("baseline_history", {}).get(norad_key, [])
        latest_residual = residual_history[-1] if residual_history else None

        events = state.get("maneuver_events", {}).get(norad_key, [])
        new_events = events[previous_event_count:]
        previous_event_count = len(events)

        points.append(
            HistoryPoint(
                commit_time=commit_time,
                commit_hash=commit_hash,
                latest_residual_km_per_day=latest_residual,
                cumulative_maneuver_count=len(events),
                new_maneuver_events=new_events,
            )
        )
    return points


def build_all_satellites_history(
    repo_path: str, norad_ids: list[int], state_file: str = "state.json", max_points: int = 200
) -> dict[int, list[HistoryPoint]]:
    """Same walk as build_satellite_history, but extracts every requested
    object's history in ONE pass over the commits instead of calling
    build_satellite_history once per satellite (which would re-run `git
    show` on every commit once per satellite -- fine for one object on
    demand, wasteful for precomputing all ~50 objects' history every
    scheduled run). `max_points` keeps only the most recent N points per
    object, since this runs hourly and the commit list only grows."""
    commits = list_commits(repo_path, state_file)
    norad_keys = [str(n) for n in norad_ids]
    points_by_id: dict[int, list[HistoryPoint]] = {n: [] for n in norad_ids}
    previous_event_counts: dict[str, int] = {k: 0 for k in norad_keys}

    for commit_hash, commit_time in commits:
        try:
            state = get_file_at_commit(repo_path, commit_hash, state_file)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue

        baseline_history = state.get("baseline_history", {})
        maneuver_events = state.get("maneuver_events", {})

        for norad_id, norad_key in zip(norad_ids, norad_keys):
            residual_history = baseline_history.get(norad_key, [])
            latest_residual = residual_history[-1] if residual_history else None

            events = maneuver_events.get(norad_key, [])
            new_events = events[previous_event_counts[norad_key]:]
            previous_event_counts[norad_key] = len(events)

            points_by_id[norad_id].append(
                HistoryPoint(
                    commit_time=commit_time,
                    commit_hash=commit_hash,
                    latest_residual_km_per_day=latest_residual,
                    cumulative_maneuver_count=len(events),
                    new_maneuver_events=new_events,
                )
            )

    if max_points:
        points_by_id = {n: pts[-max_points:] for n, pts in points_by_id.items()}
    return points_by_id


def format_history(object_name: str, points: list[HistoryPoint]) -> str:
    lines = [f"# History for {object_name}", ""]

    if not points:
        lines.append("No history found -- has this object been watched yet?")
        return "\n".join(lines)

    for point in points:
        residual_bit = (
            f"residual {point.latest_residual_km_per_day:.2f} km/day"
            if point.latest_residual_km_per_day is not None
            else "no residual yet (first time seen at this point)"
        )
        line = f"- **{point.commit_time.isoformat()}** (`{point.commit_hash[:8]}`): {residual_bit}"
        for event in point.new_maneuver_events:
            line += f"\n  - **MANEUVER**: {event['reason']}"
        lines.append(line)

    return "\n".join(lines)
