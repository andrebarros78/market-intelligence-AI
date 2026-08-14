from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from market_intelligence.persistence.models import Base, JsonType


class AlertOutcomeRecord(Base):
    __tablename__ = "alert_outcomes"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_alert_outcomes_dedupe_key"),
        Index("ix_alert_outcomes_alert_decided", "alert_id", "decided_at", "created_at"),
        Index(
            "ix_alert_outcomes_detector_eligible",
            "detector_version_snapshot",
            "calibration_eligible",
            "decided_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    alert_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    cause_classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JsonType, nullable=False, default=list)
    detector_version_snapshot: Mapped[str | None] = mapped_column(String(160), nullable=True)
    calibration_eligible: Mapped[bool] = mapped_column(nullable=False, default=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    causal_claim: Mapped[bool] = mapped_column(nullable=False, default=False)
    platform_internal_cause_confirmed: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
