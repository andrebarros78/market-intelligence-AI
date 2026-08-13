"""R1.3 Radar vertical persistence.

Revision ID: 0003_r13_radar
Revises: 0002_r11_oauth
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_r13_radar"
down_revision = "0002_r11_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("operation", sa.String(length=160), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=160), nullable=True),
        sa.Column("request_id", sa.String(length=160), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_channel_events_dedupe_key"),
    )
    op.create_index(
        "ix_channel_events_marketplace_observed",
        "channel_events",
        ["marketplace", "observed_at"],
    )
    op.add_column("alerts", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_alerts_dedupe_key", "alerts", ["dedupe_key"])


def downgrade() -> None:
    op.drop_constraint("uq_alerts_dedupe_key", "alerts", type_="unique")
    op.drop_column("alerts", "dedupe_key")
    op.drop_index("ix_channel_events_marketplace_observed", table_name="channel_events")
    op.drop_table("channel_events")
