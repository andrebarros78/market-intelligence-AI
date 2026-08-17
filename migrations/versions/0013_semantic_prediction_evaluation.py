"""semantic prediction evaluation and honest leading-signal metrics

Revision ID: 0013_semantic_prediction
Revises: 0012_continuous_evolution
Create Date: 2026-08-16
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_semantic_prediction"
down_revision: str | None = "0012_continuous_evolution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
JSONB = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    for name, column in (
        ("target_entity", sa.Column("target_entity", sa.String(length=160), nullable=True)),
        ("target_metric", sa.Column("target_metric", sa.String(length=80), nullable=True)),
        ("operator", sa.Column("operator", sa.String(length=32), nullable=True)),
        ("expected_value", sa.Column("expected_value", JSONB, nullable=True)),
        ("expected_direction", sa.Column("expected_direction", sa.String(length=16), nullable=True)),
        ("baseline_value", sa.Column("baseline_value", JSONB, nullable=True)),
        ("tolerance", sa.Column("tolerance", sa.Float(), nullable=True)),
        ("evaluation_window", sa.Column("evaluation_window", JSONB, nullable=True)),
        ("evidence_source", sa.Column("evidence_source", sa.String(length=160), nullable=True)),
        ("observed_value", sa.Column("observed_value", JSONB, nullable=True)),
        ("observed_outcome", sa.Column("observed_outcome", sa.Float(), nullable=True)),
    ):
        op.add_column("prediction_evaluations", column)
    op.alter_column("leading_signal_research", "precision", existing_type=sa.Float(), nullable=True)
    op.alter_column("leading_signal_research", "false_positives", existing_type=sa.Integer(), nullable=True)
    op.alter_column("leading_signal_research", "false_negatives", existing_type=sa.Integer(), nullable=True)
    op.add_column("leading_signal_research", sa.Column("true_positives", sa.Integer(), nullable=True))
    op.add_column("leading_signal_research", sa.Column("true_negatives", sa.Integer(), nullable=True))
    op.add_column("leading_signal_research", sa.Column("recall", sa.Float(), nullable=True))
    for name in ("predictions_evaluable","predictions_partial","predictions_not_evaluable","predictions_no_data"):
        op.add_column("evolution_metrics", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE prediction_evaluations SET status='LEGACY_NOT_EVALUABLE',correct_or_incorrect='LEGACY_NOT_EVALUABLE',calibration_error=NULL,observed_outcome=NULL WHERE target_metric IS NULL")
    op.execute("UPDATE leading_signal_research SET precision=NULL,false_positives=NULL,false_negatives=NULL,true_positives=support,true_negatives=NULL,recall=NULL,state='INCONCLUSIVE',evidence_json=evidence_json || '{\"confusion_matrix\":\"NOT_ESTIMABLE_LEGACY\",\"precision\":\"NOT_ESTIMABLE\",\"recall\":\"NOT_ESTIMABLE\"}'::jsonb")


def downgrade() -> None:
    op.execute("UPDATE leading_signal_research SET precision=0 WHERE precision IS NULL")
    op.execute("UPDATE leading_signal_research SET false_positives=0 WHERE false_positives IS NULL")
    op.execute("UPDATE leading_signal_research SET false_negatives=0 WHERE false_negatives IS NULL")
    op.alter_column("leading_signal_research", "precision", existing_type=sa.Float(), nullable=False)
    op.alter_column("leading_signal_research", "false_positives", existing_type=sa.Integer(), nullable=False)
    op.alter_column("leading_signal_research", "false_negatives", existing_type=sa.Integer(), nullable=False)
    for col in ("recall","true_negatives","true_positives"):
        op.drop_column("leading_signal_research", col)
    for col in ("predictions_no_data","predictions_not_evaluable","predictions_partial","predictions_evaluable"):
        op.drop_column("evolution_metrics", col)
    for col in ("observed_outcome","observed_value","evidence_source","evaluation_window","tolerance","baseline_value","expected_direction","expected_value","operator","target_metric","target_entity"):
        op.drop_column("prediction_evaluations", col)
