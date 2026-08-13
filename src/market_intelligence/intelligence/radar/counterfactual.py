from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.control_selection import (
    AutomaticControlSelector,
    SelectedControl,
)
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
class _ControlSignal:
    entity_id: str
    similarity: float
    baseline: float
    current: float
    scale: float
    signal: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "similarity": self.similarity,
            "baseline": self.baseline,
            "current": self.current,
            "scale": self.scale,
            "signal": self.signal,
        }


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
    control_signal_spread: float
    control_consistency: float
    control_count: int
    control_entity_ids: tuple[str, ...]
    control_details: tuple[dict[str, Any], ...]
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
            "control_signal_spread": self.control_signal_spread,
            "control_consistency": self.control_consistency,
            "control_count": self.control_count,
            "control_entity_ids": list(self.control_entity_ids),
            "control_details": list(self.control_details),
            "selection": self.selection,
            "estimator_version": self.version,
            "counterfactual_kind": "operational_not_causal",
            "selection_uses_current_values": False,
            "estimator_uses_current_control_values": True,
            "estimator_uses_current_target_to_fit": False,
            "causal_claim": False,
        }


class OperationalCounterfactualDetector:
    """Estimate a no-anomaly operational path from comparable controls.

    This detector is deliberately non-causal. Controls are selected from historical
    similarity only. Their current movement is then projected into the target's
    historical scale to estimate what the target would operationally be expected to
    do if it followed the qualified control group.
    """

    name = "operational_counterfactual_v1"
    version = "operational-counterfactual@1.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        min_controls: int = 3,
        min_similarity: float = 0.70,
        max_controls: int = 8,
        max_control_spread: float = 1.5,
        min_control_consistency: float = 2 / 3,
        min_gap_signal: float = 2.5,
        min_gap_ratio: float = 0.10,
    ) -> None:
        if min_history < 6:
            raise ValueError("min_history must be at least 6")
        if min_controls < 3:
            raise ValueError("min_controls must be at least 3")
        if max_controls < min_controls:
            raise ValueError("max_controls cannot be smaller than min_controls")
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between 0 and 1")
        if max_control_spread <= 0:
            raise ValueError("max_control_spread must be positive")
        if not 0.5 <= min_control_consistency <= 1.0:
            raise ValueError("min_control_consistency must be in [0.5, 1.0]")
        if min_gap_signal <= 0 or min_gap_ratio <= 0:
            raise ValueError("gap thresholds must be positive")
        self.min_history = min_history
        self.min_controls = min_controls
        self.max_control_spread = max_control_spread
        self.min_control_consistency = min_control_consistency
        self.min_gap_signal = min_gap_signal
        self.min_gap_ratio = min_gap_ratio
        self._selector = AutomaticControlSelector(
            min_history=min_history,
            min_similarity=min_similarity,
            max_controls=max_controls,
        )

    @staticmethod
    def _signal(control: SelectedControl, metric: str) -> _ControlSignal | None:
        history = control.history.get(metric, [])
        if metric not in control.metrics or not history:
            return None
        values = [float(value) for value in history]
        baseline = float(statistics.median(values))
        scale = _scale(values)
        current = float(control.metrics[metric])
        return _ControlSignal(
            entity_id=control.entity_id,
            similarity=control.similarity,
            baseline=baseline,
            current=current,
            scale=scale,
            signal=(current - baseline) / scale,
        )

    def estimate(self, observation: RadarObservation, metric: str) -> CounterfactualEstimate | None:
        if metric not in observation.metrics:
            return None
        target_history = observation.history.get(metric, [])
        if len(target_history) < self.min_history:
            return None
        selection = self._selector.select(observation, metric)
        signals = [
            signal
            for control in selection.controls
            if (signal := self._signal(control, metric)) is not None
            and len(control.history.get(metric, [])) >= self.min_history
        ]
        if len(signals) < self.min_controls:
            return None

        raw_signals = [item.signal for item in signals]
        control_median_signal = float(statistics.median(raw_signals))
        deviations = [abs(value - control_median_signal) for value in raw_signals]
        control_signal_spread = float(statistics.median(deviations))
        if control_signal_spread > self.max_control_spread:
            return None
        consistent = sum(
            1
            for value in raw_signals
            if abs(value - control_median_signal) <= self.max_control_spread
        )
        control_consistency = consistent / len(raw_signals)
        if control_consistency < self.min_control_consistency:
            return None

        target_values = [float(value) for value in target_history]
        target_baseline = float(statistics.median(target_values))
        target_scale = _scale(target_values)
        expected = target_baseline + control_median_signal * target_scale
        observed = float(observation.metrics[metric])
        gap = observed - expected
        gap_signal = gap / target_scale
        denominator = max(abs(expected), abs(target_baseline), target_scale, 1e-9)
        gap_ratio = abs(gap) / denominator
        if abs(gap_signal) < self.min_gap_signal or gap_ratio < self.min_gap_ratio:
            return None

        audit = selection.audit()
        audit.update(
            {
                "min_controls": self.min_controls,
                "min_history": self.min_history,
                "max_control_spread": self.max_control_spread,
                "min_control_consistency": self.min_control_consistency,
                "selection_uses_current_values": False,
            }
        )
        return CounterfactualEstimate(
            metric=metric,
            observed=observed,
            target_baseline=target_baseline,
            target_scale=target_scale,
            expected=expected,
            gap=gap,
            gap_signal=gap_signal,
            gap_ratio=gap_ratio,
            control_median_signal=control_median_signal,
            control_signal_spread=control_signal_spread,
            control_consistency=control_consistency,
            control_count=len(signals),
            control_entity_ids=tuple(item.entity_id for item in signals),
            control_details=tuple(item.as_dict() for item in signals),
            selection=audit,
            version=self.version,
        )

    def _score(self, estimate: CounterfactualEstimate) -> float:
        signal_strength = min(1.0, abs(estimate.gap_signal) / (self.min_gap_signal * 2.0))
        ratio_strength = min(1.0, estimate.gap_ratio / (self.min_gap_ratio * 2.0))
        return min(
            0.90,
            0.60
            + 0.14 * signal_strength
            + 0.10 * ratio_strength
            + 0.06 * estimate.control_consistency,
        )

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        best: CounterfactualEstimate | None = None
        for metric in sorted(observation.metrics):
            estimate = self.estimate(observation, metric)
            if estimate is None:
                continue
            if best is None or (
                abs(estimate.gap_signal), estimate.gap_ratio, estimate.metric
            ) > (
                abs(best.gap_signal), best.gap_ratio, best.metric
            ):
                best = estimate
        if best is None:
            return None
        analysis = best.as_dict()
        return DetectorResult(
            detector=self.name,
            score=self._score(best),
            level=EvidenceLevel.INFERENCE,
            summary=(
                f"Operational counterfactual for {best.metric} expected {best.expected:.6g}; "
                f"observed {best.observed:.6g}; gap {best.gap:.6g}; no causal claim"
            ),
            attributes={
                "pattern": "operational_counterfactual_divergence",
                "metric": best.metric,
                "counterfactual_analysis": analysis,
                "counterfactual_expected": best.expected,
                "counterfactual_gap": best.gap,
                "control_entity_ids": list(best.control_entity_ids),
                "control_count": best.control_count,
                "control_consistency": best.control_consistency,
                "cause_status": "unknown_not_inferred",
                "investigation_required": True,
                "counterfactual_kind": "operational_not_causal",
                "causal_claim": False,
                "fit_uses_current_target": False,
                "detector_version": self.version,
            },
        )
