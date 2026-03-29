"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-29 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ranktype = sa.Enum("FULL", "SUDO", "LESS", name="ranktype")


def upgrade() -> None:
    bind = op.get_bind()
    ranktype.create(bind, checkfirst=True)

    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("rank", ranktype, nullable=False),
        sa.Column("is_approved", sa.Boolean(), nullable=False),
        sa.Column("auto_dl_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_group_approved", "groups", ["is_approved"], unique=False)
    op.create_index("idx_group_rank", "groups", ["rank"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False),
        sa.Column("auto_dl_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_admin", "users", ["is_admin"], unique=False)
    op.create_index("idx_user_owner", "users", ["is_owner"], unique=False)

    op.create_table(
        "downloads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("group_id", sa.BigInteger(), nullable=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("request_message_id", sa.Integer(), nullable=True),
        sa.Column("status_message_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_download_user", "downloads", ["user_id"], unique=False)
    op.create_index("idx_download_group", "downloads", ["group_id"], unique=False)
    op.create_index("idx_download_chat", "downloads", ["chat_id"], unique=False)
    op.create_index("idx_download_status", "downloads", ["status"], unique=False)
    op.create_index("idx_download_started", "downloads", ["started_at"], unique=False)

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_id", sa.BigInteger(), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_action_admin", "admin_actions", ["admin_id"], unique=False)
    op.create_index("idx_action_type", "admin_actions", ["action_type"], unique=False)
    op.create_index("idx_action_timestamp", "admin_actions", ["timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_action_timestamp", table_name="admin_actions")
    op.drop_index("idx_action_type", table_name="admin_actions")
    op.drop_index("idx_action_admin", table_name="admin_actions")
    op.drop_table("admin_actions")

    op.drop_index("idx_download_started", table_name="downloads")
    op.drop_index("idx_download_status", table_name="downloads")
    op.drop_index("idx_download_chat", table_name="downloads")
    op.drop_index("idx_download_group", table_name="downloads")
    op.drop_index("idx_download_user", table_name="downloads")
    op.drop_table("downloads")

    op.drop_index("idx_user_owner", table_name="users")
    op.drop_index("idx_user_admin", table_name="users")
    op.drop_table("users")

    op.drop_index("idx_group_rank", table_name="groups")
    op.drop_index("idx_group_approved", table_name="groups")
    op.drop_table("groups")

    ranktype.drop(op.get_bind(), checkfirst=True)
