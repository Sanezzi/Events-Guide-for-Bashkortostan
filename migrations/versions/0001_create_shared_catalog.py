__doc__ = 'Create shared catalog'
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('agent_traces',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_ref', sa.String(length=128), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_traces_session_ref'), 'agent_traces', ['session_ref'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('actor', sa.String(length=64), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('normalized_title', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=30), nullable=False),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('date_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('date_end', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_min', sa.Integer(), nullable=True),
    sa.Column('city', sa.String(length=150), nullable=False),
    sa.Column('venue', sa.String(length=300), nullable=False),
    sa.Column('address', sa.String(length=500), nullable=False),
    sa.Column('lat', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('lon', sa.Numeric(precision=9, scale=6), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('price_min', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('price_max', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('is_free', sa.Boolean(), nullable=False),
    sa.Column('age_limit', sa.Integer(), nullable=False),
    sa.Column('language', sa.String(length=30), nullable=True),
    sa.Column('org_link', sa.Text(), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('source_type', sa.String(length=30), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('sources', sa.JSON(), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confidence', sa.Numeric(precision=4, scale=3), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('dedup_key', sa.String(length=64), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("category IN ('концерт','спектакль','выставка','фестиваль','кино','экскурсия','другое')", name='valid_category'),
    sa.CheckConstraint("language IS NULL OR language IN ('ru','ba','en','ru/ba')", name='valid_event_language'),
    sa.CheckConstraint("source_type IN ('manual','import','rss','api','page','demo')", name='valid_source_type'),
    sa.CheckConstraint("status IN ('опубликовано','черновик','отменено')", name='valid_status'),
    sa.CheckConstraint('NOT is_free OR (price_min = 0 AND price_max = 0)', name='valid_free'),
    sa.CheckConstraint('age_limit IN (0,6,12,16,18)', name='valid_age'),
    sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='valid_confidence'),
    sa.CheckConstraint('date_end IS NULL OR date_end >= date_start', name='valid_dates'),
    sa.CheckConstraint('duration_min IS NULL OR duration_min > 0', name='valid_duration'),
    sa.CheckConstraint('lat IS NULL OR (lat >= -90 AND lat <= 90)', name='valid_latitude'),
    sa.CheckConstraint('lon IS NULL OR (lon >= -180 AND lon <= 180)', name='valid_longitude'),
    sa.CheckConstraint('price_min >= 0 AND price_max >= price_min', name='valid_prices'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dedup_key'),
    sa.UniqueConstraint('source_hash')
    )
    op.create_index(op.f('ix_events_category'), 'events', ['category'], unique=False)
    op.create_index(op.f('ix_events_city'), 'events', ['city'], unique=False)
    op.create_index(op.f('ix_events_date_start'), 'events', ['date_start'], unique=False)
    op.create_index(op.f('ix_events_normalized_title'), 'events', ['normalized_title'], unique=False)
    op.create_index(op.f('ix_events_status'), 'events', ['status'], unique=False)
    op.create_table('feedback',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.String(length=128), nullable=False),
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_feedback_event_id'), 'feedback', ['event_id'], unique=False)
    op.create_table('raw_imports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('row_number', sa.Integer(), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_raw_imports_batch_id'), 'raw_imports', ['batch_id'], unique=False)
    op.create_index(op.f('ix_raw_imports_source_hash'), 'raw_imports', ['source_hash'], unique=False)
    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tg_user_id', sa.String(length=128), nullable=False),
    sa.Column('city', sa.String(length=150), nullable=True),
    sa.Column('category', sa.String(length=30), nullable=True),
    sa.Column('filter_key', sa.String(length=64), nullable=False),
    sa.Column('period', sa.String(length=10), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tg_user_id', 'filter_key', name='unique_subscription')
    )
    op.create_index(op.f('ix_subscriptions_tg_user_id'), 'subscriptions', ['tg_user_id'], unique=False)
    op.create_table('user_settings',
    sa.Column('tg_user_id', sa.String(length=32), nullable=False),
    sa.Column('lang', sa.String(length=5), nullable=False),
    sa.CheckConstraint("lang IN ('ru','ba','en')", name='valid_ui_language'),
    sa.PrimaryKeyConstraint('tg_user_id')
    )


def downgrade() -> None:
    op.drop_table('user_settings')
    op.drop_index(op.f('ix_subscriptions_tg_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_raw_imports_source_hash'), table_name='raw_imports')
    op.drop_index(op.f('ix_raw_imports_batch_id'), table_name='raw_imports')
    op.drop_table('raw_imports')
    op.drop_index(op.f('ix_feedback_event_id'), table_name='feedback')
    op.drop_table('feedback')
    op.drop_index(op.f('ix_events_status'), table_name='events')
    op.drop_index(op.f('ix_events_normalized_title'), table_name='events')
    op.drop_index(op.f('ix_events_date_start'), table_name='events')
    op.drop_index(op.f('ix_events_city'), table_name='events')
    op.drop_index(op.f('ix_events_category'), table_name='events')
    op.drop_table('events')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_agent_traces_session_ref'), table_name='agent_traces')
    op.drop_table('agent_traces')
