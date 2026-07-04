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


@dataclass
class ManeuverAlert:
    norad_id: int
    residual_km: float
    z_score: float
    reason: str


def generate_digest(
    object_names: dict[int, str],
    maneuver_alerts: list[ManeuverAlert],
    conjunctions: list[Conjunction],
    satnogs_healths: list[ObservationHealth],
) -> str:
    def name_for(norad_id: int) -> str:
        return object_names.get(norad_id, f"NORAD {norad_id}")

    lines = ["# Orbital Watch Digest", ""]

    lines.append("## Maneuvers detected (TLE residual analysis)")
    if not maneuver_alerts:
        lines.append("Nothing flagged this run.")
    else:
        for alert in maneuver_alerts:
            lines.append(
                f"- **{name_for(alert.norad_id)}**: {alert.reason} "
                f"({alert.residual_km:.2f} km residual, {alert.z_score:.1f} sigma)"
            )
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
