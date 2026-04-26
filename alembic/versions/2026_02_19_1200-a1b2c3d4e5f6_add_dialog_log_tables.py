from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "4f9b2c1d7a11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_request_logs",
        sa.Column("user_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("request_text", sa.Text(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_tg_id"], ["users.tg_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_request_logs_user_tg_id"), "user_request_logs", ["user_tg_id"], unique=False)

    op.create_table(
        "bot_response_logs",
        sa.Column("user_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("user_request_log_id", sa.Integer(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_tg_id"], ["users.tg_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_request_log_id"], ["user_request_logs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bot_response_logs_user_request_log_id"),
        "bot_response_logs",
        ["user_request_log_id"],
        unique=False,
    )
    op.create_index(op.f("ix_bot_response_logs_user_tg_id"), "bot_response_logs", ["user_tg_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bot_response_logs_user_request_log_id"), table_name="bot_response_logs")
    op.drop_index(op.f("ix_bot_response_logs_user_tg_id"), table_name="bot_response_logs")
    op.drop_table("bot_response_logs")

    op.drop_index(op.f("ix_user_request_logs_user_tg_id"), table_name="user_request_logs")
    op.drop_table("user_request_logs")
