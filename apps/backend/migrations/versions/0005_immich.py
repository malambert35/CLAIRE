"""Owner-admin scoped Immich MCP configuration."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "immich_connections",
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("endpoint", sa.String(1000), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("token_cipher", sa.Text),
        sa.Column("revision", sa.Integer, nullable=False),
    )
    op.create_index("ix_immich_connections_family_id", "immich_connections", ["family_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE immich_connections ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE immich_connections FORCE ROW LEVEL SECURITY")
        policy = (
            "owner_id = current_setting('claire.user_id', true) AND "
            "family_id = current_setting('claire.family_id', true) AND "
            "EXISTS (SELECT 1 FROM users u WHERE u.id = owner_id AND u.role = 'family_admin')"
        )
        op.execute(f"CREATE POLICY immich_admin ON immich_connections USING ({policy}) WITH CHECK ({policy})")
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'claire_runtime') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON immich_connections TO claire_runtime;
            END IF;
        END $$""")


def downgrade():
    op.drop_table("immich_connections")
