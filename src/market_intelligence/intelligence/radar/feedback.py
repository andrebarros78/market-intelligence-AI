from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OutcomeClassification(StrEnum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    FALSE_POSITIVE = "false_positive"
    INCONCLUSIVE = "inconclusive"
    RESOLVED = "resolved"
    PERSISTENT = "persistent"


class CauseClassification(StrEnum):
    EXTERNAL = "external"
    INTERNAL = "internal"
    UNIDENTIFIED = "unidentified"


class OutcomeSource(StrEnum):
    HUMAN = "human"
    VERIFIED_IMPORT = "verified_import"
    SYSTEM_OBSERVED = "system_observed"


class AlertOutcomeSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: OutcomeClassification
    cause_classification: CauseClassification | None = None
    decided_at: datetime
    source: OutcomeSource
    actor: str | None = Field(default=None, max_length=160)
    reason_code: str | None = Field(default=None, max_length=160)
    evidence_refs: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_trust_semantics(self) -> "AlertOutcomeSubmission":
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("decided_at must be timezone-aware")
        if self.source == OutcomeSource.HUMAN and not (self.actor or "").strip():
            raise ValueError("human outcome requires actor")
        if self.source == OutcomeSource.SYSTEM_OBSERVED:
            allowed = {
                OutcomeClassification.RESOLVED,
                OutcomeClassification.PERSISTENT,
                OutcomeClassification.INCONCLUSIVE,
            }
            if self.classification not in allowed:
                raise ValueError("system_observed cannot decide confirmation or false positive")
            if self.cause_classification not in {None, CauseClassification.UNIDENTIFIED}:
                raise ValueError("system_observed cannot assign internal/external cause")
        if any(not ref.strip() or len(ref) > 200 for ref in self.evidence_refs):
            raise ValueError("evidence_refs must be non-empty opaque references up to 200 chars")
        return self


class DetectorFeedbackReport(BaseModel):
    detector_version: str | None
    calibration_eligible_only: bool = True
    total_latest_outcomes: int = Field(ge=0)
    decisive_outcomes: int = Field(ge=0)
    validated_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    inconclusive_count: int = Field(ge=0)
    classification_counts: dict[str, int]
    cause_counts: dict[str, int]
    false_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    validated_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    causal_claim: bool = False
    platform_internal_cause_confirmed: bool = False


class FeedbackCalibrationPolicy(BaseModel):
    version: str = Field(min_length=1)
    source_type: Literal["homologated", "synthetic_test"]
    min_decisive_samples: int = Field(ge=1)
    max_false_positive_rate: float = Field(ge=0.0, le=1.0)
    min_validated_positive_rate: float = Field(ge=0.0, le=1.0)
    production_approved: bool = False

    @model_validator(mode="after")
    def validate_policy(self) -> "FeedbackCalibrationPolicy":
        if self.source_type == "synthetic_test" and self.production_approved:
            raise ValueError("synthetic feedback policy cannot be production approved")
        return self


class FeedbackCalibrationDecision(BaseModel):
    detector_version: str | None
    policy_version: str
    meets_metrics: bool
    production_eligible: bool
    reasons: list[str]
    auto_applied: bool = False


def evaluate_feedback_calibration(
    report: DetectorFeedbackReport,
    policy: FeedbackCalibrationPolicy,
) -> FeedbackCalibrationDecision:
    reasons: list[str] = []
    if report.decisive_outcomes < policy.min_decisive_samples:
        reasons.append("insufficient_decisive_samples")
    if report.false_positive_rate is None:
        reasons.append("false_positive_rate_unavailable")
    elif report.false_positive_rate > policy.max_false_positive_rate:
        reasons.append("false_positive_rate_above_policy")
    if report.validated_positive_rate is None:
        reasons.append("validated_positive_rate_unavailable")
    elif report.validated_positive_rate < policy.min_validated_positive_rate:
        reasons.append("validated_positive_rate_below_policy")
    meets_metrics = not reasons
    return FeedbackCalibrationDecision(
        detector_version=report.detector_version,
        policy_version=policy.version,
        meets_metrics=meets_metrics,
        production_eligible=bool(meets_metrics and policy.production_approved),
        reasons=reasons,
        auto_applied=False,
    )
