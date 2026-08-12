from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from market_intelligence.core.contracts import EvidenceLevel


class RadarObservation(BaseModel):
    entity_id: str
    observed_at: datetime
    metrics: dict[str, float]
    history: dict[str, list[float]] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


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
