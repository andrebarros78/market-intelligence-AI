from __future__ import annotations

import statistics
from dataclasses import dataclass

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _median_step(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.median(abs(right - left) for left, right in zip(values, values[1:]))


def _scale(values: list[float], *, floor_ratio: float) -> float:
    center = statistics.median(values) if values else 0.0
    floor = max(abs(center) * floor_ratio, 1e-9)
    return max(_mad(values), _median_step(values), floor)


def _slope(values: list[float]) -> float:
    slopes: list[float] = []
    for left_index, left in enumerate(values[:-1]):
        for right_index in range(left_index + 1, len(values)):
            slopes.append((values[right_index] - left) / (right_index - left_index))
    return statistics.median(slopes) if slopes else 0.0


def _direction(value: float) -> str:
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


@dataclass(frozen=True, slots=True)
class _RegimeCandidate:
    metric: str
    pattern: str
    score: float
    magnitude: float
    attributes: dict[str, object]


class RegimeChangeDetector:
    """Detects persistent structural changes between adjacent robust windows.

    The detector reports an observed structural change only. It deliberately
    does not infer marketplace causality or seasonality.
    """

    name = "regime_change_v1"
    version = "regime-change@1.0.0"

    def __init__(
        self,
        *,
        window: int = 6,
        level_effect_threshold: float = 3.0,
        min_relative_level_change: float = 0.15,
        volatility_ratio_threshold: float = 2.5,
        trend_signal_threshold: float = 2.5,
        min_trend_relative_change: float = 0.15,
        persistence_threshold: float = 0.80,
        floor_ratio: float = 0.02,
    ) -> None:
        if window < 5:
            raise ValueError("window must be at least 5")
        if level_effect_threshold <= 0:
            raise ValueError("level_effect_threshold must be positive")
        if volatility_ratio_threshold <= 1:
            raise ValueError("volatility_ratio_threshold must exceed 1")
        if trend_signal_threshold <= 0:
            raise ValueError("trend_signal_threshold must be positive")
        if not 0.5 <= persistence_threshold <= 1.0:
            raise ValueError("persistence_threshold must be between 0.5 and 1")
        self.window = window
        self.level_effect_threshold = level_effect_threshold
        self.min_relative_level_change = min_relative_level_change
        self.volatility_ratio_threshold = volatility_ratio_threshold
        self.trend_signal_threshold = trend_signal_threshold
        self.min_trend_relative_change = min_trend_relative_change
        self.persistence_threshold = persistence_threshold
        self.floor_ratio = floor_ratio

    @staticmethod
    def _score(signal: float, threshold: float) -> float:
        if signal < threshold:
            return 0.0
        excess = (signal - threshold) / max(threshold, 1e-9)
        return min(1.0, 0.60 + 0.40 * excess)

    def _trend_change(
        self, metric: str, baseline: list[float], recent: list[float]
    ) -> _RegimeCandidate | None:
        baseline_scale = _scale(baseline, floor_ratio=self.floor_ratio)
        baseline_slope = _slope(baseline)
        recent_slope = _slope(recent)
        slope_delta = recent_slope - baseline_slope
        recent_signal = abs(recent_slope) / baseline_scale
        change_signal = abs(slope_delta) / baseline_scale
        steps = [right - left for left, right in zip(recent, recent[1:])]
        if recent_slope == 0:
            return None
        agreeing = sum(1 for step in steps if step * recent_slope > 0)
        persistence = agreeing / len(steps)
        total_change = recent[-1] - recent[0]
        relative_change = abs(total_change) / max(abs(recent[0]), baseline_scale)
        signal = min(recent_signal, change_signal)
        if (
            signal < self.trend_signal_threshold
            or persistence < self.persistence_threshold
            or relative_change < self.min_trend_relative_change
        ):
            return None
        return _RegimeCandidate(
            metric=metric,
            pattern="trend_regime_shift",
            score=self._score(signal, self.trend_signal_threshold),
            magnitude=signal,
            attributes={
                "metric": metric,
                "pattern": "trend_regime_shift",
                "direction": _direction(recent_slope),
                "baseline_window": baseline,
                "recent_window": recent,
                "baseline_slope": baseline_slope,
                "recent_slope": recent_slope,
                "slope_change_signal": change_signal,
                "recent_slope_signal": recent_signal,
                "persistence": persistence,
                "relative_change": relative_change,
                "cause_status": "unknown_not_inferred",
                "detector_version": self.version,
            },
        )

    def _level_change(
        self, metric: str, baseline: list[float], recent: list[float]
    ) -> _RegimeCandidate | None:
        baseline_median = statistics.median(baseline)
        recent_median = statistics.median(recent)
        shift = recent_median - baseline_median
        baseline_scale = _scale(baseline, floor_ratio=self.floor_ratio)
        effect = abs(shift) / baseline_scale
        relative_change = abs(shift) / max(abs(baseline_median), baseline_scale)
        if shift == 0:
            return None
        agreeing = sum(1 for value in recent if (value - baseline_median) * shift > 0)
        persistence = agreeing / len(recent)
        if (
            effect < self.level_effect_threshold
            or relative_change < self.min_relative_level_change
            or persistence < self.persistence_threshold
        ):
            return None
        return _RegimeCandidate(
            metric=metric,
            pattern="level_regime_shift",
            score=self._score(effect, self.level_effect_threshold),
            magnitude=effect,
            attributes={
                "metric": metric,
                "pattern": "level_regime_shift",
                "direction": _direction(shift),
                "baseline_window": baseline,
                "recent_window": recent,
                "baseline_median": baseline_median,
                "recent_median": recent_median,
                "baseline_scale": baseline_scale,
                "effect_size": effect,
                "relative_change": relative_change,
                "persistence": persistence,
                "cause_status": "unknown_not_inferred",
                "detector_version": self.version,
            },
        )

    def _volatility_change(
        self, metric: str, baseline: list[float], recent: list[float]
    ) -> _RegimeCandidate | None:
        baseline_scale = _scale(baseline, floor_ratio=self.floor_ratio)
        recent_scale = _scale(recent, floor_ratio=self.floor_ratio)
        ratio = max(recent_scale / baseline_scale, baseline_scale / recent_scale)
        if ratio < self.volatility_ratio_threshold:
            return None
        direction = "up" if recent_scale > baseline_scale else "down"
        recent_center = statistics.median(recent)
        dispersed = sum(
            1 for value in recent if abs(value - recent_center) >= baseline_scale
        ) / len(recent)
        if direction == "up" and dispersed < 0.50:
            return None
        return _RegimeCandidate(
            metric=metric,
            pattern="volatility_regime_shift",
            score=self._score(ratio, self.volatility_ratio_threshold),
            magnitude=ratio,
            attributes={
                "metric": metric,
                "pattern": "volatility_regime_shift",
                "direction": direction,
                "baseline_window": baseline,
                "recent_window": recent,
                "baseline_scale": baseline_scale,
                "recent_scale": recent_scale,
                "volatility_ratio": ratio,
                "dispersion_persistence": dispersed,
                "cause_status": "unknown_not_inferred",
                "detector_version": self.version,
            },
        )

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        best: _RegimeCandidate | None = None
        required = self.window * 2
        for metric, current in observation.metrics.items():
            history = observation.history.get(metric, [])
            series = [*history, current]
            if len(series) < required:
                continue
            baseline = series[-required : -self.window]
            recent = series[-self.window :]
            candidates = (
                self._trend_change(metric, baseline, recent),
                self._level_change(metric, baseline, recent),
                self._volatility_change(metric, baseline, recent),
            )
            primary = next((candidate for candidate in candidates if candidate is not None), None)
            if primary is None:
                continue
            if best is None or (primary.score, primary.magnitude) > (best.score, best.magnitude):
                best = primary

        if best is None:
            return None
        return DetectorResult(
            detector=self.name,
            score=best.score,
            level=EvidenceLevel.FACT,
            summary=f"Observed structural regime change {best.pattern} in {best.metric}",
            attributes=best.attributes,
        )
