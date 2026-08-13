from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from market_intelligence.core.contracts import EvidenceLevel


class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float

    @model_validator(mode="after")
    def require_timezone(self) -> "TimeSeriesPoint":
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamped history requires timezone-aware timestamps")
        return self


class RadarObservation(BaseModel):
    entity_id: str
    observed_at: datetime
    metrics: dict[str, float]
    history: dict[str, list[float]] = Field(default_factory=dict)
    timestamped_history: dict[str, list[TimeSeriesPoint]] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_timestamped_history(self) -> "RadarObservation":
        if self.timestamped_history:
            if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
                raise ValueError(
                    "observed_at must be timezone-aware when timestamped_history is provided"
                )
            normalized: dict[str, list[TimeSeriesPoint]] = {}
            projected_history = dict(self.history)
            for metric, points in self.timestamped_history.items():
                ordered = sorted(points, key=lambda point: point.timestamp)
                timestamps = [point.timestamp for point in ordered]
                if len(timestamps) != len(set(timestamps)):
                    raise ValueError(
                        f"timestamped history for {metric} contains duplicate timestamps"
                    )
                normalized[metric] = ordered
                if metric not in projected_history:
                    projected_history[metric] = [float(point.value) for point in ordered]
            self.timestamped_history = normalized
            self.history = projected_history
        return self


class DetectorResult(BaseModel):
    detector: str
    score: float = Field(ge=0.0, le=1.0)
    level: EvidenceLevel
    summary: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class RadarFinding(BaseModel):
    entity_id: str
    score: float = Field(ge=0.0, le=1.0)
    anomalous: bool
    detector_results: list[DetectorResult]
