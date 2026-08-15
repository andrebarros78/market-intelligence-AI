from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from market_intelligence.persistence.models import Base, JsonType


class SovereignMissionRecord(Base):
    __tablename__="sovereign_missions"
    __table_args__=(CheckConstraint("marketplace_writes = 0",name="ck_sovereign_missions_no_writes"),CheckConstraint("priority >= 0 AND priority <= 100",name="ck_sovereign_missions_priority"),CheckConstraint("origin IN ('USER','GPT','RADAR','SYSTEM')",name="ck_sovereign_missions_origin"),CheckConstraint("mission_type IN ('DIRECTED','AUTONOMOUS')",name="ck_sovereign_missions_type"),UniqueConstraint("dedupe_key",name="uq_sovereign_missions_dedupe_key"),Index("ix_sovereign_missions_status_priority","status","priority","created_at"),Index("ix_sovereign_missions_origin_created","origin","created_at"))
    mission_id:Mapped[str]=mapped_column(String(64),primary_key=True); dedupe_key:Mapped[str|None]=mapped_column(String(64),nullable=True)
    origin:Mapped[str]=mapped_column(String(16),nullable=False); objective:Mapped[str]=mapped_column(Text,nullable=False); mission_type:Mapped[str]=mapped_column(String(16),nullable=False)
    marketplace_scope:Mapped[list]=mapped_column(JsonType,nullable=False,default=list); authority:Mapped[str]=mapped_column(String(64),nullable=False); priority:Mapped[int]=mapped_column(Integer,nullable=False,default=50); status:Mapped[str]=mapped_column(String(24),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now()); started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now()); completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); deadline_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    checkpoint:Mapped[dict]=mapped_column(JsonType,nullable=False,default=dict); error_code:Mapped[str|None]=mapped_column(String(160),nullable=True); retry_count:Mapped[int]=mapped_column(Integer,nullable=False,default=0); marketplace_writes:Mapped[int]=mapped_column(Integer,nullable=False,default=0)


class MissionStepRecord(Base):
    __tablename__="mission_steps"; __table_args__=(UniqueConstraint("mission_id","step_key",name="uq_mission_steps_key"),Index("ix_mission_steps_mission_state","mission_id","state","started_at"))
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4); mission_id:Mapped[str]=mapped_column(String(64),ForeignKey("sovereign_missions.mission_id",ondelete="CASCADE"),nullable=False); step_key:Mapped[str]=mapped_column(String(64),nullable=False); state:Mapped[str]=mapped_column(String(24),nullable=False); status:Mapped[str]=mapped_column(String(24),nullable=False); attempt:Mapped[int]=mapped_column(Integer,nullable=False,default=1); checkpoint:Mapped[dict]=mapped_column(JsonType,nullable=False,default=dict); started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now()); completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); error_code:Mapped[str|None]=mapped_column(String(160),nullable=True)


class MissionEvidenceRecord(Base):
    __tablename__="mission_evidence"; __table_args__=(UniqueConstraint("mission_id","dedupe_key",name="uq_mission_evidence_dedupe"),Index("ix_mission_evidence_mission_observed","mission_id","observed_at"))
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4); mission_id:Mapped[str]=mapped_column(String(64),ForeignKey("sovereign_missions.mission_id",ondelete="CASCADE"),nullable=False); dedupe_key:Mapped[str]=mapped_column(String(64),nullable=False); evidence_type:Mapped[str]=mapped_column(String(64),nullable=False); source:Mapped[str]=mapped_column(String(160),nullable=False); observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False); evidence_json:Mapped[dict]=mapped_column(JsonType,nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class MissionFindingRecord(Base):
    __tablename__="mission_findings"; __table_args__=(CheckConstraint("confidence >= 0 AND confidence <= 1",name="ck_mission_findings_confidence"),UniqueConstraint("mission_id","dedupe_key",name="uq_mission_findings_dedupe"),Index("ix_mission_findings_mission_state","mission_id","knowledge_state","severity"))
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4); mission_id:Mapped[str]=mapped_column(String(64),ForeignKey("sovereign_missions.mission_id",ondelete="CASCADE"),nullable=False); dedupe_key:Mapped[str]=mapped_column(String(64),nullable=False); finding_type:Mapped[str]=mapped_column(String(64),nullable=False); knowledge_state:Mapped[str]=mapped_column(String(32),nullable=False); severity:Mapped[str]=mapped_column(String(32),nullable=False); confidence:Mapped[float]=mapped_column(Float,nullable=False); finding_json:Mapped[dict]=mapped_column(JsonType,nullable=False); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class MissionReportRecord(Base):
    __tablename__="mission_reports"; __table_args__=(CheckConstraint("confidence >= 0 AND confidence <= 1",name="ck_mission_reports_confidence"),CheckConstraint("marketplace_writes = 0",name="ck_mission_reports_no_writes"),UniqueConstraint("mission_id",name="uq_mission_reports_mission"),Index("ix_mission_reports_created","created_at"))
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4); mission_id:Mapped[str]=mapped_column(String(64),ForeignKey("sovereign_missions.mission_id",ondelete="CASCADE"),nullable=False); report_version:Mapped[str]=mapped_column(String(32),nullable=False); report_json:Mapped[dict]=mapped_column(JsonType,nullable=False); report_markdown:Mapped[str]=mapped_column(Text,nullable=False); confidence:Mapped[float]=mapped_column(Float,nullable=False); marketplace_writes:Mapped[int]=mapped_column(Integer,nullable=False,default=0); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
