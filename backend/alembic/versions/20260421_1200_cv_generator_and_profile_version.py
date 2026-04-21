"""cv generator + profile versioning for stale-output banners

Adds:
  - users.profile_version (int, default 1) — bumps on POST /profile/rebuild.
  - jobs.scored_against_profile_version (int null) — set whenever we score
    a job; UI compares against users.profile_version to show a stale-score
    banner when they differ.
  - cover_letters.profile_version (int) — captures which profile version
    a cover letter was generated against, for the same banner treatment.
  - new table cv_versions — AI-generated CV drafts, up to 2/cycle for
    paid users, 0 for free. Mirrors the shape of cover_letters but adds
    tone, regenerate_reason, questions_payload, profile_version.

No backfill of content. profile_version defaults to 1 everywhere so
existing artefacts aren't retroactively marked stale — they're treated
as generated against the "v1" profile, which is the user's current
profile until they rebuild.

Revision ID: 0004_cv_generator
Revises: 0003_billing_entitlements
Create Date: 2026-04-21 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_cv_generator"
down_revision: Union[str, None] = "0003_billing_entitlements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users.profile_version ------------------------------------------
    # Default 1 with server_default so existing rows get a value during
    # the ALTER. NOT NULL because every user must have a baseline
    # version to compare against.
    op.add_column(
        "users",
        sa.Column(
            "profile_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # --- jobs.scored_against_profile_version ----------------------------
    # Nullable: an unscored job has no value yet. Populated by the
    # scoring pipeline going forward. Existing rows default to NULL,
    # which the UI interprets as "unknown — no banner".
    op.add_column(
        "jobs",
        sa.Column(
            "scored_against_profile_version", sa.Integer, nullable=True
        ),
    )

    # --- cover_letters.profile_version ----------------------------------
    # Default 1 for existing rows so they aren't shown as stale on the
    # first deploy — they'll become stale only if the user rebuilds.
    op.add_column(
        "cover_letters",
        sa.Column(
            "profile_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
    )

    # --- cv_versions -----------------------------------------------------
    op.create_table(
        "cv_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        # Markdown is the canonical source — round-trips through TipTap
        # cleanly and is what the PDF pipeline consumes.
        sa.Column("content_markdown", sa.Text, nullable=False),
        # 'professional' | 'bold'. Enum-via-string rather than PG enum so
        # adding a third tone later doesn't require a migration.
        sa.Column("tone", sa.String(32), nullable=False),
        # Full Phase-1 questions + user-typed answers. Audit trail: if a
        # user regenerates and the output is worse, we can diff the
        # answer sets to see what changed.
        sa.Column("questions_payload", postgresql.JSONB, nullable=False),
        # Null on the first generation; populated on every subsequent
        # regenerate. Feeds directly into the Phase-2 user prompt.
        sa.Column("regenerate_reason", sa.Text, nullable=True),
        # Snapshot of users.profile_version at generation time. UI uses
        # this for the stale banner exactly like cover_letters.
        sa.Column(
            "profile_version",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_cv_versions_user_id", "cv_versions", ["user_id"]
    )
    # Enforce monotonic per-user versions at the DB level so two races
    # that pick the same max+1 won't both land. Worst case: one retries.
    op.create_unique_constraint(
        "uq_cv_versions_user_version",
        "cv_versions",
        ["user_id", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_cv_versions_user_version", "cv_versions", type_="unique"
    )
    op.drop_index("ix_cv_versions_user_id", table_name="cv_versions")
    op.drop_table("cv_versions")

    op.drop_column("cover_letters", "profile_version")
    op.drop_column("jobs", "scored_against_profile_version")
    op.drop_column("users", "profile_version")
