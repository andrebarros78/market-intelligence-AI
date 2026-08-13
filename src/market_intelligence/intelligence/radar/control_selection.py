from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from market_intelligence.intelligence.radar.models import RadarObservation


class ControlCandidate(BaseModel):
    entity_id: str = Field(min_length=1)
    metrics: dict[str, float]
    history: dict[str, list[float]] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SelectedControl:
    entity_id: str
    similarity: float
    metrics: dict[str, float]
    history: dict[str, list[float]]
    attributes: dict[str, Any]
    source: str = "automatic"


@dataclass(frozen=True, slots=True)
class ControlSelection:
    metric: str
    controls: tuple[SelectedControl, ...]
    candidate_count: int
    eligible_count: int
    excluded: dict[str, int]
    version: str

    def audit(self) -> dict[str, Any]:
        return {
            "mode": "automatic",
            "selector_version": self.version,
            "metric": self.metric,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "selected_count": len(self.controls),
            "selected_entity_ids": [item.entity_id for item in self.controls],
            "selected_similarities": [item.similarity for item in self.controls],
            "excluded": dict(sorted(self.excluded.items())),
        }


def _robust_scale(values: list[float]) -> float:
    if not values:
        return 1.0
    center = float(statistics.median(values))
    mad = float(statistics.median(abs(value - center) for value in values))
    steps = [abs(right - left) for left, right in zip(values, values[1:])]
    step = float(statistics.median(steps)) if steps else 0.0
    return max(mad, step, abs(center) * 0.02, 1e-9)


def _normalized(values: list[float]) -> list[float]:
    center = float(statistics.median(values))
    scale = _robust_scale(values)
    return [(value - center) / scale for value in values]


def _direction(left: float, right: float, *, tolerance: float = 1e-12) -> int:
    delta = right - left
    if abs(delta) <= tolerance:
        return 0
    return 1 if delta > 0 else -1


def historical_similarity(target: list[float], candidate: list[float], *, min_history: int = 8) -> float | None:
    overlap = min(len(target), len(candidate))
    if overlap < min_history:
        return None
    target_window = [float(value) for value in target[-overlap:]]
    candidate_window = [float(value) for value in candidate[-overlap:]]
    target_normalized = _normalized(target_window)
    candidate_normalized = _normalized(candidate_window)
    shape_distance = float(
        statistics.median(
            abs(left - right)
            for left, right in zip(target_normalized, candidate_normalized)
        )
    )
    shape_similarity = 1.0 / (1.0 + shape_distance)
    target_directions = [
        _direction(left, right) for left, right in zip(target_window, target_window[1:])
    ]
    candidate_directions = [
        _direction(left, right) for left, right in zip(candidate_window, candidate_window[1:])
    ]
    if target_directions:
        direction_agreement = sum(
            1 for left, right in zip(target_directions, candidate_directions) if left == right
        ) / len(target_directions)
    else:
        direction_agreement = 1.0
    similarity = 0.70 * shape_similarity + 0.30 * direction_agreement
    return max(0.0, min(1.0, similarity))


class AutomaticControlSelector:
    version = "auto-control-selector@1.0.0"

    def __init__(
        self,
        *,
        min_history: int = 8,
        min_similarity: float = 0.70,
        max_controls: int = 8,
    ) -> None:
        if min_history < 6:
            raise ValueError("min_history must be at least 6")
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between 0 and 1")
        if max_controls < 3:
            raise ValueError("max_controls must be at least 3")
        self.min_history = min_history
        self.min_similarity = min_similarity
        self.max_controls = max_controls

    @staticmethod
    def _declared_ineligible(candidate: ControlCandidate) -> bool:
        return candidate.attributes.get("control_eligible") is False

    @staticmethod
    def _declared_contaminated(candidate: ControlCandidate) -> bool:
        return candidate.attributes.get("contaminated") is True

    def _candidates(self, observation: RadarObservation) -> list[ControlCandidate]:
        raw = observation.context.get("control_candidates", [])
        if not isinstance(raw, list):
            return []
        parsed: list[ControlCandidate] = []
        for item in raw:
            try:
                parsed.append(ControlCandidate.model_validate(item))
            except ValidationError:
                continue
        return parsed

    def select(self, observation: RadarObservation, metric: str) -> ControlSelection:
        candidates = self._candidates(observation)
        excluded: dict[str, int] = {}
        target_history = observation.history.get(metric, [])
        selected_by_id: dict[str, SelectedControl] = {}
        eligible_count = 0

        def reject(reason: str) -> None:
            excluded[reason] = excluded.get(reason, 0) + 1

        for candidate in candidates:
            if candidate.entity_id == observation.entity_id:
                reject("self_reference")
                continue
            if self._declared_ineligible(candidate):
                reject("declared_ineligible")
                continue
            if self._declared_contaminated(candidate):
                reject("declared_contaminated")
                continue
            if metric not in candidate.metrics:
                reject("missing_metric")
                continue
            candidate_history = candidate.history.get(metric, [])
            similarity = historical_similarity(
                target_history,
                candidate_history,
                min_history=self.min_history,
            )
            if similarity is None:
                reject("insufficient_history")
                continue
            eligible_count += 1
            if similarity < self.min_similarity:
                reject("low_similarity")
                continue
            control = SelectedControl(
                entity_id=candidate.entity_id,
                similarity=similarity,
                metrics=candidate.metrics,
                history=candidate.history,
                attributes={**candidate.attributes, "selector_version": self.version},
            )
            previous = selected_by_id.get(control.entity_id)
            if previous is None or control.similarity > previous.similarity:
                selected_by_id[control.entity_id] = control

        controls = tuple(
            sorted(
                selected_by_id.values(),
                key=lambda item: (-item.similarity, item.entity_id),
            )[: self.max_controls]
        )
        if len(selected_by_id) > self.max_controls:
            excluded["over_limit"] = len(selected_by_id) - self.max_controls
        return ControlSelection(
            metric=metric,
            controls=controls,
            candidate_count=len(candidates),
            eligible_count=eligible_count,
            excluded=excluded,
            version=self.version,
        )
