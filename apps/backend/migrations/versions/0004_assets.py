"""Private original documents and media files."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("mime", sa.String(80), nullable=False),
        sa.Column("category", sa.String(12), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("visibility", sa.String(12), nullable=False),
        sa.Column("deleted", sa.Boolean, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("visibility IN ('private', 'family')", name="asset_visibility"),
        sa.CheckConstraint("revision >= 1", name="asset_revision"),
    )
    op.create_index("ix_assets_family_id", "assets", ["family_id"])
    op.create_index("ix_assets_owner_id", "assets", ["owner_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE assets ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE assets FORCE ROW LEVEL SECURITY")
        family = "family_id = current_setting('claire.family_id', true)"
        owner = "owner_id = current_setting('claire.user_id', true)"
        op.execute(
            f"CREATE POLICY asset_read ON assets FOR SELECT USING ({family} AND "
            f"({owner} OR (visibility = 'family' AND NOT deleted)))"
        )
        op.execute(f"CREATE POLICY asset_create ON assets FOR INSERT WITH CHECK ({family} AND {owner})")
        op.execute(
            f"CREATE POLICY asset_edit ON assets FOR UPDATE USING ({family} AND {owner}) "
            f"WITH CHECK ({family} AND {owner})"
        )
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'claire_runtime') THEN
                GRANT SELECT, INSERT, UPDATE ON assets TO claire_runtime;
            END IF;
        END $$""")


def downgrade():
    op.drop_table("assets")
