"""add garden plant photos table

Revision ID: d9a4f6b8c2e1
Revises: a1b2c3d4e5f6
Create Date: 2026-02-24 13:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9a4f6b8c2e1"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "garden_plant_photos",
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("analysis", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.BOOLEAN(), server_default="true", nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["garden_plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_garden_plant_photos_plant_id"), "garden_plant_photos", ["plant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_garden_plant_photos_plant_id"), table_name="garden_plant_photos")
    op.drop_table("garden_plant_photos")
