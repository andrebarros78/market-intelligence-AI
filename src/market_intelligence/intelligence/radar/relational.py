from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.control_selection import (
    AutomaticControlSelector,
    ControlSelection,
    SelectedControl,
)
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _scale(values: list[float], *, floor_ratio: float = 0.02) -> float:
    if not values:
        return 1.0
    center = statistics.median(values)
    step = (
        statistics.median(abs(r - l) for l, r in zip(values, values[1:]))
        if len(values) > 1
        else 0.0
    )
    floor = max(abs(center) * floor_ratio, 1e-9)
    return max(_mad(values), step, floor)


def _standardized_deviation(current: float, history: list[float]) -> tuple[float, float, float]:
    center = statistics.median(history)
    scale = _scale(history)
    return (current - center) / scale, center, scale


def _relative_change(current: float, baseline: float) -> float | None:
    if abs(baseline) < 1e-12:
        return None
    return (current - baseline) / abs(baseline)


class ControlObservation(BaseModel):
    """Legacy explicit control contract preserved for backward compatibility."""

    entity_id: str
    similarity: float = Field(ge=0.0, le=1.0)
    metrics: dict[str, float]
    history: dict[str, list[float]] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _ControlSignal:
    entity_id: str
    similarity: float
    signal: float
    baseline: float
    current: float
    relative_change: float | None
    source: str


@dataclass(frozen=True, slots=True)
class _RelationalCandidate:
    metric: str
    score: float
    magnitude: float
    attributes: dict[str, Any]


class RelationalControlDetector:
    name = "relational_control_v1"
    version = "relational-control@2.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        min_controls: int = 3,
        min_similarity: float = 0.70,
        min_target_signal: float = 2.5,
        divergence_threshold: float = 3.0,
        max_control_spread: float = 1.5,
        max_controls: int = 8,
    ) -> None:
        if min_history < 6:
            raise ValueError("min_history must be at least 6")
        if min_controls < 3:
            raise ValueError("min_controls must be at least 3")
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between 0 and 1")
        if min_target_signal <= 0 or divergence_threshold <= 0 or max_control_spread <= 0:
            raise ValueError("thresholds must be positive")
        if max_controls < min_controls:
            raise ValueError("max_controls cannot be smaller than min_controls")
        self.min_history = min_history
        self.min_controls = min_controls
        self.min_similarity = min_similarity
        self.min_target_signal = min_target_signal
        self.divergence_threshold = divergence_threshold
        self.max_control_spread = max_control_spread
        self.max_controls = max_controls
        self._selector = AutomaticControlSelector(
            min_history=min_history,
            min_similarity=min_similarity,
            max_controls=max_controls,
        )

    @staticmethod
    def _score(signal: float, threshold: float) -> float:
        excess = (signal - threshold) / max(threshold, 1e-9)
        return min(1.0, 0.60 + 0.40 * max(0.0, excess))

    def _legacy_controls(self, observation: RadarObservation) -> list[SelectedControl]:
        raw = observation.context.get("controls", [])
        if not isinstance(raw, list):
            return []
        controls: list[SelectedControl] = []
        for item in raw:
            try:
                control = ControlObservation.model_validate(item)
            except ValidationError:
                continue
            if control.entity_id == observation.entity_id or control.similarity < self.min_similarity:
                continue
            controls.append(
                SelectedControl(
                    entity_id=control.entity_id,
                    similarity=control.similarity,
                    metrics=control.metrics,
                    history=control.history,
                    attributes=control.attributes,
                    source="legacy",
                )
            )
        return controls

    def _controls_for_metric(
        self,
        observation: RadarObservation,
        metric: str,
    ) -> tuple[list[SelectedControl], dict[str, Any]]:
        legacy = self._legacy_controls(observation)
        automatic: ControlSelection = self._selector.select(observation, metric)
        by_id: dict[str, SelectedControl] = {}
        for control in legacy:
            by_id[control.entity_id] = control
        for control in automatic.controls:
            by_id.setdefault(control.entity_id, control)
        selected = sorted(
            by_id.values(),
            key=lambda item: (-item.similarity, item.entity_id),
        )[: self.max_controls]
        sources = {"legacy": 0, "automatic": 0}
        for control in selected:
            sources[control.source] = sources.get(control.source, 0) + 1
        if legacy and automatic.candidate_count:
            mode = "hybrid"
        elif automatic.candidate_count:
            mode = "automatic"
        else:
            mode = "legacy"
        audit = automatic.audit()
        audit.update(
            {
                "mode": mode,
                "legacy_input_count": len(legacy),
                "final_selected_count": len(selected),
                "final_selected_entity_ids": [item.entity_id for item in selected],
                "final_selected_sources": sources,
                "min_similarity": self.min_similarity,
                "min_controls": self.min_controls,
                "min_history": self.min_history,
                "max_controls": self.max_controls,
                "selection_uses_current_values": False,
            }
        )
        return selected, audit

    def _evaluate_metric(
        self,
        observation: RadarObservation,
        metric: str,
    ) -> _RelationalCandidate | None:
        target_history = observation.history.get(metric, [])
        if len(target_history) < self.min_history:
            return None
        target_signal, target_baseline, target_scale = _standardized_deviation(
            observation.metrics[metric], target_history
        )
        if abs(target_signal) < self.min_target_signal:
            return None
        controls, selection_audit = self._controls_for_metric(observation, metric)
        control_signals: list[_ControlSignal] = []
        for control in controls:
            history = control.history.get(metric, [])
            if metric not in control.metrics or len(history) < self.min_history:
                continue
            signal, baseline, _ = _standardized_deviation(control.metrics[metric], history)
            control_signals.append(
                _ControlSignal(
                    control.entity_id,
                    control.similarity,
                    signal,
                    baseline,
                    control.metrics[metric],
                    _relative_change(control.metrics[metric], baseline),
                    control.source,
                )
            )
        if len(control_signals) < self.min_controls:
            return None
        signals = [item.signal for item in control_signals]
        control_median = statistics.median(signals)
        control_spread = _mad(signals)
        if control_spread > self.max_control_spread:
            return None
        divergence = abs(target_signal - control_median)
        if divergence < self.divergence_threshold:
            return None
        consistent_count = sum(
            1 for signal in signals if abs(signal - control_median) <= self.max_control_spread
        )
        consistency = consistent_count / len(signals)
        if consistency < 2 / 3:
            return None
        target_current = observation.metrics[metric]
        target_relative_change = _relative_change(target_current, target_baseline)
        control_relative = [
            item.relative_change for item in control_signals if item.relative_change is not None
        ]
        control_relative_median = statistics.median(control_relative) if control_relative else None
        magnitude = min(abs(target_signal), divergence)
        comparison = {
            "metric": metric,
            "target_entity_id": observation.entity_id,
            "target_baseline": target_baseline,
            "target_current": target_current,
            "target_standardized_deviation": target_signal,
            "target_relative_change": target_relative_change,
            "control_count": len(control_signals),
            "control_entity_ids": [item.entity_id for item in control_signals],
            "control_sources": {item.entity_id: item.source for item in control_signals},
            "control_median_standardized_deviation": control_median,
            "control_median_relative_change": control_relative_median,
            "control_signal_spread": control_spread,
            "control_consistency": consistency,
            "median_similarity": statistics.median(
                [item.similarity for item in control_signals]
            ),
            "divergence": divergence,
            "selection": selection_audit,
        }
        return _RelationalCandidate(
            metric,
            self._score(
                magnitude,
                min(self.min_target_signal, self.divergence_threshold),
            ),
            magnitude,
            {
                "pattern": "control_group_divergence",
                "control_comparison": comparison,
                "cause_status": "unknown_not_inferred",
                "detector_version": self.version,
                "target_history_scale": target_scale,
            },
        )

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        best: _RelationalCandidate | None = None
        for metric in sorted(observation.metrics):
            candidate = self._evaluate_metric(observation, metric)
            if candidate is not None and (
                best is None
                or (candidate.score, candidate.magnitude) > (best.score, best.magnitude)
            ):
                best = candidate
        if best is None:
            return None
        return DetectorResult(
            detector=self.name,
            score=best.score,
            level=EvidenceLevel.FACT,
            summary=(
                f"Observed divergence for {best.metric} against comparable control group"
            ),
            attributes=best.attributes,
        )
