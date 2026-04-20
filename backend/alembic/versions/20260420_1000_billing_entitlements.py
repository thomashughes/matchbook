"""billing entitlements — plan fields on users + usage_counters table

Adds the infrastructure for freemium caps + Stripe billing:
  - users.plan, users.stripe_customer_id, users.stripe_subscription_id,
    users.subscription_status, users.subscription_current_period_end,
    users.cancel_at_period_end.
  - new table usage_counters — per-(user, resource, scope, window) count.
  - grandfather the developer account (paid_grandfathered bypasses all
    caps) by email lookup. The email is idempotently set; if the row
    doesn't exist in this environment (local dev on a fresh DB), the
    UPDATE is a no-op, which is the desired behaviour.

No historical backfill: every existing user starts at 0 in their
current window. Grandfathering handles the only real-data edge (the
developer account already has 8 jobs and would otherwise hit the cap
on day one).

Revision ID: 0003_billing_entitlements
Revises: 0002_job_ai_outputs
Create Date: 2026-04-20 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_billing_entitlements"
down_revision: Union[str, None] = "0002_job_ai_outputs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Email of the developer account to grandfather. Kept as a module constant
# so it's auditable in the migration history rather than hidden in a
# fixture. Changing it in the future = new migration, don't edit this one.
GRANDFATHER_EMAIL = "thomashughes1992.th@gmail.com"


def upgrade() -> None:
    # --- users: billing + plan columns -----------------------------------

    # plan is NOT NULL with a default of 'free' so existing rows get the
    # right value at ADD-COLUMN time (server_default is applied to every
    # existing row during the ALTER).
    op.add_column(
        "users",
        sa.Column(
            "plan",
            sa.String(20),
            nullable=False,
            server_default="free",
        ),
    )

    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_stripe_customer_id", "users", ["stripe_customer_id"]
    )

    op.add_column(
        "users",
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_stripe_subscription_id", "users", ["stripe_subscription_id"]
    )

    op.add_column(
        "users",
        sa.Column("subscription_status", sa.String(32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "subscription_current_period_end",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # --- usage_counters --------------------------------------------------

    op.create_table(
        "usage_counters",
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
        sa.Column("resource", sa.String(32), nullable=False),
        # scope_key is NULL for per-user resources, job_id for per-(user, job)
        # resources. Not a FK to jobs(id) because the meaning depends on the
        # resource string; enforcing referential integrity across polymorphic
        # scopes isn't worth the complexity.
        sa.Column("scope_key", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "count",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_usage_counters_user_id", "usage_counters", ["user_id"]
    )
    # Upsert target — this is the key the entitlement service does
    # INSERT ... ON CONFLICT against.
    op.create_unique_constraint(
        "uq_usage_counter_user_resource_scope_window",
        "usage_counters",
        ["user_id", "resource", "scope_key", "window_start"],
    )

    # --- Grandfather the developer account -------------------------------
    # Idempotent: if the row doesn't exist in this environment (fresh
    # local DB, CI), UPDATE affects zero rows and migration still succeeds.
    # In prod this flips Thomas's account to unlimited on deploy, so the
    # existing 8 jobs don't immediately breach the 5-jobs-per-month cap.
    op.execute(
        sa.text(
            "UPDATE users SET plan = 'paid_grandfathered' WHERE email = :email"
        ).bindparams(email=GRANDFATHER_EMAIL)
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_usage_counter_user_resource_scope_window",
        "usage_counters",
        type_="unique",
    )
    op.drop_index("ix_usage_counters_user_id", table_name="usage_counters")
    op.drop_table("usage_counters")

    op.drop_column("users", "cancel_at_period_end")
    op.drop_column("users", "subscription_current_period_end")
    op.drop_column("users", "subscription_status")
    op.drop_constraint("uq_users_stripe_subscription_id", "users", type_="unique")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_constraint("uq_users_stripe_customer_id", "users", type_="unique")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "plan")
