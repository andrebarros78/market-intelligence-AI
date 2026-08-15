"""Sovereign intelligence and counterintelligence core persistence.

Revision ID: 0009_sovereign_intelligence_core
Revises: 0008_sovereign_learning
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_sovereign_intelligence_core"
down_revision = "0008_sovereign_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sovereign_intelligence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("signal_kind", sa.String(length=160), nullable=False),
        sa.Column("knowledge_state", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_sovereign_intelligence_confidence"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_sovereign_intelligence_dedupe_key"),
    )
    op.create_index(
        "ix_sovereign_intelligence_entity_observed",
        "sovereign_intelligence",
        ["marketplace", "entity_type", "entity_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_sovereign_intelligence_state_severity",
        "sovereign_intelligence",
        ["knowledge_state", "severity"],
        unique=False,
    )

    op.create_table(
        "exposure_map",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exposure_key", sa.String(length=64), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("data_point", sa.String(length=160), nullable=False),
        sa.Column("platform_observes", sa.Text(), nullable=False),
        sa.Column("possible_inferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("mitigation", sa.Text(), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exposure_key", name="uq_exposure_map_exposure_key"),
    )
    op.create_index(
        "ix_exposure_map_marketplace_risk",
        "exposure_map",
        ["marketplace", "risk_level", "last_observed_at"],
        unique=False,
    )

    op.create_table(
        "cognitive_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=160), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("audit_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_cognitive_audits_dedupe_key"),
    )
    op.create_index("ix_cognitive_audits_created", "cognitive_audits", ["passed", "created_at"], unique=False)

    op.create_table(
        "sovereign_core_checkpoints",
        sa.Column("mission_id", sa.String(length=160), nullable=False),
        sa.Column("cursor_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("marketplace_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("marketplace_writes = 0", name="ck_sovereign_core_checkpoint_no_writes"),
        sa.PrimaryKeyConstraint("mission_id"),
    )


def downgrade() -> None:
    op.drop_table("sovereign_core_checkpoints")
    op.drop_index("ix_cognitive_audits_created", table_name="cognitive_audits")
    op.drop_table("cognitive_audits")
    op.drop_index("ix_exposure_map_marketplace_risk", table_name="exposure_map")
    op.drop_table("exposure_map")
    op.drop_index("ix_sovereign_intelligence_state_severity", table_name="sovereign_intelligence")
    op.drop_index("ix_sovereign_intelligence_entity_observed", table_name="sovereign_intelligence")
    op.drop_table("sovereign_intelligence")
