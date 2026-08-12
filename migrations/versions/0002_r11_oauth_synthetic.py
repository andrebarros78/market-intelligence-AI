"""R1.1 synthetic OAuth persistence.

Revision ID: 0002_r11_oauth
Revises: 0001_base02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_r11_oauth"
down_revision = "0001_base02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=160), nullable=False),
        sa.Column("access_envelope", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_envelope", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("key_version", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("marketplace", "account_id", name="uq_oauth_credentials_account"),
    )
    op.create_index("ix_oauth_credentials_expires", "oauth_credentials", ["marketplace", "expires_at"])
    op.create_table(
        "oauth_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("correlation_id", sa.String(length=96), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_oauth_audit_correlation_created", "oauth_audit", ["correlation_id", "created_at"])
    op.create_index("ix_oauth_audit_marketplace_action", "oauth_audit", ["marketplace", "action"])
    op.create_table(
        "oauth_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=96), nullable=False),
        sa.Column("marketplace", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_oauth_operations_idempotency"),
    )
    op.create_index("ix_oauth_operations_marketplace_status", "oauth_operations", ["marketplace", "status"])


def downgrade() -> None:
    op.drop_index("ix_oauth_operations_marketplace_status", table_name="oauth_operations")
    op.drop_table("oauth_operations")
    op.drop_index("ix_oauth_audit_marketplace_action", table_name="oauth_audit")
    op.drop_index("ix_oauth_audit_correlation_created", table_name="oauth_audit")
    op.drop_table("oauth_audit")
    op.drop_index("ix_oauth_credentials_expires", table_name="oauth_credentials")
    op.drop_table("oauth_credentials")
