"""Persistent Sovereign Mission Protocol tables.

Revision ID: 0010_sovereign_missions
Revises: 0009_sovereign_intelligence_core
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_sovereign_missions"
down_revision = "0009_sovereign_intelligence_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sovereign_missions",
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=True),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("mission_type", sa.String(length=16), nullable=False),
        sa.Column("marketplace_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("authority", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("marketplace_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("marketplace_writes = 0", name="ck_sovereign_missions_no_writes"),
        sa.CheckConstraint("priority >= 0 AND priority <= 100", name="ck_sovereign_missions_priority"),
        sa.CheckConstraint("origin IN ('USER','GPT','RADAR','SYSTEM')", name="ck_sovereign_missions_origin"),
        sa.CheckConstraint("mission_type IN ('DIRECTED','AUTONOMOUS')", name="ck_sovereign_missions_type"),
        sa.PrimaryKeyConstraint("mission_id"),
        sa.UniqueConstraint("dedupe_key", name="uq_sovereign_missions_dedupe_key"),
    )
    op.create_index("ix_sovereign_missions_status_priority", "sovereign_missions", ["status", "priority", "created_at"], unique=False)
    op.create_index("ix_sovereign_missions_origin_created", "sovereign_missions", ["origin", "created_at"], unique=False)

    op.create_table(
        "mission_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checkpoint", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "step_key", name="uq_mission_steps_key"),
    )
    op.create_index("ix_mission_steps_mission_state", "mission_steps", ["mission_id", "state", "started_at"], unique=False)

    op.create_table(
        "mission_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "dedupe_key", name="uq_mission_evidence_dedupe"),
    )
    op.create_index("ix_mission_evidence_mission_observed", "mission_evidence", ["mission_id", "observed_at"], unique=False)

    op.create_table(
        "mission_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("finding_type", sa.String(length=64), nullable=False),
        sa.Column("knowledge_state", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("finding_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mission_findings_confidence"),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "dedupe_key", name="uq_mission_findings_dedupe"),
    )
    op.create_index("ix_mission_findings_mission_state", "mission_findings", ["mission_id", "knowledge_state", "severity"], unique=False)

    op.create_table(
        "mission_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("report_version", sa.String(length=32), nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report_markdown", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("marketplace_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mission_reports_confidence"),
        sa.CheckConstraint("marketplace_writes = 0", name="ck_mission_reports_no_writes"),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", name="uq_mission_reports_mission"),
    )
    op.create_index("ix_mission_reports_created", "mission_reports", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mission_reports_created", table_name="mission_reports")
    op.drop_table("mission_reports")
    op.drop_index("ix_mission_findings_mission_state", table_name="mission_findings")
    op.drop_table("mission_findings")
    op.drop_index("ix_mission_evidence_mission_observed", table_name="mission_evidence")
    op.drop_table("mission_evidence")
    op.drop_index("ix_mission_steps_mission_state", table_name="mission_steps")
    op.drop_table("mission_steps")
    op.drop_index("ix_sovereign_missions_origin_created", table_name="sovereign_missions")
    op.drop_index("ix_sovereign_missions_status_priority", table_name="sovereign_missions")
    op.drop_table("sovereign_missions")
