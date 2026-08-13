from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    evidence_classification: EvidenceLevel | None = None
    severity: Severity
    estimated_impact: float | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    observable_causes: list[str] = Field(default_factory=list)
    unexplained_residual: float | None = None
    hypotheses: list[str] = Field(default_factory=list)
    control_comparison: dict[str, Any] | None = None
    recommended_action: str | None = None
    responsible: str | None = None
    deadline: datetime | None = None
    state: AlertState = AlertState.OPEN
    outcome: str | None = None
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    detector_version: str | None = None

    @model_validator(mode="after")
    def derive_epistemic_and_temporal_defaults(self) -> "Alert":
        if self.evidence_classification is None:
            levels = {item.level for item in self.evidence}
            if EvidenceLevel.HYPOTHESIS in levels or self.hypotheses:
                self.evidence_classification = EvidenceLevel.HYPOTHESIS
            elif EvidenceLevel.INFERENCE in levels:
                self.evidence_classification = EvidenceLevel.INFERENCE
            else:
                self.evidence_classification = EvidenceLevel.FACT
        if self.evidence:
            observed = [item.observed_at for item in self.evidence]
            if self.first_observed_at is None:
                self.first_observed_at = min(observed)
            if self.last_observed_at is None:
                self.last_observed_at = max(observed)
        if (
            self.first_observed_at is not None
            and self.last_observed_at is not None
            and self.last_observed_at < self.first_observed_at
        ):
            raise ValueError("last_observed_at cannot precede first_observed_at")
        return self
