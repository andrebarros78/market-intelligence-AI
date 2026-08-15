from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from market_intelligence.persistence.models import Base, JsonType


class SovereignIntelligenceRecord(Base):
    __tablename__ = "sovereign_intelligence"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_sovereign_intelligence_confidence"),
        UniqueConstraint("dedupe_key", name="uq_sovereign_intelligence_dedupe_key"),
        Index(
            "ix_sovereign_intelligence_entity_observed",
            "marketplace",
            "entity_type",
            "entity_id",
            "observed_at",
        ),
        Index("ix_sovereign_intelligence_state_severity", "knowledge_state", "severity"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    signal_kind: Mapped[str] = mapped_column(String(160), nullable=False)
    knowledge_state: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ExposureMapRecord(Base):
    __tablename__ = "exposure_map"
    __table_args__ = (
        UniqueConstraint("exposure_key", name="uq_exposure_map_exposure_key"),
        Index("ix_exposure_map_marketplace_risk", "marketplace", "risk_level", "last_observed_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    exposure_key: Mapped[str] = mapped_column(String(64), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    data_point: Mapped[str] = mapped_column(String(160), nullable=False)
    platform_observes: Mapped[str] = mapped_column(Text, nullable=False)
    possible_inferences: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    mitigation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CognitiveAuditRecord(Base):
    __tablename__ = "cognitive_audits"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_cognitive_audits_dedupe_key"),
        Index("ix_cognitive_audits_created", "passed", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_id: Mapped[str] = mapped_column(String(160), nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    audit_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SovereignCoreCheckpointRecord(Base):
    __tablename__ = "sovereign_core_checkpoints"
    __table_args__ = (
        CheckConstraint("marketplace_writes = 0", name="ck_sovereign_core_checkpoint_no_writes"),
    )

    mission_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    cursor_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marketplace_writes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
