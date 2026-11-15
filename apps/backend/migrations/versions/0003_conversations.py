"""Private conversation history and bounded generation leases."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active_run", sa.String(36)),
        sa.Column("active_until", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])
    op.create_index("ix_conversations_family_id", "conversations", ["family_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("family_id", sa.String(36), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("model", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    if op.get_bind().dialect.name == "postgresql":
        policy = "owner_id = current_setting('claire.user_id', true) AND family_id = current_setting('claire.family_id', true)"
        for table in ("conversations", "messages"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            check = policy
            if table == "messages":
                check += " AND EXISTS (SELECT 1 FROM conversations c WHERE c.id = conversation_id AND c.owner_id = current_setting('claire.user_id', true))"
            op.execute(f"CREATE POLICY {table}_owner ON {table} USING ({check}) WITH CHECK ({check})")
        op.execute("""DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'claire_runtime') THEN
                GRANT SELECT, INSERT, UPDATE ON conversations TO claire_runtime;
                GRANT SELECT, INSERT ON messages TO claire_runtime;
            END IF;
        END $$""")


def downgrade():
    op.drop_table("messages")
    op.drop_table("conversations")
