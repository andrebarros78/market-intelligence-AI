from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.control_selection import AutomaticControlSelector
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


def _scale(values: list[float]) -> float:
    if not values:
        return 1.0
    center = float(statistics.median(values))
    mad = float(statistics.median(abs(value - center) for value in values))
    steps = [abs(right - left) for left, right in zip(values, values[1:])]
    step = float(statistics.median(steps)) if steps else 0.0
    return max(mad, step, abs(center) * 0.02, 1e-9)


@dataclass(frozen=True, slots=True)
class CounterfactualEstimate:
    metric: str
    observed: float
    target_baseline: float
    target_scale: float
    expected: float
    gap: float
    gap_signal: float
    gap_ratio: float
    control_median_signal: float
    control_count: int
    control_entity_ids: tuple[str, ...]
    selection: dict[str, Any]
    version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "observed": self.observed,
            "target_baseline": self.target_baseline,
            "target_scale": self.target_scale,
            "counterfactual_expected": self.expected,
            "counterfactual_gap": self.gap,
            "gap_signal": self.gap_signal,
            "gap_ratio": self.gap_ratio,
            "control_median_signal": self.control_median_signal,
            "control_count": self.control_count,
            "control_entity_ids": list(self.control_entity_ids),
            "selection": self.selection,
            "estimator_version": self.version,
            "selection_uses_current_values": False,
            "estimator_uses_current_control_values": True,
            "estimator_uses_current_target_to_fit": False,
            "causal_claim": False,
        }


class OperationalCounterfactualDetector:
    name = "operational_counterfactual_v1"
    version = "operational-counterfactual@1.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        min_controls: int = 3,
        min_similarity: float = 0.70,
        max_controls: int = 8,
        min_gap_signal: float = 2.5,
        min_gap_ratio: float = 0.10,
    ) -> None:
        if min_history < 6:
            raise ValueError("min_history must be at least 6")
        if min_controls < 3:
            raise ValueError("min_controls must be at least 3")
        if min_gap_signal <= 0 or min_gap_ratio <= 0:
            raise ValueError("gap thresholds must be positive")
        self.min_history = min_history
        self.min_controls = min_controls
        self.min_gap_signal = min_gap_signal
        self.min_gap_ratio = min_gap_ratio
        self._selector = AutomaticControlSelector(
            min_history=min_history,
            min_similarity=min_similarity,
            max_controls=max_controls,
        )
