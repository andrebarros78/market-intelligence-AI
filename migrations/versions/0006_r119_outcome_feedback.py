"""R1.19 posterior outcome feedback persistence.

Revision ID: 0006_r119_outcome_feedback
Revises: 0005_r118_investigation
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_r119_outcome_feedback"
down_revision = "0005_r118_investigation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("alert_id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("cause_classification", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=160), nullable=True),
        sa.Column("reason_code", sa.String(length=160), nullable=True),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("detector_version_snapshot", sa.String(length=160), nullable=True),
        sa.Column("calibration_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("causal_claim", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "platform_internal_cause_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_alert_outcomes_dedupe_key"),
    )
    op.create_index("ix_alert_outcomes_alert_id", "alert_outcomes", ["alert_id"], unique=False)
    op.create_index(
        "ix_alert_outcomes_alert_decided",
        "alert_outcomes",
        ["alert_id", "decided_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_alert_outcomes_detector_eligible",
        "alert_outcomes",
        ["detector_version_snapshot", "calibration_eligible", "decided_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_outcomes_detector_eligible", table_name="alert_outcomes")
    op.drop_index("ix_alert_outcomes_alert_decided", table_name="alert_outcomes")
    op.drop_index("ix_alert_outcomes_alert_id", table_name="alert_outcomes")
    op.drop_table("alert_outcomes")
