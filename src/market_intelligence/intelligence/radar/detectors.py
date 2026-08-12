from __future__ import annotations

import statistics
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
