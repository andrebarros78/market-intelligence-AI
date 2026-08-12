from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceLevel(StrEnum):
    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertState(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class EntityRef(BaseModel):
    marketplace: str
    entity_type: str
    entity_id: str


class Evidence(BaseModel):
    level: EvidenceLevel
    statement: str
    source: str
    observed_at: datetime
    attributes: dict[str, Any] = Field(default_factory=dict)


class Alert(BaseModel):
    entity: EntityRef
    observed_change: str
    evidence: list[Evidence]
    severity: Severity
    estimated_impact: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: str | None = None
    responsible: str | None = None
    deadline: datetime | None = None
    state: AlertState = AlertState.OPEN
    outcome: str | None = None
