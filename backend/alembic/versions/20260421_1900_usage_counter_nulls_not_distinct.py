"""fix usage_counter uniqueness for NULL scope_key

Root cause: PostgreSQL default is NULLS DISTINCT, so our unique
constraint on (user_id, resource, scope_key, window_start) DOES NOT
match two rows that differ only in scope_key being NULL both times.
That means user-scoped resources (scope=user, scope_key=None) didn't
upsert on subsequent calls — they just inserted a duplicate row with
count=1. Paid users still saw the right "over quota" eventually (the
limit check reads ONE row), but the usage table was littered with
duplicates and the counter never summed correctly.

Fix:
    1. Merge any existing duplicate rows by summing their counts into
       the earliest row (MIN(id)) and deleting the rest.
    2. Drop the old constraint.
    3. Recreate it with NULLS NOT DISTINCT (PG 15+), which makes two
       NULLs equal for the purpose of the unique check — exactly the
       semantics we wanted.

Safe to run on prod: the merge step is idempotent, and NULLS NOT
DISTINCT is a well-supported feature in PG 15 and 16 (prod is 16.13).

Revision ID: 0005_usage_nulls_distinct
Revises: 0004_cv_generator
Create Date: 2026-04-21 19:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_usage_nulls_distinct"
down_revision: Union[str, None] = "0004_cv_generator"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Sum counts into the earliest row per group; delete the rest.
    # Handles only the NULL scope_key case because non-NULL keys have
    # never duplicated (the old constraint worked correctly for them).
    op.execute(
        """
        WITH grouped AS (
            SELECT
                user_id, resource, window_start, window_end,
                SUM(count)::int AS total_count,
                -- Postgres has no MIN() aggregate for uuid; use an ordered array
-- aggregate and take the first element to pick a deterministic
-- row to keep.
                (array_agg(id ORDER BY id))[1] AS keep_id
            FROM usage_counters
            WHERE scope_key IS NULL
            GROUP BY user_id, resource, window_start, window_end
            HAVING COUNT(*) > 1
        )
        UPDATE usage_counters uc
        SET count = g.total_count
        FROM grouped g
        WHERE uc.id = g.keep_id;
        """
    )
    op.execute(
        """
        DELETE FROM usage_counters uc
        USING (
            SELECT user_id, resource, window_start, -- Postgres has no MIN() aggregate for uuid; use an ordered array
-- aggregate and take the first element to pick a deterministic
-- row to keep.
                (array_agg(id ORDER BY id))[1] AS keep_id
            FROM usage_counters
            WHERE scope_key IS NULL
            GROUP BY user_id, resource, window_start
            HAVING COUNT(*) > 1
        ) g
        WHERE uc.user_id = g.user_id
          AND uc.resource = g.resource
          AND uc.window_start = g.window_start
          AND uc.scope_key IS NULL
          AND uc.id != g.keep_id;
        """
    )

    # 2. Drop the old constraint (created in 0003_billing_entitlements).
    op.drop_constraint(
        "uq_usage_counter_user_resource_scope_window",
        "usage_counters",
        type_="unique",
    )

    # 3. Recreate with NULLS NOT DISTINCT. Raw SQL rather than
    # op.create_unique_constraint because Alembic's helper doesn't
    # expose the NULLS NOT DISTINCT modifier yet (as of 1.13).
    op.execute(
        """
        ALTER TABLE usage_counters
        ADD CONSTRAINT uq_usage_counter_user_resource_scope_window
        UNIQUE NULLS NOT DISTINCT (user_id, resource, scope_key, window_start);
        """
    )


def downgrade() -> None:
    # Downgrade returns to the previous (broken) state. We don't
    # re-split merged rows — that's not recoverable.
    op.drop_constraint(
        "uq_usage_counter_user_resource_scope_window",
        "usage_counters",
        type_="unique",
    )
    op.execute(
        """
        ALTER TABLE usage_counters
        ADD CONSTRAINT uq_usage_counter_user_resource_scope_window
        UNIQUE (user_id, resource, scope_key, window_start);
        """
    )
