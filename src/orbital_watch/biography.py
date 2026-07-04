"""
The plain-English "satellite biography" -- one page per object instead of
piecing together SATCAT codes, Wikipedia, and McDowell's newsletter
archive by hand. Combines SATCAT metadata (who/what/when) with our own
detected maneuver history (what it's done lately).
"""
from __future__ import annotations

from orbital_watch.satcat import SatcatRecord

_OBJECT_TYPE_PLAIN = {
    "PAYLOAD": "an active or inactive spacecraft",
    "ROCKET BODY": "a spent rocket stage",
    "DEBRIS": "a piece of orbital debris",
    "UNKNOWN": "an object of unknown type",
}


def build_biography(record: SatcatRecord, maneuver_events: list[dict]) -> str:
    """`maneuver_events` are dicts as stored by cli.py's state file:
    {"timestamp": iso-string, "residual_km": float, "z_score": float,
    "reason": str} -- most recent first."""
    lines = [f"# {record.object_name} (NORAD {record.norad_id})", ""]

    what = _OBJECT_TYPE_PLAIN.get(record.object_type, record.object_type.lower())
    owner_bit = f", operated by {record.owner}" if record.owner else ""
    lines.append(f"This is {what}{owner_bit}.")

    if record.launch_date:
        site_bit = f" from {record.launch_site}" if record.launch_site else ""
        lines.append(f"Launched {record.launch_date}{site_bit}.")

    if record.decay_date:
        lines.append(f"Reentered/decayed on {record.decay_date}.")
    else:
        lines.append("Still in orbit as of the last catalog update.")

    if record.period_minutes and record.inclination_deg:
        lines.append(
            f"Orbit: {record.period_minutes:.1f}-minute period, "
            f"{record.inclination_deg:.1f} deg inclination"
            + (
                f", {record.perigee_km:.0f}-{record.apogee_km:.0f} km altitude"
                if record.perigee_km and record.apogee_km
                else ""
            )
            + "."
        )

    lines.append("")
    lines.append("## Maneuver timeline")
    if not maneuver_events:
        lines.append("No maneuvers detected yet (or not enough tracking history to tell).")
    else:
        for event in maneuver_events:
            lines.append(
                f"- **{event['timestamp']}**: {event['reason']} "
                f"(residual {event['residual_km']:.2f} km, {event['z_score']:.1f} sigma)"
            )

    return "\n".join(lines)
