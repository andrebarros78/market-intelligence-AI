from __future__ import annotations

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation
from market_intelligence.intelligence.radar.time_series import SeasonalReference, find_seasonal_reference


class SeasonalityDetector:
    name = "seasonality_v1"
    version = "seasonality@1.0.0"

    def __init__(self, *, deviation_threshold: float = 3.0, min_deviation_ratio: float = 0.15) -> None:
        self.deviation_threshold = deviation_threshold
        self.min_deviation_ratio = min_deviation_ratio

    def _unexpected(self, reference: SeasonalReference) -> bool:
        return (
            reference.deviation_signal >= self.deviation_threshold
            and reference.deviation_ratio >= self.min_deviation_ratio
        )

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        references = [
            reference
            for metric in observation.metrics
            if (reference := find_seasonal_reference(observation, metric)) is not None
        ]
        if not references:
            return None

        deviations = [item for item in references if self._unexpected(item)]
        expected = [item for item in references if not self._unexpected(item)]
        expected_metrics = sorted(item.metric for item in expected)

        if deviations:
            selected = max(deviations, key=lambda item: (item.deviation_signal, item.deviation_ratio))
            attributes = selected.as_dict()
            attributes.update(
                {
                    "pattern": "seasonal_deviation",
                    "expected_metrics": expected_metrics,
                    "detector_version": self.version,
                }
            )
            excess = max(0.0, selected.deviation_signal - self.deviation_threshold)
            score = min(1.0, 0.60 + 0.40 * excess / max(self.deviation_threshold, 1e-9))
            return DetectorResult(
                detector=self.name,
                score=score,
                level=EvidenceLevel.FACT,
                summary=f"Seasonal deviation detected in {selected.metric}",
                attributes=attributes,
            )

        selected = max(references, key=lambda item: (item.effect_size, item.relative_effect))
        attributes = selected.as_dict()
        attributes.update(
            {
                "pattern": "seasonal_expected",
                "expected_metrics": expected_metrics,
                "detector_version": self.version,
            }
        )
        return DetectorResult(
            detector=self.name,
            score=0.0,
            level=EvidenceLevel.FACT,
            summary=f"Observed value matches established seasonal pattern in {selected.metric}",
            attributes=attributes,
        )
