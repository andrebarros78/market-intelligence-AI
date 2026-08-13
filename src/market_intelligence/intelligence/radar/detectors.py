from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Protocol

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


class Detector(Protocol):
    name: str

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None: ...


class KnownRuleDetector:
    name = "known_rule"

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        violated = observation.context.get("known_rule_violation")
        if not violated:
            return None
        return DetectorResult(
            detector=self.name,
            score=1.0,
            level=EvidenceLevel.FACT,
            summary=str(observation.context.get("known_rule_summary", "Known rule violated")),
        )


class RobustZScoreDetector:
    """Deterministic baseline; PyOD ensemble will extend/replace it later."""

    name = "robust_zscore"

    def __init__(self, *, threshold: float = 3.5) -> None:
        self.threshold = threshold

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        best: tuple[str, float, float, float] | None = None
        for metric, current in observation.metrics.items():
            values = observation.history.get(metric, [])
            if len(values) < 5:
                continue
            median = statistics.median(values)
            deviations = [abs(value - median) for value in values]
            mad = statistics.median(deviations)
            if mad == 0:
                if current == median:
                    continue
                robust_z = float("inf")
            else:
                robust_z = 0.6745 * abs(current - median) / mad
            if robust_z >= self.threshold and (best is None or robust_z > best[1]):
                best = (metric, robust_z, current, median)

        if best is None:
            return None

        metric, robust_z, current, median = best
        score = 1.0 if robust_z == float("inf") else min(1.0, robust_z / (self.threshold * 2))
        return DetectorResult(
            detector=self.name,
            score=score,
            level=EvidenceLevel.FACT,
            summary=f"Statistical anomaly detected in {metric}",
            attributes={"metric": metric, "current": current, "historical_median": median, "robust_z": robust_z},
        )


def _median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _median_absolute_step(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.median(abs(right - left) for left, right in zip(values, values[1:]))


def _robust_scale(values: list[float], *, floor_ratio: float) -> float:
    if not values:
        return 1.0
    center = statistics.median(values)
    mad = _median_absolute_deviation(values)
    step = _median_absolute_step(values)
    floor = max(abs(center) * floor_ratio, 1e-9)
    return max(mad, step, floor)


def _median_pairwise_slope(values: list[float]) -> float:
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
class _TemporalCandidate:
    metric: str
    pattern: str
    score: float
    magnitude: float
    attributes: dict[str, float | int | str | list[float]]


class TemporalPatternDetector:
    """Versioned bootstrap detector for ordered numeric histories.

    It detects observed sequence patterns only. It does not infer marketplace
    causality or seasonality because RadarObservation does not yet carry a
    timestamped seasonal index.
    """

    name = "temporal_pattern_v1"
    version = "temporal-pattern@1.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        trend_window: int = 6,
        level_window: int = 4,
        abrupt_window: int = 2,
        effect_threshold: float = 3.0,
        trend_signal_threshold: float = 2.5,
        min_relative_change: float = 0.15,
        floor_ratio: float = 0.02,
    ) -> None:
        if min_history < 6:
            raise ValueError("min_history must be at least 6")
        if trend_window < 5:
            raise ValueError("trend_window must be at least 5")
        if level_window < 3:
            raise ValueError("level_window must be at least 3")
        if abrupt_window != 2:
            raise ValueError("abrupt_window is fixed at 2 for v1")
        self.min_history = min_history
        self.trend_window = trend_window
        self.level_window = level_window
        self.abrupt_window = abrupt_window
        self.effect_threshold = effect_threshold
        self.trend_signal_threshold = trend_signal_threshold
        self.min_relative_change = min_relative_change
        self.floor_ratio = floor_ratio

    @staticmethod
    def _score(signal: float, threshold: float) -> float:
        if signal < threshold:
            return 0.0
        excess = (signal - threshold) / max(threshold, 1e-9)
        return min(1.0, 0.60 + 0.40 * excess)

    def _trend(self, metric: str, series: list[float]) -> _TemporalCandidate | None:
        if len(series) < self.trend_window + 4:
            return None
        recent = series[-self.trend_window :]
        baseline = series[: -self.trend_window]
        baseline_scale = _robust_scale(baseline, floor_ratio=self.floor_ratio)
        slope = _median_pairwise_slope(recent)
        slope_signal = abs(slope) / baseline_scale
        steps = [right - left for left, right in zip(recent, recent[1:])]
        if slope == 0:
            return None
        agreeing = sum(1 for step in steps if step * slope > 0)
        monotonic_fraction = agreeing / len(steps)
        total_change = recent[-1] - recent[0]
        relative_change = abs(total_change) / max(abs(recent[0]), baseline_scale)
        if (
            slope_signal < self.trend_signal_threshold
            or monotonic_fraction < 0.80
            or relative_change < self.min_relative_change
        ):
            return None
        score = self._score(slope_signal, self.trend_signal_threshold)
        return _TemporalCandidate(
            metric=metric,
            pattern="progressive_trend",
            score=score,
            magnitude=slope_signal,
            attributes={
                "metric": metric,
                "pattern": "progressive_trend",
                "direction": _direction(slope),
                "current": series[-1],
                "recent_values": recent,
                "robust_slope": slope,
                "slope_signal": slope_signal,
                "monotonic_fraction": monotonic_fraction,
                "relative_change": relative_change,
                "baseline_median": statistics.median(baseline),
                "baseline_scale": baseline_scale,
                "detector_version": self.version,
            },
        )

    def _level_shift(self, metric: str, series: list[float]) -> _TemporalCandidate | None:
        if len(series) < self.level_window + 5:
            return None
        recent = series[-self.level_window :]
        baseline = series[: -self.level_window]
        baseline_median = statistics.median(baseline)
        recent_median = statistics.median(recent)
        shift = recent_median - baseline_median
        scale = _robust_scale(baseline, floor_ratio=self.floor_ratio)
        effect = abs(shift) / scale
        relative_change = abs(shift) / max(abs(baseline_median), scale)
        if shift == 0:
            return None
        agreeing = sum(1 for value in recent if (value - baseline_median) * shift > 0)
        persistence = agreeing / len(recent)
        if (
            effect < self.effect_threshold
            or relative_change < self.min_relative_change
            or persistence < 0.75
        ):
            return None
        score = self._score(effect, self.effect_threshold)
        return _TemporalCandidate(
            metric=metric,
            pattern="persistent_level_shift",
            score=score,
            magnitude=effect,
            attributes={
                "metric": metric,
                "pattern": "persistent_level_shift",
                "direction": _direction(shift),
                "current": series[-1],
                "baseline_median": baseline_median,
                "recent_median": recent_median,
                "recent_values": recent,
                "effect_size": effect,
                "relative_change": relative_change,
                "persistence": persistence,
                "baseline_scale": scale,
                "detector_version": self.version,
            },
        )

    def _abrupt_break(self, metric: str, series: list[float]) -> _TemporalCandidate | None:
        if len(series) < self.min_history + 1:
            return None
        recent = series[-self.abrupt_window :]
        baseline = series[: -self.abrupt_window]
        if len(baseline) < 5:
            return None
        baseline_median = statistics.median(baseline)
        recent_median = statistics.median(recent)
        shift = recent_median - baseline_median
        scale = _robust_scale(baseline, floor_ratio=self.floor_ratio)
        effect = abs(shift) / scale
        relative_change = abs(shift) / max(abs(baseline_median), scale)
        same_side = all((value - baseline_median) * shift > 0 for value in recent) if shift else False
        jump = recent[0] - baseline[-1]
        jump_signal = abs(jump) / scale
        if (
            not same_side
            or effect < self.effect_threshold
            or jump_signal < self.effect_threshold
            or relative_change < self.min_relative_change
        ):
            return None
        signal = min(effect, jump_signal)
        score = self._score(signal, self.effect_threshold)
        return _TemporalCandidate(
            metric=metric,
            pattern="abrupt_break",
            score=score,
            magnitude=signal,
            attributes={
                "metric": metric,
                "pattern": "abrupt_break",
                "direction": _direction(shift),
                "current": series[-1],
                "baseline_median": baseline_median,
                "recent_values": recent,
                "effect_size": effect,
                "jump_signal": jump_signal,
                "relative_change": relative_change,
                "baseline_scale": scale,
                "detector_version": self.version,
            },
        )

    def _isolated_spike(self, metric: str, history: list[float], current: float) -> _TemporalCandidate | None:
        if len(history) < self.min_history:
            return None
        baseline_median = statistics.median(history)
        scale = _robust_scale(history, floor_ratio=self.floor_ratio)
        delta = current - baseline_median
        effect = abs(delta) / scale
        relative_change = abs(delta) / max(abs(baseline_median), scale)
        stable_tail = history[-min(3, len(history)) :]
        tail_distance = max(abs(value - baseline_median) for value in stable_tail) / scale
        if (
            effect < self.effect_threshold
            or relative_change < self.min_relative_change
            or tail_distance > self.effect_threshold / 2
        ):
            return None
        score = self._score(effect, self.effect_threshold)
        return _TemporalCandidate(
            metric=metric,
            pattern="isolated_spike",
            score=score,
            magnitude=effect,
            attributes={
                "metric": metric,
                "pattern": "isolated_spike",
                "direction": _direction(delta),
                "current": current,
                "baseline_median": baseline_median,
                "effect_size": effect,
                "relative_change": relative_change,
                "tail_stability_signal": tail_distance,
                "baseline_scale": scale,
                "detector_version": self.version,
            },
        )

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        best: _TemporalCandidate | None = None
        for metric, current in observation.metrics.items():
            history = observation.history.get(metric, [])
            if len(history) < self.min_history:
                continue
            series = [*history, current]
            candidates = (
                self._trend(metric, series),
                self._level_shift(metric, series),
                self._abrupt_break(metric, series),
                self._isolated_spike(metric, history, current),
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
            summary=f"Temporal pattern {best.pattern} detected in {best.metric}",
            attributes=best.attributes,
        )
