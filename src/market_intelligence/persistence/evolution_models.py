from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from market_intelligence.persistence.models import Base, JsonType


class SignalDictionaryRecord(Base):
    __tablename__ = "signal_dictionary"
    __table_args__ = (
        UniqueConstraint("marketplace", "signal_family", "source", "endpoint_or_topic", name="uq_signal_dictionary_identity"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_signal_dictionary_confidence"),
        Index("ix_signal_dictionary_family_updated", "signal_family", "updated_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_family: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    who_triggered_it: Mapped[str] = mapped_column(String(64), nullable=False)
    collector_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    endpoint_or_topic: Mapped[str] = mapped_column(String(320), nullable=False)
    what_we_requested: Mapped[str] = mapped_column(Text, nullable=False)
    what_marketplace_returned: Mapped[str] = mapped_column(Text, nullable=False)
    important_fields: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    temporal_behavior: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    known_meaning: Mapped[str] = mapped_column(Text, nullable=False)
    unknown_meaning: Mapped[str] = mapped_column(Text, nullable=False)
    business_relevance: Mapped[str] = mapped_column(Text, nullable=False)
    related_signals: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CognitiveQuestionRecord(Base):
    __tablename__ = "cognitive_questions"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_cognitive_questions_dedupe"),
        CheckConstraint("priority >= 0 AND priority <= 100", name="ck_cognitive_questions_priority"),
        CheckConstraint("expected_value >= 0 AND expected_value <= 1", name="ck_cognitive_questions_expected_value"),
        CheckConstraint("status IN ('OPEN','INVESTIGATING','ANSWERED','INCONCLUSIVE','REJECTED','REOPENED')", name="ck_cognitive_questions_status"),
        Index("ix_cognitive_questions_status_priority", "status", "priority", "created_at"),
    )
    question_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    priority_factors: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    related_entities: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    related_signals: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    evidence_required: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    investigation_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sovereign_missions.mission_id", ondelete="SET NULL"), nullable=True)
    answer_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PredictionEvaluationRecord(Base):
    __tablename__ = "prediction_evaluations"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_prediction_evaluations_dedupe"),
        CheckConstraint("confidence_before >= 0 AND confidence_before <= 1", name="ck_prediction_confidence_before"),
        CheckConstraint("confidence_after >= 0 AND confidence_after <= 1", name="ck_prediction_confidence_after"),
        CheckConstraint("marketplace_writes = 0", name="ck_prediction_evaluations_no_writes"),
        Index("ix_prediction_evaluations_due", "status", "evaluation_due_at"),
    )
    prediction_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_intelligence_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sovereign_intelligence.id", ondelete="SET NULL"), nullable=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(320), nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence_before: Mapped[float] = mapped_column(Float, nullable=False)
    expected_observation: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    evaluation_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_result: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    correct_or_incorrect: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    calibration_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_after: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marketplace_writes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class KnowledgeLifecycleRecord(Base):
    __tablename__ = "knowledge_lifecycle"
    __table_args__ = (
        UniqueConstraint("source_intelligence_id", name="uq_knowledge_lifecycle_source"),
        CheckConstraint("current_confidence >= 0 AND current_confidence <= 1", name="ck_knowledge_lifecycle_confidence"),
        CheckConstraint("state IN ('VALIDATED','AGING','REVALIDATION_REQUIRED','QUARANTINED','REJECTED','SUPERSEDED')", name="ck_knowledge_lifecycle_state"),
        Index("ix_knowledge_lifecycle_state_due", "state", "revalidation_due_at"),
    )
    knowledge_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_intelligence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sovereign_intelligence.id", ondelete="CASCADE"), nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revalidation_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    contradiction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    knowledge_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    last_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CommercialBaselineRecord(Base):
    __tablename__ = "commercial_baselines"
    __table_args__ = (
        UniqueConstraint("marketplace", "entity_type", "entity_id", "metric", name="uq_commercial_baselines_metric"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_commercial_baselines_confidence"),
        Index("ix_commercial_baselines_entity", "entity_type", "entity_id", "updated_at"),
    )
    baseline_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    baseline_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    current_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(160), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DriftEventRecord(Base):
    __tablename__ = "drift_events"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_drift_events_dedupe"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_drift_events_confidence"),
        CheckConstraint("state IN ('DETECTED','INVESTIGATING','CONFIRMED','REJECTED','RESOLVED')", name="ck_drift_events_state"),
        Index("ix_drift_events_state_detected", "state", "detected_at"),
    )
    drift_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_family: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    baseline_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    current_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    magnitude: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="DETECTED")
    mission_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sovereign_missions.mission_id", ondelete="SET NULL"), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LeadingSignalResearchRecord(Base):
    __tablename__ = "leading_signal_research"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_leading_signal_research_dedupe"),
        CheckConstraint("precision >= 0 AND precision <= 1", name="ck_leading_signal_precision"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_leading_signal_confidence"),
        Index("ix_leading_signal_research_state", "state", "updated_at"),
    )
    research_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    antecedent_family: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_family: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_group: Mapped[str] = mapped_column(String(160), nullable=False)
    lead_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    support: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    precision: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    false_positives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    false_negatives: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="INCONCLUSIVE")
    evidence_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class RejectedHypothesisRecord(Base):
    __tablename__ = "rejected_hypotheses"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_rejected_hypotheses_dedupe"),
        Index("ix_rejected_hypotheses_error", "error_class", "last_seen_at"),
    )
    rejected_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    error_class: Mapped[str] = mapped_column(String(64), nullable=False)
    lesson: Mapped[str] = mapped_column(Text, nullable=False)
    source_mission_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sovereign_missions.mission_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HumanDomainHypothesisRecord(Base):
    __tablename__ = "human_domain_hypotheses"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_human_domain_hypotheses_dedupe"),
        CheckConstraint("confidence_initial >= 0 AND confidence_initial <= 1", name="ck_human_domain_hypotheses_confidence"),
        Index("ix_human_domain_hypotheses_status", "status", "created_at"),
    )
    hypothesis_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="owner_domain_experience")
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    signal_family: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_initial: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    requires_validation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    mission_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("sovereign_missions.mission_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvolutionCycleRecord(Base):
    __tablename__ = "evolution_cycles"
    __table_args__ = (
        UniqueConstraint("cycle_key", name="uq_evolution_cycles_key"),
        CheckConstraint("marketplace_writes = 0", name="ck_evolution_cycles_no_writes"),
        Index("ix_evolution_cycles_completed", "completed_at"),
    )
    cycle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    cycle_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    summary_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    marketplace_writes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EvolutionMetricRecord(Base):
    __tablename__ = "evolution_metrics"
    __table_args__ = (
        CheckConstraint("marketplace_writes = 0", name="ck_evolution_metrics_no_writes"),
        Index("ix_evolution_metrics_observed", "observed_at"),
    )
    metric_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    understood_signal_families: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_signal_families: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    answered_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validated_knowledge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_knowledge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_knowledge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stale_knowledge: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predictions_made: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predictions_evaluated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predictions_correct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    predictions_incorrect: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calibration_error: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regime_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    autonomous_investigations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    false_patterns_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_hypotheses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_hypotheses_validated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marketplace_writes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
