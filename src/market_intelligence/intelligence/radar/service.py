from __future__ import annotations

from collections.abc import Iterable

from market_intelligence.intelligence.radar.detectors import Detector
from market_intelligence.intelligence.radar.models import RadarFinding, RadarObservation


class RadarService:
    def __init__(self, detectors: Iterable[Detector], *, anomaly_threshold: float = 0.60) -> None:
        self._detectors = tuple(detectors)
        self._anomaly_threshold = anomaly_threshold

    def evaluate(self, observation: RadarObservation) -> RadarFinding:
        results = [result for detector in self._detectors if (result := detector.evaluate(observation))]
        score = max((result.score for result in results), default=0.0)
        return RadarFinding(
            entity_id=observation.entity_id,
            score=score,
            anomalous=score >= self._anomaly_threshold,
            detector_results=results,
        )
