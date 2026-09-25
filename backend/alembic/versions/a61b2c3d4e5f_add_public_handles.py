"""Add public profile navigation handles without changing authentication data.

Revision ID: a61b2c3d4e5f
Revises: f6a1b2c3d4e5
"""

import secrets

from alembic import op
import sqlalchemy as sa

revision = "a61b2c3d4e5f"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None

# Frozen migration policy: do not import evolving application validators.
HANDLE_CHECK = (
    "REGEXP_LIKE(public_handle, '^[a-z0-9][a-z0-9_-]{1,28}[a-z0-9]$', 'c') "
    "AND public_handle NOT IN "
    "('about','account','admin','api','assets','auth','categories','chat','cities',"
    "'dev','help','login','logout','messages','notifications','products','profile',"
    "'profiles','register','search','seller','sellers','settings','static','support','users')"
)


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("public_handle", sa.String(30), nullable=True))
    profiles = sa.table("user_profiles", sa.column("id", sa.String(36)),
                        sa.column("public_handle", sa.String(30)))
    connection = op.get_bind()
    allocated: set[str] = set()
    # Run during a maintenance window; no pre-existing column is updated.
    for row_id in connection.execute(sa.select(profiles.c.id)).scalars().all():
        for _ in range(8):
            handle = "user-" + secrets.token_hex(10)
            if handle not in allocated:
                break
        else:
            raise RuntimeError("Public handle allocation unavailable.")
        allocated.add(handle)
        connection.execute(profiles.update().where(profiles.c.id == row_id)
                           .values(public_handle=handle))
    op.alter_column("user_profiles", "public_handle", existing_type=sa.String(30), nullable=False)
    op.create_unique_constraint("uq_user_profiles_public_handle", "user_profiles", ["public_handle"])
    op.create_check_constraint("ck_user_profiles_public_handle", "user_profiles", HANDLE_CHECK)


def downgrade() -> None:
    # Removes only this phase's navigation field. Existing profiles/authentication survive.
    op.drop_constraint("ck_user_profiles_public_handle", "user_profiles", type_="check")
    op.drop_constraint("uq_user_profiles_public_handle", "user_profiles", type_="unique")
    op.drop_column("user_profiles", "public_handle")
