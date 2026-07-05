"""
SGP4-residual maneuver detection.

Core idea (established technique, see Kelecy 2007 / MDPI 2021 "Simplified
Approach to Detect Satellite Maneuvers Using TLE Data"):

Given two TLEs for the same object at times t1 < t2, propagate the *older*
TLE's model forward to t2 and compare the predicted position/velocity to
what the *newer* TLE says is actually there. If nothing but drag/perturbation
happened between t1 and t2, SGP4 propagation from the old element set should
land close to the new element set's epoch state. A large residual means the
object did something SGP4 can't explain from t1's elements alone -- i.e. it
maneuvered.

ACCURACY NOTE (added after research into reducing false positives): multiple
published studies (Kelecy 2007; the MDPI 2021 paper above) flag that
atmospheric drag in LEO causes elevated false-positive rates for this exact
technique, and that the time gap between the two TLEs matters a lot --
Starlink-class objects get new TLEs every ~4 hours, while a rarely-tracked
object might go a week between updates, and raw SGP4 propagation error grows
from ~1km near epoch to 10s of km after a week (published TLE accuracy
studies). A residual of 5km is routine for a week-old gap and alarming for a
4-hour gap. `epoch_gap_days` and `position_error_km_per_day` exist so the
baseline (see baseline.py) can compare like with like instead of raw km
across objects/updates with wildly different gap sizes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt

from sgp4.api import Satrec, jday

MINUTES_PER_DAY = 1440.0
# Floor to avoid a division blow-up for two TLEs sharing (almost) the same
# epoch -- an hour is short enough that per-day normalization stops being
# meaningful anyway, so anything under it is treated as "1 hour" of gap.
_MIN_GAP_DAYS = 1 / 24.0


@dataclass
class Residual:
    norad_id: int
    position_error_km: float
    velocity_error_km_s: float
    predicted_position_km: tuple
    actual_position_km: tuple
    epoch_gap_days: float
    position_error_km_per_day: float


def _distance(a: tuple, b: tuple) -> float:
    return sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def compute_residual(satrec_before: Satrec, satrec_after: Satrec) -> Residual:
    """Propagate `satrec_before` to `satrec_after`'s epoch and diff against
    `satrec_after`'s own state at that same epoch (its residual is ~0 by
    construction, so this isolates what `satrec_before` failed to predict).
    """
    jd = satrec_after.jdsatepoch
    fr = satrec_after.jdsatepochF

    err_code, r_pred, v_pred = satrec_before.sgp4(jd, fr)
    if err_code != 0:
        raise RuntimeError(f"SGP4 propagation error code {err_code} for NORAD {satrec_before.satnum}")

    err_code, r_actual, v_actual = satrec_after.sgp4(jd, fr)
    if err_code != 0:
        raise RuntimeError(f"SGP4 propagation error code {err_code} for NORAD {satrec_after.satnum}")

    position_error_km = _distance(r_pred, r_actual)

    epoch_gap_days = (
        (satrec_after.jdsatepoch - satrec_before.jdsatepoch)
        + (satrec_after.jdsatepochF - satrec_before.jdsatepochF)
    )
    normalizing_gap_days = max(epoch_gap_days, _MIN_GAP_DAYS)

    return Residual(
        norad_id=satrec_after.satnum,
        position_error_km=position_error_km,
        velocity_error_km_s=_distance(v_pred, v_actual),
        predicted_position_km=r_pred,
        actual_position_km=r_actual,
        epoch_gap_days=epoch_gap_days,
        position_error_km_per_day=position_error_km / normalizing_gap_days,
    )


def tle_age_days(satrec: Satrec, now: datetime | None = None) -> float:
    """How many days old this TLE's epoch is, relative to `now` (real
    current time by default, injectable for tests). Surfaced in the
    digest as a staleness/confidence signal: published studies show SGP4
    propagation error grows from ~1km near epoch to 10s of km after a
    week, so a maneuver call (or lack of one) based on a week-old TLE
    deserves less confidence than one based on a fresh one -- showing the
    reader the age lets them judge that themselves instead of a bare
    number pretending to be equally precise regardless of staleness."""
    if now is None:
        now = datetime.now(timezone.utc)
    now_jd, now_fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second + now.microsecond / 1e6)
    return (now_jd - satrec.jdsatepoch) + (now_fr - satrec.jdsatepochF)
