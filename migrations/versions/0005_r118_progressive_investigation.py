"""R1.18 progressive investigation persistence.

Revision ID: 0005_r118_investigation
Revises: 0004_r15_evidence
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_r118_investigation"
down_revision = "0004_r15_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("active_key", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("anomalous_observation_count", sa.Integer(), nullable=False),
        sa.Column("anomaly_streak", sa.Integer(), nullable=False),
        sa.Column("normal_streak", sa.Integer(), nullable=False),
        sa.Column("ever_confirmed", sa.Boolean(), nullable=False),
        sa.Column(
            "hypotheses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(length=160), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_investigation_cases_confidence",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_key", name="uq_investigation_cases_active_key"),
    )
    op.create_index(
        "ix_investigation_cases_entity_updated",
        "investigation_cases",
        ["marketplace", "entity_type", "entity_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "investigation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finding_hash", sa.String(length=64), nullable=False),
        sa.Column("status_before", sa.String(length=32), nullable=True),
        sa.Column("status_after", sa.String(length=32), nullable=False),
        sa.Column("anomalous", sa.Boolean(), nullable=False),
        sa.Column("finding_score", sa.Float(), nullable=False),
        sa.Column("confidence_before", sa.Float(), nullable=True),
        sa.Column("confidence_after", sa.Float(), nullable=False),
        sa.Column("confidence_delta", sa.Float(), nullable=False),
        sa.Column(
            "evidence_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "hypotheses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(length=160), nullable=False),
        sa.Column("causal_claim", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["investigation_cases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_investigation_events_dedupe_key"),
    )
    op.create_index(
        "ix_investigation_events_case_id",
        "investigation_events",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_investigation_events_case_observed",
        "investigation_events",
        ["case_id", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_investigation_events_case_observed", table_name="investigation_events")
    op.drop_index("ix_investigation_events_case_id", table_name="investigation_events")
    op.drop_table("investigation_events")
    op.drop_index("ix_investigation_cases_entity_updated", table_name="investigation_cases")
    op.drop_table("investigation_cases")
