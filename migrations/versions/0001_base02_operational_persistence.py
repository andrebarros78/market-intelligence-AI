"""BASE-02 operational persistence.

Revision ID: 0001_base02
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_base02"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("external_id", sa.String(length=160), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dedupe_key", name="uq_raw_events_dedupe_key"),
    )
    op.create_index("ix_raw_events_source_received", "raw_events", ["source", "received_at"])

    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("current_hash", sa.String(length=64), nullable=False),
        sa.Column("current_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("marketplace", "entity_type", "entity_id", name="uq_entities_natural_key"),
    )
    op.create_index("ix_entities_marketplace_type", "entities", ["marketplace", "entity_type"])

    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint(
            "marketplace", "entity_type", "entity_id", "payload_hash", name="uq_snapshots_entity_hash"
        ),
    )
    op.create_index(
        "ix_snapshots_entity_captured",
        "snapshots",
        ["marketplace", "entity_type", "entity_id", "captured_at"],
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("observed_change", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("estimated_impact", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("responsible", sa.String(length=160), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_alerts_confidence"),
    )
    op.create_index("ix_alerts_state_severity", "alerts", ["state", "severity"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=160), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_evidence_alert_id", "evidence", ["alert_id"])
    op.create_index(
        "ix_evidence_entity_observed",
        "evidence",
        ["marketplace", "entity_type", "entity_id", "observed_at"],
    )

    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("verifier_envelope", sa.LargeBinary(), nullable=True),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("synthetic", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("state_hash", name="uq_oauth_states_state_hash"),
    )
    op.create_index("ix_oauth_states_marketplace_expires", "oauth_states", ["marketplace", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_oauth_states_marketplace_expires", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("ix_evidence_entity_observed", table_name="evidence")
    op.drop_index("ix_evidence_alert_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index("ix_alerts_state_severity", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_snapshots_entity_captured", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index("ix_entities_marketplace_type", table_name="entities")
    op.drop_table("entities")
    op.drop_index("ix_raw_events_source_received", table_name="raw_events")
    op.drop_table("raw_events")
