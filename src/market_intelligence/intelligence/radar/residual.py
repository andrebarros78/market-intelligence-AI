from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.factor_attribution import FactorAttributionEngine
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation
from market_intelligence.intelligence.radar.time_series import find_seasonal_reference


class ObservableEffect(BaseModel):
    name: str = Field(min_length=1)
    contribution: float
    source: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ResidualAnalysis(BaseModel):
    metric: str = Field(min_length=1)
    expected: float | None = None
    observable_effects: list[ObservableEffect] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class UnexplainedResidualDetector:
    name = "unexplained_residual_v1"
    version = "unexplained-residual@2.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        min_total_change_ratio: float = 0.15,
        min_residual_ratio: float = 0.20,
        min_unexplained_fraction: float = 0.50,
    ) -> None:
        if min_history < 4:
            raise ValueError("min_history must be at least 4")
        if min_total_change_ratio <= 0:
            raise ValueError("min_total_change_ratio must be positive")
        if min_residual_ratio <= 0:
            raise ValueError("min_residual_ratio must be positive")
        if not 0 < min_unexplained_fraction <= 1:
            raise ValueError("min_unexplained_fraction must be in (0, 1]")
        self.min_history = min_history
        self.min_total_change_ratio = min_total_change_ratio
        self.min_residual_ratio = min_residual_ratio
        self.min_unexplained_fraction = min_unexplained_fraction
        self.factor_engine = FactorAttributionEngine(min_history=min_history)

    @staticmethod
    def _score(residual_ratio: float, threshold: float, unexplained_fraction: float) -> float:
        residual_strength = residual_ratio / max(threshold, 1e-9)
        fraction_strength = unexplained_fraction
        strength = min(residual_strength, 1.0 + fraction_strength)
        return min(1.0, 0.60 + 0.25 * max(0.0, strength - 1.0))

    def _analysis(self, observation: RadarObservation) -> ResidualAnalysis | None:
        raw = observation.context.get("residual_analysis")
        if isinstance(raw, dict):
            try:
                return ResidualAnalysis.model_validate(raw)
            except ValidationError:
                return None

        attribution = self.factor_engine.analyze(observation)
        if attribution is None:
            return None

        return ResidualAnalysis(
            metric=attribution.metric,
            expected=attribution.expected,
            observable_effects=[
                ObservableEffect(
                    name=factor.name,
                    contribution=factor.contribution,
                    source=factor.source,
                    attributes={
                        "association": factor.association,
                        "slope": factor.slope,
                        "factor_attribution_version": attribution.version,
                    },
                )
                for factor in attribution.factors
            ],
            attributes={
                "automatic_factor_attribution": True,
                "factor_attribution": attribution.model_dump(mode="json"),
            },
        )

    def _expected(
        self, observation: RadarObservation, analysis: ResidualAnalysis
    ) -> tuple[float, str] | None:
        if analysis.expected is not None:
            return analysis.expected, "explicit_expected"
        seasonal = find_seasonal_reference(observation, analysis.metric)
        if seasonal is not None:
            return seasonal.expected, f"seasonal:{seasonal.period}"
        history = observation.history.get(analysis.metric, [])
        if len(history) < self.min_history:
            return None
        return float(statistics.median(history)), "history_median"

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        analysis = self._analysis(observation)
        if analysis is None or analysis.metric not in observation.metrics:
            return None
        expected_result = self._expected(observation, analysis)
        if expected_result is None:
            return None
        expected, reference_source = expected_result
        observed = float(observation.metrics[analysis.metric])
        observed_delta = observed - expected
        history = observation.history.get(analysis.metric, [])
        historical_magnitude = (
            float(statistics.median(abs(value) for value in history)) if history else 0.0
        )
        denominator = max(abs(expected), historical_magnitude, 1e-9)
        total_change_ratio = abs(observed_delta) / denominator
        if total_change_ratio < self.min_total_change_ratio:
            return None

        explained_delta = sum(effect.contribution for effect in analysis.observable_effects)
        residual = observed_delta - explained_delta
        residual_ratio = abs(residual) / denominator
        unexplained_fraction = abs(residual) / max(abs(observed_delta), 1e-9)
        if residual_ratio < self.min_residual_ratio:
            return None
        if unexplained_fraction < self.min_unexplained_fraction:
            return None

        observable_causes = [effect.name for effect in analysis.observable_effects]
        effects = [effect.model_dump(mode="json") for effect in analysis.observable_effects]
        attributes = {
            "pattern": "unexplained_residual",
            "metric": analysis.metric,
            "expected": expected,
            "observed": observed,
            "observed_delta": observed_delta,
            "observable_effects": effects,
            "explained_delta": explained_delta,
            "unexplained_residual": residual,
            "total_change_ratio": total_change_ratio,
            "residual_ratio": residual_ratio,
            "unexplained_fraction": unexplained_fraction,
            "reference_source": reference_source,
            "observable_causes": observable_causes,
            "cause_status": "unknown_not_inferred",
            "investigation_required": True,
            "detector_version": self.version,
            "analysis_attributes": analysis.attributes,
        }
        score = self._score(residual_ratio, self.min_residual_ratio, unexplained_fraction)
        return DetectorResult(
            detector=self.name,
            score=score,
            level=EvidenceLevel.INFERENCE,
            summary=(
                f"Observable factors do not sufficiently explain {analysis.metric}; "
                f"residual {residual:.6g} remains"
            ),
            attributes=attributes,
        )
