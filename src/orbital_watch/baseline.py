"""
Per-object rolling baseline, so an object that normally maneuvers often
(e.g. a Starlink satellite doing routine station-keeping) doesn't spam
alerts, while a normally-quiet object that suddenly moves does.

Instead of one global "residual > X km = alert" threshold, each NORAD ID
gets its own trailing window of past residuals. A new residual is flagged
only if it's an outlier *relative to that object's own recent history*.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class BaselineVerdict:
    norad_id: int
    residual_km: float
    z_score: float | None
    is_anomalous: bool
    reason: str


class PerObjectBaseline:
    def __init__(self, window_size: int = 10, z_threshold: float = 3.0, min_samples: int = 4):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self._history: dict[int, deque] = {}

    def evaluate(self, norad_id: int, residual_km: float) -> BaselineVerdict:
        history = self._history.setdefault(norad_id, deque(maxlen=self.window_size))

        if len(history) < self.min_samples:
            verdict = BaselineVerdict(
                norad_id=norad_id,
                residual_km=residual_km,
                z_score=None,
                is_anomalous=False,
                reason=f"building baseline ({len(history)}/{self.min_samples} samples)",
            )
            history.append(residual_km)
            return verdict

        mu = mean(history)
        sigma = pstdev(history) or 1e-6  # avoid div-by-zero for a perfectly flat history
        z = (residual_km - mu) / sigma

        is_anomalous = z >= self.z_threshold
        reason = (
            f"residual {residual_km:.3f} km is {z:.1f} sigma above this object's "
            f"recent baseline ({mu:.3f} km avg)"
            if is_anomalous
            else "within this object's normal drift pattern"
        )

        history.append(residual_km)
        return BaselineVerdict(
            norad_id=norad_id,
            residual_km=residual_km,
            z_score=z,
            is_anomalous=is_anomalous,
            reason=reason,
        )

    def to_dict(self) -> dict:
        """For persisting between scheduled runs (see store.py)."""
        return {str(k): list(v) for k, v in self._history.items()}

    @classmethod
    def from_dict(cls, data: dict, **kwargs) -> "PerObjectBaseline":
        instance = cls(**kwargs)
        for norad_id_str, residuals in data.items():
            history = deque(residuals, maxlen=instance.window_size)
            instance._history[int(norad_id_str)] = history
        return instance
