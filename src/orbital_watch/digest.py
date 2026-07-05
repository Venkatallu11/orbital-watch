"""
The unified feed: automates the actual McDowell workflow (read the
catalog, notice maneuvers, notice risk, write it up in plain English) by
combining three currently-scattered free sources into one report each run
-- instead of manually checking CelesTrak SOCRATES, running your own TLE
math, and separately checking SatNOGS.
"""
from __future__ import annotations

from dataclasses import dataclass

from orbital_watch.satnogs import ObservationHealth
from orbital_watch.socrates import Conjunction


def format_tle_age(age_days: float) -> str:
    """Renders tle_age_days as a sentence, including the (real, if rare)
    case where a TLE's own epoch is later than the fetch time -- seen live
    on NORAD 25867/Chandra (2026-07-05): CelesTrak occasionally publishes
    an element set whose fit epoch is a day or two ahead of when it's
    fetched, which is a genuine catalog/clock-skew artifact, not a bug in
    tle_age_days' math. A bare negative number ("-1.8 day(s) old") reads as
    broken, so it's spelled out instead of just formatted with %.1f."""
    if age_days < 0:
        return (
            f"TLE epoch is {abs(age_days):.1f} day(s) ahead of fetch time "
            f"(catalog/clock-skew artifact, not stale data)"
        )
    flag = " -- STALE, treat any numbers above with extra caution" if age_days > 7 else ""
    return f"TLE is {age_days:.1f} day(s) old{flag}"


@dataclass
class ManeuverAlert:
    norad_id: int
    residual_km: float
    z_score: float
    reason: str
    epoch_gap_days: float | None = None
    residual_km_per_day: float | None = None


def generate_digest(
    object_names: dict[int, str],
    maneuver_alerts: list[ManeuverAlert],
    conjunctions: list[Conjunction],
    satnogs_healths: list[ObservationHealth],
    tle_ages_days: dict[int, float] | None = None,
) -> str:
    def name_for(norad_id: int) -> str:
        return object_names.get(norad_id, f"NORAD {norad_id}")

    lines = ["# Orbital Watch Digest", ""]

    lines.append("## Maneuvers detected (TLE residual analysis)")
    if not maneuver_alerts:
        lines.append("Nothing flagged this run.")
    else:
        for alert in maneuver_alerts:
            gap_bit = (
                f", {alert.residual_km_per_day:.2f} km/day over {alert.epoch_gap_days:.2f} day(s) between TLEs"
                if alert.residual_km_per_day is not None
                else ""
            )
            lines.append(
                f"- **{name_for(alert.norad_id)}**: {alert.reason} "
                f"({alert.residual_km:.2f} km residual{gap_bit}, {alert.z_score:.1f} sigma)"
            )
    lines.append("")

    # Surfaced per research into false-positive causes: SGP4/TLE accuracy
    # degrades from ~1km near epoch to 10s of km after a week, so every
    # number above deserves to be read next to how stale its input was,
    # rather than presented with a false sense of uniform precision.
    if tle_ages_days:
        lines.append("## Data freshness (how old is the TLE behind each number)")
        for norad_id in sorted(tle_ages_days):
            lines.append(f"- **{name_for(norad_id)}**: {format_tle_age(tle_ages_days[norad_id])}")
        lines.append("")

    lines.append("## Conjunction risk (CelesTrak SOCRATES, filtered to your watchlist)")
    if not conjunctions:
        lines.append("No conjunctions involving your watchlist in the current 7-day SOCRATES run.")
    else:
        for c in sorted(conjunctions, key=lambda c: c.max_probability, reverse=True):
            # Prefer our own watchlist name, but a conjunction partner that
            # ISN'T on your watchlist (e.g. random debris) still has a name
            # from SOCRATES itself -- use that instead of just "NORAD nnn".
            label_1 = object_names.get(c.norad_id_1) or c.name_1 or f"NORAD {c.norad_id_1}"
            label_2 = object_names.get(c.norad_id_2) or c.name_2 or f"NORAD {c.norad_id_2}"
            lines.append(
                f"- **{label_1}** vs **{label_2}**: "
                f"TCA {c.time_of_closest_approach.isoformat()}, "
                f"min range {c.min_range_km:.2f} km, "
                f"max probability {c.max_probability:.2e}"
            )
    lines.append("")

    lines.append("## Observation health (SatNOGS cross-check, where available)")
    if not satnogs_healths:
        lines.append("No SatNOGS-trackable objects on your watchlist, or no recent observations.")
    else:
        for health in satnogs_healths:
            flag = " -- DEGRADED" if health.is_degraded else ""
            lines.append(f"- **{name_for(health.norad_id)}**: {health.reason}{flag}")

    return "\n".join(lines)
