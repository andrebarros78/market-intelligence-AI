from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from market_intelligence.intelligence.radar.feedback import (
    AlertOutcomeSubmission,
    DetectorFeedbackReport,
    FeedbackCalibrationPolicy,
    OutcomeClassification,
    OutcomeSource,
    evaluate_feedback_calibration,
)


def test_human_feedback_requires_actor_and_timezone() -> None:
    with pytest.raises(ValidationError):
        AlertOutcomeSubmission(
            classification="confirmed",
            decided_at=datetime.now(UTC),
            source="human",
        )
    with pytest.raises(ValidationError):
        AlertOutcomeSubmission(
            classification="confirmed",
            decided_at=datetime.now().replace(tzinfo=None),
            source="human",
            actor="reviewer-1",
        )


def test_system_observed_cannot_claim_false_positive_or_internal_external_cause() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        AlertOutcomeSubmission(
            classification="false_positive",
            decided_at=now,
            source="system_observed",
        )
    with pytest.raises(ValidationError):
        AlertOutcomeSubmission(
            classification="resolved",
            cause_classification="external",
            decided_at=now,
            source="system_observed",
        )
    allowed = AlertOutcomeSubmission(
        classification="resolved",
        cause_classification="unidentified",
        decided_at=now,
        source="system_observed",
    )
    assert allowed.classification == OutcomeClassification.RESOLVED
    assert allowed.source == OutcomeSource.SYSTEM_OBSERVED


def test_synthetic_policy_cannot_be_production_approved() -> None:
    with pytest.raises(ValidationError):
        FeedbackCalibrationPolicy(
            version="synthetic-v1",
            source_type="synthetic_test",
            min_decisive_samples=10,
            max_false_positive_rate=0.10,
            min_validated_positive_rate=0.90,
            production_approved=True,
        )


def test_feedback_calibration_never_auto_applies() -> None:
    report = DetectorFeedbackReport(
        detector_version="detector@1.0.0",
        total_latest_outcomes=20,
        decisive_outcomes=20,
        validated_positive_count=19,
        false_positive_count=1,
        inconclusive_count=0,
        classification_counts={
            "confirmed": 19,
            "partially_confirmed": 0,
            "false_positive": 1,
            "inconclusive": 0,
            "resolved": 0,
            "persistent": 0,
        },
        cause_counts={"external": 0, "internal": 0, "unidentified": 20},
        false_positive_rate=0.05,
        validated_positive_rate=0.95,
    )
    policy = FeedbackCalibrationPolicy(
        version="homologated-v1",
        source_type="homologated",
        min_decisive_samples=20,
        max_false_positive_rate=0.05,
        min_validated_positive_rate=0.95,
        production_approved=True,
    )
    decision = evaluate_feedback_calibration(report, policy)
    assert decision.meets_metrics is True
    assert decision.production_eligible is True
    assert decision.auto_applied is False


def test_unapproved_policy_can_measure_but_not_promote() -> None:
    report = DetectorFeedbackReport(
        detector_version="detector@1.0.0",
        total_latest_outcomes=2,
        decisive_outcomes=2,
        validated_positive_count=2,
        false_positive_count=0,
        inconclusive_count=0,
        classification_counts={
            "confirmed": 2,
            "partially_confirmed": 0,
            "false_positive": 0,
            "inconclusive": 0,
            "resolved": 0,
            "persistent": 0,
        },
        cause_counts={"external": 0, "internal": 0, "unidentified": 2},
        false_positive_rate=0.0,
        validated_positive_rate=1.0,
    )
    policy = FeedbackCalibrationPolicy(
        version="lab-v1",
        source_type="synthetic_test",
        min_decisive_samples=2,
        max_false_positive_rate=0.0,
        min_validated_positive_rate=1.0,
        production_approved=False,
    )
    decision = evaluate_feedback_calibration(report, policy)
    assert decision.meets_metrics is True
    assert decision.production_eligible is False
    assert decision.auto_applied is False
