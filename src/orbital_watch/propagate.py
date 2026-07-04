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
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from sgp4.api import Satrec


@dataclass
class Residual:
    norad_id: int
    position_error_km: float
    velocity_error_km_s: float
    predicted_position_km: tuple
    actual_position_km: tuple


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

    return Residual(
        norad_id=satrec_after.satnum,
        position_error_km=_distance(r_pred, r_actual),
        velocity_error_km_s=_distance(v_pred, v_actual),
        predicted_position_km=r_pred,
        actual_position_km=r_actual,
    )
