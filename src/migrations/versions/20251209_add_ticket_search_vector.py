"""Add ticket search vector and GIN index."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Keep <= 32 chars to fit alembic_version.version_num
revision = "20251209_ticket_vec"
down_revision = "20251209_agents_tables"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("inboxiq_tickets")}
    if "search_vec" not in cols:
        op.add_column("inboxiq_tickets", sa.Column("search_vec", postgresql.TSVECTOR(), nullable=True))

    # Populate vector for existing rows
    op.execute(
        """
        UPDATE inboxiq_tickets
        SET search_vec = to_tsvector(
          'english',
          coalesce(subject, '') || ' ' || coalesce(body_preview, '')
        )
        """
    )
    # Ensure trigger function exists
    op.execute(
        """
        CREATE OR REPLACE FUNCTION inboxiq_tickets_search_vec_trigger() RETURNS trigger AS $$
        begin
          new.search_vec :=
            to_tsvector('english', coalesce(new.subject, '') || ' ' || coalesce(new.body_preview, ''));
          return new;
        end;
        $$ LANGUAGE plpgsql;
        """
    )
    # Recreate trigger idempotently
    op.execute("DROP TRIGGER IF EXISTS inboxiq_tickets_search_vec_update ON inboxiq_tickets;")
    op.execute(
        """
        CREATE TRIGGER inboxiq_tickets_search_vec_update
        BEFORE INSERT OR UPDATE ON inboxiq_tickets
        FOR EACH ROW EXECUTE PROCEDURE inboxiq_tickets_search_vec_trigger();
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_inboxiq_tickets_search_vec
        ON inboxiq_tickets
        USING gin (search_vec)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_inboxiq_tickets_search_vec;")
    op.execute("DROP TRIGGER IF EXISTS inboxiq_tickets_search_vec_update ON inboxiq_tickets;")
    op.execute("DROP FUNCTION IF EXISTS inboxiq_tickets_search_vec_trigger();")
    op.drop_column("inboxiq_tickets", "search_vec")
