"""add_unique_index_to_payments_payment_id

Revision ID: f3c2b7a91d4e
Revises: d9a4f6b8c2e1
Create Date: 2026-04-23 12:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3c2b7a91d4e"
down_revision: str | None = "d9a4f6b8c2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UNIQUE_CONSTRAINT_NAME = "uq_payments_payment_id"


def upgrade() -> None:
    op.create_unique_constraint(
        UNIQUE_CONSTRAINT_NAME,
        "payments",
        ["payment_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        UNIQUE_CONSTRAINT_NAME,
        "payments",
        type_="unique",
    )
