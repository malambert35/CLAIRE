"""Permission-scoped operational catalogue for portable memory revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "memories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("visibility", sa.String(12), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("deleted", sa.Boolean, nullable=False),
        sa.Column("event_date", sa.String(80)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("visibility IN ('private', 'family')", name="memory_visibility"),
        sa.CheckConstraint("revision >= 1", name="memory_revision"),
    )
    op.create_index("ix_memories_family_id", "memories", ["family_id"])
    op.create_index("ix_memories_owner_id", "memories", ["owner_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE memories ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE memories FORCE ROW LEVEL SECURITY")
        family = "family_id = current_setting('claire.family_id', true)"
        owner = "owner_id = current_setting('claire.user_id', true)"
        op.execute(
            f"CREATE POLICY memory_read ON memories FOR SELECT USING ({family} AND "
            f"({owner} OR (visibility = 'family' AND NOT deleted)))"
        )
        op.execute(f"CREATE POLICY memory_create ON memories FOR INSERT WITH CHECK ({family} AND {owner})")
        op.execute(
            f"CREATE POLICY memory_edit ON memories FOR UPDATE USING ({family} AND {owner}) "
            f"WITH CHECK ({family} AND {owner})"
        )
        # Existing installations may already have provisioned this least-privilege role.
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'claire_runtime') THEN
                GRANT SELECT, INSERT, UPDATE ON memories TO claire_runtime;
            END IF;
        END $$""")


def downgrade():
    op.drop_table("memories")
