"""Enrich existing catalog events with age and topic tags."""
from alembic import op
import sqlalchemy as sa

from contour.tags import event_tags

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    events = sa.table(
        "events", sa.column("id", sa.Uuid()), sa.column("title"), sa.column("description"),
        sa.column("category"), sa.column("age_limit"), sa.column("is_free"),
        sa.column("tags", sa.JSON()),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(events)).mappings():
        tags = event_tags(row["title"], row["description"], row["category"],
                          row["age_limit"], row["is_free"], row["tags"])
        connection.execute(events.update().where(events.c.id == row["id"]).values(tags=tags))


def downgrade():
    # The enriched tags are valid catalog data at the previous schema version.
    pass
