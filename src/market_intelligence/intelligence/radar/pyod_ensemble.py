from __future__ import annotations

import statistics
from importlib.metadata import version as package_version
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field, field_validator, model_validator
from pyod.models.ecod import ECOD
from pyod.models.iforest import IForest
from pyod.models.knn import KNN

from market_intelligence.core.contracts import EvidenceLevel
from market_intelligence.intelligence.radar.models import DetectorResult, RadarObservation


PYOD_DETECTORS = ("ecod", "iforest", "knn")


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def _median_step(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.median(abs(right - left) for left, right in zip(values, values[1:]))


def _robust_scale(values: list[float]) -> float:
    center = statistics.median(values) if values else 0.0
    floor = max(abs(center) * 0.02, 1e-9)
    return max(_mad(values), _median_step(values), floor)


def _percentile(training_scores: list[float], score: float) -> float:
    if not training_scores:
        return 0.0
    less = sum(1 for value in training_scores if value < score)
    equal = sum(1 for value in training_scores if value == score)
    return min(1.0, max(0.0, (less + 0.5 * equal) / len(training_scores)))


def _balanced_accuracy(
    labels: list[bool], predictions: list[bool]
) -> tuple[float, float, float]:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives <= 0 or negatives <= 0:
        raise ValueError("benchmark requires positive and negative validation examples")
    true_positive = sum(1 for label, pred in zip(labels, predictions) if label and pred)
    true_negative = sum(1 for label, pred in zip(labels, predictions) if not label and not pred)
    sensitivity = true_positive / positives
    specificity = true_negative / negatives
    return (sensitivity + specificity) / 2.0, sensitivity, specificity


def _best_threshold(labels: list[bool], scores: list[float]) -> tuple[float, dict[str, float]]:
    unique = sorted(set(scores))
    if len(unique) < 2:
        raise ValueError("benchmark scores do not separate validation examples")
    candidates = [(left + right) / 2.0 for left, right in zip(unique, unique[1:])]
    best: tuple[float, float, float, float] | None = None
    for threshold in candidates:
        predictions = [score >= threshold for score in scores]
        balanced, sensitivity, specificity = _balanced_accuracy(labels, predictions)
        candidate = (balanced, threshold, sensitivity, specificity)
        if best is None or (candidate[0], candidate[1]) > (best[0], best[1]):
            best = candidate
    if best is None:
        raise ValueError("benchmark threshold selection failed")
    balanced, threshold, sensitivity, specificity = best
    return threshold, {
        "balanced_accuracy": balanced,
        "sensitivity": sensitivity,
        "specificity": specificity,
    }


def _model(name: str):
    if name == "ecod":
        return ECOD()
    if name == "iforest":
        return IForest(random_state=17)
    if name == "knn":
        return KNN(n_neighbors=5)
    raise ValueError(f"unsupported pyod detector: {name}")


def _normalize_matrix(
    rows: list[list[float]],
) -> tuple[list[list[float]], list[float], list[float]]:
    if not rows:
        raise ValueError("feature matrix cannot be empty")
    width = len(rows[0])
    if width < 2 or any(len(row) != width for row in rows):
        raise ValueError("feature matrix requires at least two aligned features")
    columns = [[float(row[index]) for row in rows] for index in range(width)]
    centers = [float(statistics.median(column)) for column in columns]
    scales = [_robust_scale(column) for column in columns]
    normalized = [
        [(float(value) - centers[index]) / scales[index] for index, value in enumerate(row)]
        for row in rows
    ]
    return normalized, centers, scales


def _normalize_rows(
    rows: list[list[float]], centers: list[float], scales: list[float]
) -> list[list[float]]:
    width = len(centers)
    if any(len(row) != width for row in rows):
        raise ValueError("validation feature width does not match training features")
    return [
        [(float(value) - centers[index]) / scales[index] for index, value in enumerate(row)]
        for row in rows
    ]


def _as_matrix(rows: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(rows, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("pyod adapter requires a two-dimensional matrix")
    return matrix


class PyODBenchmarkSample(BaseModel):
    label: bool
    features: list[float] = Field(min_length=2)


class PyODBenchmarkProfile(BaseModel):
    version: str = Field(min_length=1)
    source_type: Literal["historical_validation", "synthetic_test"]
    detector_weights: dict[str, float]
    threshold: float = Field(gt=0.0, lt=1.0)
    feature_names: list[str] = Field(min_length=2)
    min_history: int = Field(default=12, ge=12)
    production_approved: bool = False
    sample_count: int = Field(default=0, ge=0)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    metrics: dict[str, float] = Field(default_factory=dict)
    detector_metrics: dict[str, dict[str, float]] = Field(default_factory=dict)

    @field_validator("detector_weights")
    @classmethod
    def validate_detector_weights(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) < 2:
            raise ValueError("pyod ensemble requires at least two detectors")
        clean: dict[str, float] = {}
        for name, raw_weight in value.items():
            if name not in PYOD_DETECTORS:
                raise ValueError(f"unsupported pyod detector: {name}")
            weight = float(raw_weight)
            if weight <= 0:
                raise ValueError("pyod detector weights must be positive")
            clean[name] = weight
        return clean

    @field_validator("feature_names")
    @classmethod
    def validate_feature_names(cls, value: list[str]) -> list[str]:
        clean = [str(name).strip() for name in value if str(name).strip()]
        if len(clean) < 2 or len(set(clean)) != len(clean):
            raise ValueError("pyod profile requires at least two unique feature names")
        return clean

    @model_validator(mode="after")
    def validate_approval(self) -> "PyODBenchmarkProfile":
        if self.sample_count or self.positive_count or self.negative_count:
            if self.positive_count + self.negative_count != self.sample_count:
                raise ValueError("benchmark class counts must equal sample_count")
        if self.production_approved:
            if self.source_type != "historical_validation":
                raise ValueError("synthetic pyod benchmark cannot be production approved")
            if self.sample_count <= 0 or self.positive_count <= 0 or self.negative_count <= 0:
                raise ValueError(
                    "production-approved pyod profile requires positive and negative history"
                )
            if "balanced_accuracy" not in self.metrics:
                raise ValueError("production-approved pyod profile requires benchmark metrics")
        return self


class PyODBenchmarkCalibrator:
    """Benchmark PyOD detectors on labelled holdout data without auto-promotion."""

    version = "pyod-benchmark@1.0.0"

    def fit(
        self,
        train_features: list[list[float]],
        validation_samples: list[PyODBenchmarkSample | dict[str, Any]],
        *,
        feature_names: list[str],
        version: str,
        source_type: Literal["historical_validation", "synthetic_test"] = "historical_validation",
        detector_names: tuple[str, ...] = PYOD_DETECTORS,
    ) -> PyODBenchmarkProfile:
        if len(train_features) < 12:
            raise ValueError("pyod benchmark requires at least 12 training rows")
        if len(feature_names) < 2 or len(set(feature_names)) != len(feature_names):
            raise ValueError("pyod benchmark requires at least two unique features")
        if any(name not in PYOD_DETECTORS for name in detector_names):
            raise ValueError("pyod benchmark received unsupported detector")
        if len(set(detector_names)) < 2:
            raise ValueError("pyod benchmark requires at least two detectors")

        parsed = [
            sample
            if isinstance(sample, PyODBenchmarkSample)
            else PyODBenchmarkSample.model_validate(sample)
            for sample in validation_samples
        ]
        if not parsed:
            raise ValueError("pyod benchmark requires validation samples")
        labels = [sample.label for sample in parsed]
        _balanced_accuracy(labels, [False for _ in labels])

        normalized_train, centers, scales = _normalize_matrix(train_features)
        if len(centers) != len(feature_names):
            raise ValueError("feature_names width does not match training features")
        normalized_validation = _normalize_rows(
            [sample.features for sample in parsed], centers, scales
        )
        train_matrix = _as_matrix(normalized_train)
        validation_matrix = _as_matrix(normalized_validation)

        detector_scores: dict[str, list[float]] = {}
        detector_metrics: dict[str, dict[str, float]] = {}
        qualities: dict[str, float] = {}
        for name in sorted(set(detector_names)):
            model = _model(name)
            model.fit(train_matrix)
            training_scores = [float(value) for value in model.decision_scores_]
            raw_validation = [
                float(value) for value in model.decision_function(validation_matrix)
            ]
            normalized_scores = [
                _percentile(training_scores, value) for value in raw_validation
            ]
            detector_scores[name] = normalized_scores
            threshold, metrics = _best_threshold(labels, normalized_scores)
            detector_metrics[name] = {**metrics, "threshold": threshold}
            quality = max(0.0, metrics["balanced_accuracy"] - 0.50)
            if quality > 0:
                qualities[name] = quality

        if len(qualities) < 2:
            raise ValueError("benchmark did not identify at least two useful detectors")
        total_quality = sum(qualities.values())
        weights = {name: quality / total_quality for name, quality in qualities.items()}
        ensemble_scores = [
            sum(detector_scores[name][index] * weight for name, weight in weights.items())
            for index in range(len(parsed))
        ]
        threshold, ensemble_metrics = _best_threshold(labels, ensemble_scores)
        return PyODBenchmarkProfile(
            version=version,
            source_type=source_type,
            detector_weights=weights,
            threshold=threshold,
            feature_names=feature_names,
            min_history=12,
            production_approved=False,
            sample_count=len(parsed),
            positive_count=sum(labels),
            negative_count=len(labels) - sum(labels),
            metrics={
                **ensemble_metrics,
                "benchmark_engine_version": 1.0,
            },
            detector_metrics=detector_metrics,
        )


class PyODEnsembleDetector:
    name = "pyod_ensemble_v1"
    version = "pyod-ensemble@1.0.0"

    def __init__(
        self,
        *,
        trusted_profile: PyODBenchmarkProfile | dict[str, Any] | None = None,
        experimental_min_history: int = 12,
    ) -> None:
        self.trusted_profile = (
            trusted_profile
            if isinstance(trusted_profile, PyODBenchmarkProfile)
            else PyODBenchmarkProfile.model_validate(trusted_profile)
            if trusted_profile is not None
            else None
        )
        self.experimental_min_history = max(12, experimental_min_history)

    @staticmethod
    def _history_matrix(
        observation: RadarObservation,
        feature_names: list[str],
        min_history: int,
    ) -> tuple[list[list[float]], list[float], dict[str, dict[str, float]]] | None:
        if len(feature_names) < 2:
            return None
        histories: dict[str, list[float]] = {}
        for name in feature_names:
            values = observation.history.get(name, [])
            if name not in observation.metrics or len(values) < min_history:
                return None
            histories[name] = [float(value) for value in values]
        length = min(len(values) for values in histories.values())
        if length < min_history:
            return None
        length = min(length, 256)
        windows = {name: values[-length:] for name, values in histories.items()}
        rows = [
            [windows[name][index] for name in feature_names]
            for index in range(length)
        ]
        normalized, centers, scales = _normalize_matrix(rows)
        current = [
            (float(observation.metrics[name]) - centers[index]) / scales[index]
            for index, name in enumerate(feature_names)
        ]
        scaling = {
            name: {"center": centers[index], "scale": scales[index]}
            for index, name in enumerate(feature_names)
        }
        return normalized, current, scaling

    def _experimental_features(self, observation: RadarObservation) -> list[str]:
        return sorted(
            name
            for name in observation.metrics
            if len(observation.history.get(name, [])) >= self.experimental_min_history
        )

    @staticmethod
    def _decision_score(raw_score: float, threshold: float) -> float:
        if raw_score >= threshold:
            return min(
                1.0,
                0.60 + 0.40 * ((raw_score - threshold) / max(1.0 - threshold, 1e-9)),
            )
        return max(0.0, 0.60 * (raw_score / max(threshold, 1e-9)))

    def evaluate(self, observation: RadarObservation) -> DetectorResult | None:
        profile = self.trusted_profile
        if profile is None:
            if observation.context.get("pyod_experimental") is not True:
                return None
            feature_names = self._experimental_features(observation)
            min_history = self.experimental_min_history
            detector_weights = {name: 1.0 for name in PYOD_DETECTORS}
            threshold: float | None = None
            trust_boundary = "request_experimental"
            approved = False
            profile_version = "experimental-unbenchmarked"
            source_type = "synthetic_test"
        else:
            feature_names = profile.feature_names
            min_history = profile.min_history
            detector_weights = profile.detector_weights
            threshold = profile.threshold
            trust_boundary = "trusted_runtime"
            approved = profile.production_approved
            profile_version = profile.version
            source_type = profile.source_type

        matrix = self._history_matrix(observation, feature_names, min_history)
        if matrix is None:
            return None
        training_rows, current, scaling = matrix
        train_matrix = _as_matrix(training_rows)
        current_matrix = _as_matrix([current])

        detector_percentiles: dict[str, float] = {}
        raw_scores: dict[str, float] = {}
        for name in sorted(detector_weights):
            model = _model(name)
            model.fit(train_matrix)
            train_scores = [float(value) for value in model.decision_scores_]
            raw_score = float(model.decision_function(current_matrix)[0])
            raw_scores[name] = raw_score
            detector_percentiles[name] = _percentile(train_scores, raw_score)

        weight_total = sum(detector_weights.values())
        ensemble_score = sum(
            detector_percentiles[name] * weight
            for name, weight in detector_weights.items()
        ) / weight_total
        if threshold is None:
            decision = False
            mapped_score = min(0.59, ensemble_score * 0.59)
        else:
            decision = ensemble_score >= threshold
            mapped_score = self._decision_score(ensemble_score, threshold)
            if not approved:
                mapped_score = min(0.59, mapped_score)
        level = EvidenceLevel.INFERENCE if approved else EvidenceLevel.HYPOTHESIS
        summary = (
            "Benchmarked PyOD ensemble detected an anomalous multivariate state"
            if approved and decision
            else "Benchmarked PyOD ensemble remained below its promoted threshold"
            if approved
            else "Experimental PyOD ensemble evaluated; no production alert promotion"
        )
        return DetectorResult(
            detector=self.name,
            score=mapped_score,
            level=level,
            summary=summary,
            attributes={
                "pattern": "pyod_outlier_ensemble",
                "ensemble_score": ensemble_score,
                "ensemble_threshold": threshold,
                "ensemble_decision": decision if approved else False,
                "alert_eligible": approved and decision,
                "production_approved": approved,
                "trust_boundary": trust_boundary,
                "profile_version": profile_version,
                "profile_source_type": source_type,
                "feature_names": feature_names,
                "history_rows": len(training_rows),
                "feature_scaling": scaling,
                "detector_weights": detector_weights,
                "detector_percentiles": detector_percentiles,
                "detector_raw_scores": raw_scores,
                "pyod_library_version": package_version("pyod"),
                "numpy_library_version": package_version("numpy"),
                "causal_claim": False,
                "detector_version": self.version,
            },
        )
