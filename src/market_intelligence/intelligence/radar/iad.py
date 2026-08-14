from __future__ import annotations

import statistics
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


IAD_COMPONENTS = (
    "traffic_deviation",
    "conversion_deviation",
    "competition_change",
    "control_divergence",
    "regime_change",
    "observable_gap",
    "unexplained_residual",
    "channel_regime",
)

_TRAFFIC_METRICS = {
    "visits",
    "visitas",
    "impressions",
    "impressoes",
    "clicks",
    "cliques",
    "traffic",
    "trafego",
}
_CONVERSION_METRICS = {"conversion", "conversao", "conversion_rate", "ctr"}
_COMPETITION_METRICS = {
    "competition",
    "competicao",
    "catalog_competition",
    "catalog_rank",
    "price_to_win",
    "buy_box",
    "winning_offer",
}


class IADCalibrationProfile(BaseModel):
    """Versioned scoring profile produced from historical validation.

    The runtime never invents weights. A profile must be supplied explicitly.
    Synthetic profiles are accepted for tests/experiments but cannot be marked
    as production approved.
    """

    version: str = Field(min_length=1)
    source_type: Literal["historical_validation", "synthetic_test"]
    weights: dict[str, float]
    threshold: float = Field(gt=0.0, lt=1.0)
    min_components: int = Field(default=2, ge=2)
    production_approved: bool = False
    sample_count: int = Field(default=0, ge=0)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("iad calibration requires at least one weight")
        clean: dict[str, float] = {}
        for name, weight in value.items():
            if name not in IAD_COMPONENTS:
                raise ValueError(f"unknown iad component: {name}")
            numeric = float(weight)
            if numeric <= 0:
                raise ValueError("iad weights must be positive")
            clean[name] = numeric
        return clean

    @model_validator(mode="after")
    def validate_approval(self) -> "IADCalibrationProfile":
        if self.min_components > len(self.weights):
            raise ValueError("iad min_components cannot exceed weighted components")
        if self.sample_count or self.positive_count or self.negative_count:
            if self.positive_count + self.negative_count != self.sample_count:
                raise ValueError("calibration class counts must equal sample_count")
        if self.production_approved:
            if self.source_type != "historical_validation":
                raise ValueError("synthetic calibration cannot be production approved")
            if self.sample_count <= 0 or self.positive_count <= 0 or self.negative_count <= 0:
                raise ValueError(
                    "production-approved iad calibration requires recorded positive and negative history"
                )
        return self


class IADCalibrationSample(BaseModel):
    label: bool
    components: dict[str, float]

    @field_validator("components")
    @classmethod
    def validate_components(cls, value: dict[str, float]) -> dict[str, float]:
        clean: dict[str, float] = {}
        for name, score in value.items():
            if name not in IAD_COMPONENTS:
                raise ValueError(f"unknown iad component: {name}")
            numeric = float(score)
            if not 0.0 <= numeric <= 1.0:
                raise ValueError("iad component scores must be between 0 and 1")
            clean[name] = numeric
        if not clean:
            raise ValueError("calibration sample requires components")
        return clean


class IADCalibrator:
    """Deterministic historical calibrator.

    Component weights are learned from class separation in supplied labelled
    historical examples. The decision threshold is selected by balanced
    accuracy, with deterministic tie-breaking toward the higher threshold to
    reduce false-positive promotion when validation quality is equal.
    """

    version = "iad-calibrator@1.0.0"

    @staticmethod
    def _weighted_score(components: dict[str, float], weights: dict[str, float]) -> float | None:
        available = {name: weights[name] for name in components if name in weights}
        if not available:
            return None
        denominator = sum(available.values())
        return sum(components[name] * weight for name, weight in available.items()) / denominator

    @staticmethod
    def _balanced_accuracy(labels: list[bool], predictions: list[bool]) -> tuple[float, float, float]:
        positives = sum(labels)
        negatives = len(labels) - positives
        true_positive = sum(1 for label, pred in zip(labels, predictions) if label and pred)
        true_negative = sum(1 for label, pred in zip(labels, predictions) if not label and not pred)
        sensitivity = true_positive / positives
        specificity = true_negative / negatives
        return (sensitivity + specificity) / 2.0, sensitivity, specificity

    def fit(
        self,
        samples: list[IADCalibrationSample | dict[str, Any]],
        *,
        version: str,
        source_type: Literal["historical_validation", "synthetic_test"] = "historical_validation",
    ) -> IADCalibrationProfile:
        parsed = [
            sample if isinstance(sample, IADCalibrationSample) else IADCalibrationSample.model_validate(sample)
            for sample in samples
        ]
        if not parsed:
            raise ValueError("iad calibration requires samples")
        positives = [sample for sample in parsed if sample.label]
        negatives = [sample for sample in parsed if not sample.label]
        if not positives or not negatives:
            raise ValueError("iad calibration requires positive and negative examples")

        separations: dict[str, float] = {}
        for component in IAD_COMPONENTS:
            positive_values = [sample.components[component] for sample in positives if component in sample.components]
            negative_values = [sample.components[component] for sample in negatives if component in sample.components]
            if not positive_values or not negative_values:
                continue
            separation = statistics.fmean(positive_values) - statistics.fmean(negative_values)
            if separation > 0:
                separations[component] = separation
        if len(separations) < 2:
            raise ValueError("iad calibration requires at least two positively separating components")

        total = sum(separations.values())
        weights = {name: value / total for name, value in separations.items()}
        scored: list[tuple[bool, float, int]] = []
        for sample in parsed:
            score = self._weighted_score(sample.components, weights)
            if score is None:
                continue
            count = sum(1 for name in sample.components if name in weights)
            scored.append((sample.label, score, count))
        if not scored:
            raise ValueError("calibration samples cannot be scored")

        labels = [label for label, _, _ in scored]
        unique = sorted({score for _, score, _ in scored})
        if len(unique) == 1:
            raise ValueError("historical samples do not separate iad classes")
        candidates = [(left + right) / 2.0 for left, right in zip(unique, unique[1:])]

        best: tuple[float, float, float, float] | None = None
        for threshold in candidates:
            predictions = [score >= threshold for _, score, _ in scored]
            balanced, sensitivity, specificity = self._balanced_accuracy(labels, predictions)
            candidate = (balanced, threshold, sensitivity, specificity)
            if best is None or (candidate[0], candidate[1]) > (best[0], best[1]):
                best = candidate
        if best is None:
            raise ValueError("iad threshold calibration failed")
        balanced, threshold, sensitivity, specificity = best

        positive_component_counts = [count for label, _, count in scored if label]
        min_components = max(2, min(positive_component_counts))
        min_components = min(min_components, len(weights))
        return IADCalibrationProfile(
            version=version,
            source_type=source_type,
            weights=weights,
            threshold=threshold,
            min_components=min_components,
            production_approved=False,
            sample_count=len(scored),
            positive_count=sum(labels),
            negative_count=len(labels) - sum(labels),
            metrics={
                "balanced_accuracy": balanced,
                "sensitivity": sensitivity,
                "specificity": specificity,
            },
        )


class DistributionAnomalyIndex:
    """Calibrated, non-causal distribution anomaly indicator."""

    name = "distribution_anomaly_index_v1"
    version = "distribution-anomaly-index@1.0.0"

    @staticmethod
    def _metric(result: DetectorResult) -> str | None:
        value = result.attributes.get("metric")
        return str(value).strip().lower() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _max_component(
        current: dict[str, tuple[float, list[str]]],
        name: str,
        score: float,
        source: str,
    ) -> None:
        existing = current.get(name)
        if existing is None or score > existing[0]:
            current[name] = (float(score), [source])
        elif score == existing[0] and source not in existing[1]:
            existing[1].append(source)

    def components(self, results: list[DetectorResult]) -> tuple[dict[str, float], dict[str, list[str]]]:
        observed: dict[str, tuple[float, list[str]]] = {}
        for result in results:
            metric = self._metric(result)
            if metric in _TRAFFIC_METRICS and result.detector in {
                "robust_zscore",
                "temporal_pattern_v1",
                "regime_change_v1",
            }:
                self._max_component(observed, "traffic_deviation", result.score, result.detector)
            if metric in _CONVERSION_METRICS and result.detector in {
                "robust_zscore",
                "temporal_pattern_v1",
                "regime_change_v1",
            }:
                self._max_component(observed, "conversion_deviation", result.score, result.detector)
            if metric in _COMPETITION_METRICS:
                self._max_component(observed, "competition_change", result.score, result.detector)
            if result.detector in {"relational_control_v1", "operational_counterfactual_v1"}:
                self._max_component(observed, "control_divergence", result.score, result.detector)
            if result.detector == "regime_change_v1":
                self._max_component(observed, "regime_change", result.score, result.detector)
            if result.detector == "unexplained_residual_v1":
                self._max_component(observed, "unexplained_residual", result.score, result.detector)
            if result.detector == "channel_regime_correlation_v1":
                self._max_component(observed, "channel_regime", result.score, result.detector)
            if result.detector == "factor_attribution_v1":
                raw = result.attributes.get("factor_attribution")
                if isinstance(raw, dict):
                    explained = raw.get("explained_fraction")
                    if isinstance(explained, (int, float)):
                        gap = min(1.0, max(0.0, 1.0 - float(explained)))
                        self._max_component(observed, "observable_gap", gap, result.detector)
        return (
            {name: value[0] for name, value in observed.items()},
            {name: sorted(value[1]) for name, value in observed.items()},
        )

    @staticmethod
    def _decision_score(raw_score: float, threshold: float) -> float:
        if raw_score >= threshold:
            return 0.60 + 0.40 * ((raw_score - threshold) / max(1.0 - threshold, 1e-9))
        return 0.60 * (raw_score / max(threshold, 1e-9))

    def evaluate(
        self,
        observation: RadarObservation,
        results: list[DetectorResult],
    ) -> DetectorResult | None:
        raw_profile = observation.context.get("iad_calibration")
        if not isinstance(raw_profile, dict):
            return None
        try:
            profile = IADCalibrationProfile.model_validate(raw_profile)
        except ValidationError:
            return None

        components, sources = self.components(results)
        available_weights = {
            name: weight for name, weight in profile.weights.items() if name in components
        }
        if len(available_weights) < profile.min_components:
            return None
        weight_total = sum(available_weights.values())
        raw_score = sum(
            components[name] * weight for name, weight in available_weights.items()
        ) / weight_total
        decision_score = self._decision_score(raw_score, profile.threshold)
        anomaly_decision = raw_score >= profile.threshold

        approved = profile.production_approved
        level = EvidenceLevel.INFERENCE if approved else EvidenceLevel.HYPOTHESIS
        score = decision_score if approved else min(0.59, decision_score)
        attributes = {
            "pattern": "distribution_anomaly_index",
            "iad_score": raw_score,
            "iad_threshold": profile.threshold,
            "iad_decision": anomaly_decision if approved else False,
            "alert_eligible": approved,
            "calibration_version": profile.version,
            "calibration_source_type": profile.source_type,
            "production_approved": approved,
            "calibration_sample_count": profile.sample_count,
            "calibration_metrics": profile.metrics,
            "components": components,
            "component_sources": sources,
            "weights_used": available_weights,
            "component_count": len(available_weights),
            "missing_weighted_components": sorted(set(profile.weights) - set(available_weights)),
            "causal_claim": False,
            "internal_platform_cause_confirmed": False,
            "detector_version": self.version,
        }
        if approved:
            summary = (
                "Calibrated distribution anomaly index exceeded its historical threshold"
                if anomaly_decision
                else "Calibrated distribution anomaly index remained below its historical threshold"
            )
        else:
            summary = "Experimental IAD calculated with non-production calibration; no alert promotion"
        return DetectorResult(
            detector=self.name,
            score=score,
            level=level,
            summary=summary,
            attributes=attributes,
        )
