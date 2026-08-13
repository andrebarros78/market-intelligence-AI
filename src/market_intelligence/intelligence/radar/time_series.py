from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from market_intelligence.intelligence.radar.models import RadarObservation


def robust_scale(values: list[float], *, floor_ratio: float = 0.02) -> float:
    if not values:
        return 1.0
    center = float(statistics.median(values))
    mad = float(statistics.median(abs(value - center) for value in values))
    return max(mad, abs(center) * floor_ratio, 1e-9)


_PERIODS: tuple[tuple[str, Callable[[datetime], int]], ...] = (
    ("weekday", lambda value: value.weekday()),
    ("hour_of_day", lambda value: value.hour),
    ("day_of_month", lambda value: value.day),
    ("month_of_year", lambda value: value.month),
)


@dataclass(frozen=True, slots=True)
class SeasonalReference:
    metric: str
    period: str
    bucket: int
    current: float
    expected: float
    baseline: float
    seasonal_effect: float
    effect_size: float
    relative_effect: float
    bucket_count: int
    other_count: int
    bucket_scale: float
    deviation: float
    deviation_signal: float
    deviation_ratio: float

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "metric": self.metric,
            "period": self.period,
            "bucket": self.bucket,
            "current": self.current,
            "seasonal_expected": self.expected,
            "nonseasonal_baseline": self.baseline,
            "seasonal_effect": self.seasonal_effect,
            "seasonal_effect_size": self.effect_size,
            "seasonal_relative_effect": self.relative_effect,
            "same_bucket_count": self.bucket_count,
            "other_count": self.other_count,
            "bucket_scale": self.bucket_scale,
            "current_deviation": self.deviation,
            "current_deviation_signal": self.deviation_signal,
            "current_deviation_ratio": self.deviation_ratio,
        }


def find_seasonal_reference(
    observation: RadarObservation,
    metric: str,
    *,
    min_total_points: int = 16,
    min_bucket_points: int = 4,
    min_other_points: int = 8,
    min_effect_size: float = 2.5,
    min_relative_effect: float = 0.10,
) -> SeasonalReference | None:
    points = observation.timestamped_history.get(metric, [])
    if metric not in observation.metrics or len(points) < min_total_points:
        return None
    current_time = observation.observed_at
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        return None
    localized = [
        (point.timestamp.astimezone(current_time.tzinfo), float(point.value))
        for point in points
    ]
    current = float(observation.metrics[metric])
    candidates: list[SeasonalReference] = []
    for period, bucket_of in _PERIODS:
        bucket = bucket_of(current_time)
        same = [value for timestamp, value in localized if bucket_of(timestamp) == bucket]
        other = [value for timestamp, value in localized if bucket_of(timestamp) != bucket]
        if len(same) < min_bucket_points or len(other) < min_other_points:
            continue
        expected = float(statistics.median(same))
        baseline = float(statistics.median(other))
        seasonal_effect = expected - baseline
        scale = robust_scale(other)
        effect_size = abs(seasonal_effect) / scale
        relative_effect = abs(seasonal_effect) / max(abs(baseline), scale)
        if effect_size < min_effect_size or relative_effect < min_relative_effect:
            continue
        bucket_scale = robust_scale(same)
        deviation = current - expected
        candidates.append(
            SeasonalReference(
                metric=metric,
                period=period,
                bucket=bucket,
                current=current,
                expected=expected,
                baseline=baseline,
                seasonal_effect=seasonal_effect,
                effect_size=effect_size,
                relative_effect=relative_effect,
                bucket_count=len(same),
                other_count=len(other),
                bucket_scale=bucket_scale,
                deviation=deviation,
                deviation_signal=abs(deviation) / bucket_scale,
                deviation_ratio=abs(deviation) / max(abs(expected), bucket_scale),
            )
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.effect_size, item.relative_effect, item.bucket_count))
