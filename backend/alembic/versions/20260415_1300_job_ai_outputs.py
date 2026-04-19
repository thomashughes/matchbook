"""job_ai_outputs — generic store for outreach / form / follow-up / interview prep

Single table keyed by (job_id, kind, version). See the model docstring
for why these four AI actions share storage while cover letters don't.

Revision ID: 0002_job_ai_outputs
Revises: 0001_initial
Create Date: 2026-04-15 13:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_job_ai_outputs"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_ai_outputs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_job_ai_outputs_job_id", "job_ai_outputs", ["job_id"])
    op.create_index("ix_job_ai_outputs_user_id", "job_ai_outputs", ["user_id"])
    op.create_index("ix_job_ai_outputs_kind", "job_ai_outputs", ["kind"])
    # Fast list-by-kind-for-a-job (the common read pattern).
    op.create_index(
        "ix_job_ai_outputs_job_kind", "job_ai_outputs", ["job_id", "kind"]
    )


def downgrade() -> None:
    op.drop_table("job_ai_outputs")
