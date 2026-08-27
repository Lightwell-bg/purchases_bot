"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURCHASE_STATUS = sa.Enum(
    "DRAFT",
    "OPEN",
    "CLOSED",
    "ORDERED",
    "SHIPPED",
    "RECEIVED",
    "COMPLETED",
    "CANCELLED",
    name="purchase_status",
    native_enum=False,
    length=20,
)

PARTICIPANT_STATUS = sa.Enum(
    "ACTIVE",
    "CANCELLED",
    name="participant_status",
    native_enum=False,
    length=20,
)

RULES_ACTION = sa.Enum(
    "CREATE_PURCHASE",
    "JOIN_PURCHASE",
    name="rules_action",
    native_enum=False,
    length=20,
)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "purchases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_token", sa.String(length=32), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("product_url", sa.String(length=1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("variant_description", sa.String(length=500), nullable=True),
        sa.Column("unit_price", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("organizer_quantity", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=False),
        sa.Column("pickup_location", sa.String(length=200), nullable=True),
        sa.Column("photo_file_id", sa.String(length=300), nullable=True),
        sa.Column("status", PURCHASE_STATUS, nullable=False),
        sa.Column("group_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("group_message_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organizer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchases_public_token", "purchases", ["public_token"], unique=True)
    op.create_index("ix_purchases_organizer_id", "purchases", ["organizer_id"])
    op.create_index("ix_purchases_status", "purchases", ["status"])
    op.create_index("ix_purchases_status_deadline", "purchases", ["status", "deadline"])

    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("variant", sa.String(length=300), nullable=True),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column("status", PARTICIPANT_STATUS, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("purchase_id", "user_id", name="uq_participant_purchase_user"),
    )
    op.create_index("ix_participants_user_id", "participants", ["user_id"])
    op.create_index(
        "ix_participants_purchase_status", "participants", ["purchase_id", "status"]
    )

    op.create_table(
        "rules_acceptances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purchase_id", sa.Integer(), nullable=True),
        sa.Column("action", RULES_ACTION, nullable=False),
        sa.Column("rules_version", sa.String(length=20), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rules_acceptances_user_id", "rules_acceptances", ["user_id"])
    op.create_index(
        "ix_rules_user_action_version",
        "rules_acceptances",
        ["user_id", "action", "rules_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_rules_user_action_version", table_name="rules_acceptances")
    op.drop_index("ix_rules_acceptances_user_id", table_name="rules_acceptances")
    op.drop_table("rules_acceptances")

    op.drop_index("ix_participants_purchase_status", table_name="participants")
    op.drop_index("ix_participants_user_id", table_name="participants")
    op.drop_table("participants")

    op.drop_index("ix_purchases_status_deadline", table_name="purchases")
    op.drop_index("ix_purchases_status", table_name="purchases")
    op.drop_index("ix_purchases_organizer_id", table_name="purchases")
    op.drop_index("ix_purchases_public_token", table_name="purchases")
    op.drop_table("purchases")

    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
