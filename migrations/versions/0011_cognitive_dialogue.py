"""Cognitive operational dialogue, lineage and intelligence inbox.

Revision ID: 0011_cognitive_dialogue
Revises: 0010_sovereign_missions
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_cognitive_dialogue"
down_revision = "0010_sovereign_missions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sovereign_missions", sa.Column("thread_id", sa.String(length=64), nullable=True))
    op.add_column("sovereign_missions", sa.Column("root_mission_id", sa.String(length=64), nullable=True))
    op.add_column("sovereign_missions", sa.Column("parent_mission_id", sa.String(length=64), nullable=True))
    op.add_column("sovereign_missions", sa.Column("source_report_id", sa.Uuid(), nullable=True))
    op.add_column("sovereign_missions", sa.Column("source_finding_id", sa.Uuid(), nullable=True))
    op.add_column("sovereign_missions", sa.Column("follow_up_question", sa.Text(), nullable=True))
    op.add_column(
        "sovereign_missions",
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="standard"),
    )
    op.execute(
        "UPDATE sovereign_missions SET thread_id=mission_id, root_mission_id=mission_id "
        "WHERE thread_id IS NULL OR root_mission_id IS NULL"
    )
    op.create_foreign_key(
        "fk_sovereign_missions_root",
        "sovereign_missions",
        "sovereign_missions",
        ["root_mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sovereign_missions_parent",
        "sovereign_missions",
        "sovereign_missions",
        ["parent_mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sovereign_missions_source_report",
        "sovereign_missions",
        "mission_reports",
        ["source_report_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sovereign_missions_source_finding",
        "sovereign_missions",
        "mission_findings",
        ["source_finding_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sovereign_missions_thread_created", "sovereign_missions", ["thread_id", "created_at"], unique=False)
    op.create_index("ix_sovereign_missions_parent", "sovereign_missions", ["parent_mission_id"], unique=False)

    op.create_table(
        "intelligence_threads",
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("root_mission_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["root_mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index("ix_intelligence_threads_updated", "intelligence_threads", ["updated_at"], unique=False)
    op.execute(
        """
        INSERT INTO intelligence_threads(thread_id,root_mission_id,title,status)
        SELECT mission_id,mission_id,left(objective,500),'ACTIVE'
        FROM sovereign_missions
        ON CONFLICT(thread_id) DO NOTHING
        """
    )

    op.create_table(
        "mission_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("plan_version", sa.String(length=48), nullable=False),
        sa.Column("objective_original", sa.Text(), nullable=False),
        sa.Column("main_question", sa.Text(), nullable=False),
        sa.Column("plan_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", name="uq_mission_plans_mission"),
    )

    op.create_table(
        "mission_iterations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("iteration_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("evidence_gain", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_before", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_after", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_change", sa.Float(), nullable=False, server_default="0"),
        sa.Column("open_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("stop_reason", sa.String(length=80), nullable=True),
        sa.Column("iteration_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("marketplace_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("iteration_count >= 1 AND iteration_count <= 8", name="ck_mission_iterations_safe_limit"),
        sa.CheckConstraint("evidence_gain >= 0", name="ck_mission_iterations_evidence_gain"),
        sa.CheckConstraint("marketplace_writes = 0", name="ck_mission_iterations_no_writes"),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "iteration_count", name="uq_mission_iterations_number"),
    )
    op.create_index("ix_mission_iterations_mission", "mission_iterations", ["mission_id", "iteration_count"], unique=False)

    op.create_table(
        "intelligence_inbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.String(length=64), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="UNREAD"),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("marketplace_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('UNREAD','READ','ACKNOWLEDGED')", name="ck_intelligence_inbox_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_intelligence_inbox_confidence"),
        sa.CheckConstraint("marketplace_writes = 0", name="ck_intelligence_inbox_no_writes"),
        sa.ForeignKeyConstraint(["mission_id"], ["sovereign_missions.mission_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["mission_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", name="uq_intelligence_inbox_report"),
    )
    op.create_index("ix_intelligence_inbox_status_created", "intelligence_inbox", ["status", "created_at"], unique=False)
    op.create_index("ix_intelligence_inbox_thread", "intelligence_inbox", ["thread_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_intelligence_inbox_thread", table_name="intelligence_inbox")
    op.drop_index("ix_intelligence_inbox_status_created", table_name="intelligence_inbox")
    op.drop_table("intelligence_inbox")
    op.drop_index("ix_mission_iterations_mission", table_name="mission_iterations")
    op.drop_table("mission_iterations")
    op.drop_table("mission_plans")
    op.drop_index("ix_intelligence_threads_updated", table_name="intelligence_threads")
    op.drop_table("intelligence_threads")
    op.drop_index("ix_sovereign_missions_parent", table_name="sovereign_missions")
    op.drop_index("ix_sovereign_missions_thread_created", table_name="sovereign_missions")
    op.drop_constraint("fk_sovereign_missions_source_finding", "sovereign_missions", type_="foreignkey")
    op.drop_constraint("fk_sovereign_missions_source_report", "sovereign_missions", type_="foreignkey")
    op.drop_constraint("fk_sovereign_missions_parent", "sovereign_missions", type_="foreignkey")
    op.drop_constraint("fk_sovereign_missions_root", "sovereign_missions", type_="foreignkey")
    op.drop_column("sovereign_missions", "mode")
    op.drop_column("sovereign_missions", "follow_up_question")
    op.drop_column("sovereign_missions", "source_finding_id")
    op.drop_column("sovereign_missions", "source_report_id")
    op.drop_column("sovereign_missions", "parent_mission_id")
    op.drop_column("sovereign_missions", "root_mission_id")
    op.drop_column("sovereign_missions", "thread_id")
