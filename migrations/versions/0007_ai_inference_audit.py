"""IA-06 minimized inference audit persistence.

Revision ID: 0007_ai_inference_audit
Revises: 0006_r119_outcome_feedback
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_ai_inference_audit"
down_revision = "0006_r119_outcome_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_inference_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("endpoint_host", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=160), nullable=False),
        sa.Column("gateway_policy_version", sa.String(length=160), nullable=False),
        sa.Column("gateway_output_sha256", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=160), nullable=False),
        sa.Column("prompt_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_class", sa.String(length=32), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key", name="uq_ai_inference_audits_request_key"),
    )
    op.create_index(
        "ix_ai_inference_audits_role_created",
        "ai_inference_audits",
        ["role", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_ai_inference_audits_provider_model",
        "ai_inference_audits",
        ["provider", "model", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_inference_audits_provider_model", table_name="ai_inference_audits")
    op.drop_index("ix_ai_inference_audits_role_created", table_name="ai_inference_audits")
    op.drop_table("ai_inference_audits")
