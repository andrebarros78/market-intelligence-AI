"""Sovereign continuous learning persistence.

Revision ID: 0008_sovereign_learning
Revises: 0007_ai_inference_audit
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_sovereign_learning"
down_revision = "0007_ai_inference_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("official_resource_fetched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("causal_claim", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hypotheses", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("feedback_targets", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("watchdogs", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_learning_episodes_dedupe_key"),
    )
    op.create_index(
        "ix_learning_episodes_marketplace_state",
        "learning_episodes",
        ["marketplace", "state", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_learning_episodes_entity",
        "learning_episodes",
        ["marketplace", "entity_type", "entity_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "learning_promotions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("regression_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("independent_verifier_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("watchdog_passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("candidate_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["learning_episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id", "target", name="uq_learning_promotions_episode_target"),
    )
    op.create_index(
        "ix_learning_promotions_status",
        "learning_promotions",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "learning_checkpoints",
        sa.Column("mission_id", sa.String(length=160), nullable=False),
        sa.Column("checkpoint_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("marketplace_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("mission_id"),
    )


def downgrade() -> None:
    op.drop_table("learning_checkpoints")
    op.drop_index("ix_learning_promotions_status", table_name="learning_promotions")
    op.drop_table("learning_promotions")
    op.drop_index("ix_learning_episodes_entity", table_name="learning_episodes")
    op.drop_index("ix_learning_episodes_marketplace_state", table_name="learning_episodes")
    op.drop_table("learning_episodes")
