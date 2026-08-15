from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from market_intelligence.persistence.models import Base, JsonType


class LearningEpisodeRecord(Base):
    __tablename__ = "learning_episodes"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_learning_episodes_dedupe_key"),
        Index("ix_learning_episodes_marketplace_state", "marketplace", "state", "updated_at"),
        Index("ix_learning_episodes_entity", "marketplace", "entity_type", "entity_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(160), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    official_resource_fetched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    causal_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_summary: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    hypotheses: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    feedback_targets: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    watchdogs: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class LearningPromotionRecord(Base):
    __tablename__ = "learning_promotions"
    __table_args__ = (
        UniqueConstraint("episode_id", "target", name="uq_learning_promotions_episode_target"),
        Index("ix_learning_promotions_status", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(ForeignKey("learning_episodes.id", ondelete="CASCADE"), nullable=False)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    regression_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    independent_verifier_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watchdog_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    candidate_payload: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LearningCheckpointRecord(Base):
    __tablename__ = "learning_checkpoints"

    mission_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    checkpoint_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    marketplace_writes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
