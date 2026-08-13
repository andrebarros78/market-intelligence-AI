from __future__ import annotations

import itertools
import statistics
from dataclasses import dataclass

from market_intelligence.core.contracts import EvidenceLevel
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
    step = statistics.median(abs(r - l) for l, r in zip(values, values[1:])) if len(values) > 1 else 0.0
    floor = max(abs(center) * floor_ratio, 1e-9)
    return max(_mad(values), step, floor)


def _theil_sen(x_values: list[float], y_values: list[float]) -> tuple[float, float] | None:
    slopes: list[float] = []
    for left, right in itertools.combinations(range(len(x_values)), 2):
        delta_x = x_values[right] - x_values[left]
        if delta_x == 0:
            continue
        slopes.append((y_values[right] - y_values[left]) / delta_x)
    if not slopes:
        return None
    slope = statistics.median(slopes)
    intercept = statistics.median(y - slope * x for x, y in zip(x_values, y_values))
    return slope, intercept


@dataclass(frozen=True, slots=True)
class _RelationshipCandidate:
    x_metric: str
    y_metric: str
    score: float
    magnitude: float
    attributes: dict[str, object]


class MultivariateRelationshipDetector:
    """Detects rupture of historically stable relationships between metrics."""

    name = "multivariate_relationship_v1"
    version = "multivariate-relationship@1.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        min_fit_quality: float = 0.70,
        min_slope_signal: float = 0.35,
        residual_threshold: float = 4.0,
        max_extrapolation_scale: float = 1.5,
        floor_ratio: float = 0.02,
    ) -> None:
        if min_history < 6:
            raise ValueError("min_history must be at least 6")
        if not 0.0 < min_fit_quality < 1.0:
            raise ValueError("min_fit_quality must be between 0 and 1")
        if min_slope_signal <= 0 or residual_threshold <= 0:
            raise ValueError("thresholds must be positive")
        if max_extrapolation_scale < 0:
            raise ValueError("max_extrapolation_scale cannot be negative")
        self.min_history = min_history
        self.min_fit_quality = min_fit_quality
        self.min_slope_signal = min_slope_signal
        self.residual_threshold = residual_threshold
        self.max_extrapolation_scale = max_extrapolation_scale
        self.floor_ratio = floor_ratio

    @staticmethod
    def _score(signal: float, threshold: float) -> float:
        excess = (signal - threshold) / max(threshold, 1e-9)
        return min(1.0, 0.60 + 0.40 * max(0.0, excess))

    def _directed_relationship(
        self,
        *,
        x_metric: str,
        y_metric: str,
        x_history: list[float],
        y_history: list[float],
        x_current: float,
        y_current: float,
    ) -> _RelationshipCandidate | None:
        aligned = min(len(x_history), len(y_history))
        if aligned < self.min_history:
            return None
        x_values = x_history[-aligned:]
        y_values = y_history[-aligned:]
        if len(set(x_values)) < 4 or len(set(y_values)) < 4:
            return None
        fit = _theil_sen(x_values, y_values)
        if fit is None:
            return None
        slope, intercept = fit
        x_scale = _scale(x_values, floor_ratio=self.floor_ratio)
        y_scale = _scale(y_values, floor_ratio=self.floor_ratio)
        slope_signal = abs(slope) * x_scale / y_scale
        if slope_signal < self.min_slope_signal:
            return None
        fitted = [intercept + slope * value for value in x_values]
        residuals = [actual - expected for actual, expected in zip(y_values, fitted)]
        residual_center = statistics.median(residuals)
        residual_scale = _scale(residuals, floor_ratio=self.floor_ratio)
        fit_quality = max(0.0, 1.0 - residual_scale / y_scale)
        if fit_quality < self.min_fit_quality:
            return None
        lower = min(x_values) - self.max_extrapolation_scale * x_scale
        upper = max(x_values) + self.max_extrapolation_scale * x_scale
        if not lower <= x_current <= upper:
            return None
        expected = intercept + slope * x_current + residual_center
        residual = y_current - expected
        residual_signal = abs(residual) / residual_scale
        if residual_signal < self.residual_threshold:
            return None
        return _RelationshipCandidate(
            x_metric=x_metric,
            y_metric=y_metric,
            score=self._score(residual_signal, self.residual_threshold),
            magnitude=residual_signal,
            attributes={
                "pattern": "relationship_break",
                "x_metric": x_metric,
                "y_metric": y_metric,
                "history_points": aligned,
                "historical_slope": slope,
                "historical_intercept": intercept,
                "fit_quality": fit_quality,
                "slope_signal": slope_signal,
                "expected_y": expected,
                "observed_x": x_current,
                "observed_y": y_current,
                "residual": residual,
                "residual_signal": residual_signal,
                "historical_residual_scale": residual_scale,
                "cause_status": "unknown_not_inferred",
                "detector_version": self.version,
            },
        )

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        metrics = sorted(
            metric for metric in observation.metrics
            if len(observation.history.get(metric, [])) >= self.min_history
        )
        if len(metrics) < 2:
            return None
        best: _RelationshipCandidate | None = None
        for first, second in itertools.combinations(metrics, 2):
            first_history = observation.history.get(first, [])
            second_history = observation.history.get(second, [])
            candidates = (
                self._directed_relationship(
                    x_metric=first, y_metric=second,
                    x_history=first_history, y_history=second_history,
                    x_current=observation.metrics[first], y_current=observation.metrics[second],
                ),
                self._directed_relationship(
                    x_metric=second, y_metric=first,
                    x_history=second_history, y_history=first_history,
                    x_current=observation.metrics[second], y_current=observation.metrics[first],
                ),
            )
            for candidate in candidates:
                if candidate is None:
                    continue
                if best is None or (candidate.score, candidate.magnitude) > (best.score, best.magnitude):
                    best = candidate
        if best is None:
            return None
        return DetectorResult(
            detector=self.name,
            score=best.score,
            level=EvidenceLevel.FACT,
            summary=f"Observed multivariate relationship break between {best.x_metric} and {best.y_metric}",
            attributes=best.attributes,
        )
