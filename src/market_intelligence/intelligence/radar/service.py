from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from market_intelligence.intelligence.radar.detectors import Detector
from market_intelligence.intelligence.radar.models import DetectorResult, RadarFinding, RadarObservation


class DerivedDetector(Protocol):
    name: str

    def evaluate(
        self,
        observation: RadarObservation,
        results: list[DetectorResult],
    ) -> DetectorResult | None: ...


def _seasonally_expected_metrics(results: list[DetectorResult]) -> set[str]:
    expected: set[str] = set()
    for result in results:
        if result.detector != "seasonality_v1":
            continue
        values = result.attributes.get("expected_metrics")
        if isinstance(values, list):
            expected.update(str(value) for value in values)
    return expected


def _seasonal_false_positive(result: DetectorResult, expected: set[str]) -> bool:
    metric = result.attributes.get("metric")
    if not isinstance(metric, str) or metric not in expected:
        return False
    if result.detector == "robust_zscore":
        return True
    return (
        result.detector == "temporal_pattern_v1"
        and result.attributes.get("pattern") == "isolated_spike"
    )


class RadarService:
    def __init__(
        self,
        detectors: Iterable[Detector],
        *,
        derived_detectors: Iterable[DerivedDetector] = (),
        anomaly_threshold: float = 0.60,
    ) -> None:
        self._detectors = tuple(detectors)
        self._derived_detectors = tuple(derived_detectors)
        self._anomaly_threshold = anomaly_threshold

    def evaluate(self, observation: RadarObservation) -> RadarFinding:
        observed = [
            result
            for detector in self._detectors
            if (result := detector.evaluate(observation)) is not None
        ]
        expected = _seasonally_expected_metrics(observed)
        results = [
            result for result in observed if not _seasonal_false_positive(result, expected)
        ]
        for detector in self._derived_detectors:
            derived = detector.evaluate(observation, list(results))
            if derived is not None:
                results.append(derived)
        score = max((result.score for result in results), default=0.0)
        return RadarFinding(
            entity_id=observation.entity_id,
            score=score,
            anomalous=score >= self._anomaly_threshold,
            detector_results=results,
        )
