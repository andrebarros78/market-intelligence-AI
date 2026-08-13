from __future__ import annotations

import math
import statistics


def differences(values: list[float]) -> list[float]:
    return [float(right) - float(left) for left, right in zip(values, values[1:])]


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    left_ss = sum(value * value for value in left_centered)
    right_ss = sum(value * value for value in right_centered)
    if left_ss <= 1e-18 or right_ss <= 1e-18:
        return None
    value = sum(a * b for a, b in zip(left_centered, right_centered)) / math.sqrt(left_ss * right_ss)
    return max(-1.0, min(1.0, float(value)))
