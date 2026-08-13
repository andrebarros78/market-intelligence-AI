from __future__ import annotations

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation
from market_intelligence.intelligence.radar.time_series import find_seasonal_reference


class SeasonalityDetector:
    name = "seasonality_v1"
    version = "seasonality@1.0.0"

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        references = [
            reference
            for metric in observation.metrics
            if (reference := find_seasonal_reference(observation, metric)) is not None
        ]
        if not references:
            return None
        selected = max(references, key=lambda item: (item.effect_size, item.relative_effect))
        return DetectorResult(
            detector=self.name,
            score=0.0,
            level=EvidenceLevel.FACT,
            summary=f"Seasonal pattern observed in {selected.metric}",
            attributes={
                **selected.as_dict(),
                "pattern": "seasonal_expected",
                "expected_metrics": sorted(item.metric for item in references),
                "detector_version": self.version,
            },
        )
