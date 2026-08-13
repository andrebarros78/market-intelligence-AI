"""R1.5 Radar evidence contract.

Revision ID: 0004_r15_evidence
Revises: 0003_r13_radar
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_r15_evidence"
down_revision = "0003_r13_radar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("evidence_classification", sa.String(length=32), nullable=True))
    op.add_column(
        "alerts",
        sa.Column(
            "observable_causes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("alerts", sa.Column("unexplained_residual", sa.Float(), nullable=True))
    op.add_column(
        "alerts",
        sa.Column(
            "hypotheses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "alerts",
        sa.Column("control_comparison", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("alerts", sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("detector_version", sa.String(length=160), nullable=True))


def downgrade() -> None:
    op.drop_column("alerts", "detector_version")
    op.drop_column("alerts", "last_observed_at")
    op.drop_column("alerts", "first_observed_at")
    op.drop_column("alerts", "control_comparison")
    op.drop_column("alerts", "hypotheses")
    op.drop_column("alerts", "unexplained_residual")
    op.drop_column("alerts", "observable_causes")
    op.drop_column("alerts", "evidence_classification")
