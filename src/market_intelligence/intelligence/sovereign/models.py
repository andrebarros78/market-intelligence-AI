from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeState(StrEnum):
    HYPOTHESIS = "hypothesis"
    OBSERVED = "observed"
    CORRELATED = "correlated"
    TESTED = "tested"
    VALIDATED = "validated"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AutonomyLevel(StrEnum):
    OBSERVE = "observe"
    RECOMMEND = "recommend"
    AUTOMATE_SAFE = "automate_safe"
    LIMITED_AUTONOMY = "limited_autonomy"
    HUMAN_REQUIRED = "human_required"


class SignalEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str = Field(min_length=1, max_length=160)
    marketplace: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(min_length=1, max_length=64)
    entity_id: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=160)
    source: str = Field(min_length=1, max_length=160)
    observed_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    official_resource_fetched: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ProbePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    questions: tuple[str, ...] = ()
    missing_surfaces: tuple[str, ...] = ()
    next_observations: tuple[str, ...] = ()
    priority: Severity = Severity.INFO


class CorrelationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    related_signal_ids: tuple[str, ...] = ()
    shared_dimensions: tuple[str, ...] = ()
    numeric_changes: dict[str, float] = Field(default_factory=dict)
    strength: float = Field(default=0.0, ge=0.0, le=1.0)
    fact_eligible: bool = False
    reason: str = ""


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    statement: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    falsifier: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    causal_claim: bool = False


class ExperimentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_type: str
    objective: str
    control: str
    treatment: str
    measures: tuple[str, ...]
    marketplace_write_required: bool = False
    requires_action_gateway: bool = False
    executable_now: bool = False
    reason: str


class IntelligenceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classification: str
    summary: str
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    opportunity: bool = False
    threat: bool = False
    development_need: str | None = None
    evidence: tuple[str, ...] = ()


class ExposureAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_point: str
    platform_observes: str
    possible_inferences: tuple[str, ...]
    risk: Severity
    mitigation: str
    evidence: tuple[str, ...] = ()


class ValidationVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: KnowledgeState
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_sufficient: bool
    provenance_complete: bool
    repeated_observation: bool
    causal_validated: bool
    reason: str


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prediction_type: Literal["FORECAST", "ABSTAIN"] = "ABSTAIN"
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    horizon: str
    leading_indicators: tuple[str, ...] = ()
    falsifier: str
    state: KnowledgeState = KnowledgeState.HYPOTHESIS
    abstention_reason: str | None = None
    target_entity: str | None = None
    target_metric: str | None = None
    operator: str | None = None
    expected_value: Any | None = None
    expected_direction: str | None = None
    baseline_value: Any | None = None
    baseline_source: str | None = None
    baseline_observed_at: datetime | None = None
    tolerance: float | None = Field(default=None, ge=0.0)
    evaluation_window: dict[str, Any] | None = None
    evidence_source: str | None = None
    created_at: datetime | None = None


class ActionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_type: str
    target: str
    recommendation: str
    autonomy_level: AutonomyLevel
    risk: Severity
    reversible: bool
    direct_marketplace_write: bool = False
    requires_action_gateway: bool = True
    requires_human_approval: bool = True
    rationale: str


class CognitiveAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    issues: tuple[str, ...] = ()
    overconfidence_detected: bool = False
    contradiction_detected: bool = False
    unsafe_authority_detected: bool = False
    calibration_action: str | None = None


class CoreCycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    core_version: str
    signal: SignalEnvelope
    probe: ProbePlan
    correlation: CorrelationFinding
    hypotheses: tuple[Hypothesis, ...]
    experiment: ExperimentPlan
    intelligence: IntelligenceAssessment
    counterintelligence: tuple[ExposureAssessment, ...]
    validation: ValidationVerdict
    learning: dict[str, Any]
    prediction: Prediction
    action_intent: ActionIntent
    audit: CognitiveAudit
    marketplace_writes: int = 0
