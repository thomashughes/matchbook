"""job status history + expanded statuses

Adds the job_status_history table that powers the dashboard Sankey
funnel, backfills one row per existing job (representing the journey
starting at the current state), and migrates the legacy
"interviewing" status to "first_interview" so the new pipeline has a
single, more granular interview column instead of the v1 catch-all.

Revision ID: 0006_job_status_history
Revises: 0005_usage_nulls_distinct
Create Date: 2026-04-29 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_job_status_history"
down_revision: Union[str, None] = "0005_usage_nulls_distinct"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Migrate legacy "interviewing" rows to "first_interview".
    # Lossy — we cannot recover which round each job was at — but
    # first_interview is the safer-default landing stage when the
    # information is unknowable, since a job marked "interviewing"
    # has at least cleared the application stage.
    op.execute(
        "UPDATE jobs SET status = 'first_interview' WHERE status = 'interviewing'"
    )

    # 2. Bump the status column width to fit the longest new value
    # ("second_interview" = 16 chars). The history table uses
    # String(30) too — 30 leaves comfortable headroom for any future
    # "phone_screen_followup_round_3" pathological case.
    op.alter_column("jobs", "status", type_=sa.String(30))

    # 3. Create the history table.
    op.create_table(
        "job_status_history",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_job_status_history_user_changed",
        "job_status_history",
        ["user_id", "changed_at"],
    )
    op.create_index(
        "ix_job_status_history_job_changed",
        "job_status_history",
        ["job_id", "changed_at"],
    )

    # 4. Backfill: one row per existing job, recording the current
    # state as the entry point of the funnel. from_status NULL = "this
    # is where the journey starts". changed_at clones jobs.created_at
    # so the funnel time-window filter works retroactively (a job
    # created 60 days ago shouldn't suddenly show up in "last 30
    # days" because the backfill ran today).
    op.execute(
        """
        INSERT INTO job_status_history (job_id, user_id, from_status, to_status, changed_at)
        SELECT id, user_id, NULL, status, created_at
        FROM jobs
        """
    )


def downgrade() -> None:
    # Reverse order: drop the history table first, then shrink the
    # status column, then revert the legacy mapping.
    op.drop_index(
        "ix_job_status_history_job_changed", table_name="job_status_history"
    )
    op.drop_index(
        "ix_job_status_history_user_changed", table_name="job_status_history"
    )
    op.drop_table("job_status_history")
    op.alter_column("jobs", "status", type_=sa.String(20))
    op.execute(
        "UPDATE jobs SET status = 'interviewing' WHERE status IN "
        "('first_interview', 'second_interview', 'final_interview')"
    )
