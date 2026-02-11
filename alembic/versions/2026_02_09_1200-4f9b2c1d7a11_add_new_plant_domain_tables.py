from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f9b2c1d7a11'
down_revision: Union[str, None] = 'eb266184380d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plant_species',
        sa.Column('latin_name', sa.Text(), nullable=False),
        sa.Column('common_name', sa.Text(), nullable=True),
        sa.Column('water_days_min', sa.Integer(), nullable=True),
        sa.Column('water_days_max', sa.Integer(), nullable=True),
        sa.Column('spray_interval', sa.Integer(), nullable=True),
        sa.Column('light_type', sa.String(length=64), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'user_plants',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('species_id', sa.Integer(), nullable=True),
        sa.Column('nickname', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='healthy', nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('notifications_enabled', sa.BOOLEAN(), server_default='true', nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['species_id'], ['plant_species.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.tg_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_plants_species_id'), 'user_plants', ['species_id'], unique=False)
    op.create_index(op.f('ix_user_plants_user_id'), 'user_plants', ['user_id'], unique=False)

    op.create_table(
        'plant_photos',
        sa.Column('user_plant_id', sa.Integer(), nullable=False),
        sa.Column('image_url', sa.Text(), nullable=False),
        sa.Column('ml_guess', sa.Text(), nullable=True),
        sa.Column('ml_confidence', sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column('confirmed', sa.BOOLEAN(), server_default='false', nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_plant_id'], ['user_plants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_plant_photos_user_plant_id'), 'plant_photos', ['user_plant_id'], unique=False)

    op.create_table(
        'care_profiles',
        sa.Column('user_plant_id', sa.Integer(), nullable=False),
        sa.Column('water_interval', sa.Integer(), nullable=True),
        sa.Column('spray_interval', sa.Integer(), nullable=True),
        sa.Column('last_watered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_water_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_plant_id'], ['user_plants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_care_profiles_user_plant_id'), 'care_profiles', ['user_plant_id'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('user_plant_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('cron_expr', sa.Text(), nullable=False),
        sa.Column('next_run', sa.DateTime(timezone=True), nullable=True),
        sa.Column('enabled', sa.BOOLEAN(), server_default='true', nullable=False),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_plant_id'], ['user_plants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_user_plant_id'), 'notifications', ['user_plant_id'], unique=False)

    op.create_table(
        'plant_care_logs',
        sa.Column('user_plant_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_plant_id'], ['user_plants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_plant_care_logs_user_plant_id'), 'plant_care_logs', ['user_plant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_plant_care_logs_user_plant_id'), table_name='plant_care_logs')
    op.drop_table('plant_care_logs')

    op.drop_index(op.f('ix_notifications_user_plant_id'), table_name='notifications')
    op.drop_table('notifications')

    op.drop_index(op.f('ix_care_profiles_user_plant_id'), table_name='care_profiles')
    op.drop_table('care_profiles')

    op.drop_index(op.f('ix_plant_photos_user_plant_id'), table_name='plant_photos')
    op.drop_table('plant_photos')

    op.drop_index(op.f('ix_user_plants_user_id'), table_name='user_plants')
    op.drop_index(op.f('ix_user_plants_species_id'), table_name='user_plants')
    op.drop_table('user_plants')

    op.drop_table('plant_species')