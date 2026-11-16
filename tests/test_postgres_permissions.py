import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from claire.db import Asset, Conversation, Family, ImmichConnection, Memory, Message, User, now
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


@pytest.mark.skipif(
    not os.environ.get("CLAIRE_TEST_DATABASE_URL"), reason="Disposable PostgreSQL URL required"
)
def test_database_rls_denies_private_foreign_and_owner_forgery(monkeypatch):
    url = os.environ["CLAIRE_TEST_DATABASE_URL"]
    monkeypatch.setenv("CLAIRE_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(url)
    role = f"claire_test_{uuid4().hex}"
    with Session(engine) as db:
        family, foreign = Family(name="Test family"), Family(name="Other family")
        db.add_all([family, foreign])
        db.flush()
        alice = User(
            email="rls-alice@example.test", family_id=family.id, password_hash="not-a-login", role="member"
        )
        bob = User(
            email="rls-bob@example.test",
            family_id=family.id,
            password_hash="not-a-login",
            role="family_admin",
        )
        eve = User(
            email="rls-eve@example.test", family_id=foreign.id, password_hash="not-a-login", role="member"
        )
        db.add_all([alice, bob, eve])
        db.flush()
        for title, user, visibility in [
            ("private", alice, "private"),
            ("shared", alice, "family"),
            ("foreign", eve, "family"),
        ]:
            db.add(
                Memory(
                    id=str(uuid4()),
                    family_id=user.family_id,
                    owner_id=user.id,
                    title=title,
                    visibility=visibility,
                    revision=1,
                    deleted=False,
                    updated_at=now(),
                )
            )
        family_id, alice_id, bob_id = family.id, alice.id, bob.id
        db.add(
            ImmichConnection(
                owner_id=bob_id,
                family_id=family_id,
                endpoint="http://mcp.test:5000/mcp",
                enabled=False,
                token_cipher="synthetic-encrypted-value",
                revision=1,
            )
        )
        for title, user, visibility in [
            ("private", alice, "private"),
            ("shared", alice, "family"),
            ("foreign", eve, "family"),
        ]:
            db.add(
                Asset(
                    family_id=user.family_id,
                    owner_id=user.id,
                    title=title,
                    filename="photo.png",
                    description="",
                    mime="image/png",
                    category="image",
                    sha256="0" * 64,
                    size=20,
                    visibility=visibility,
                )
            )
        conversation = Conversation(owner_id=alice_id, family_id=family_id, title="Private chat")
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
        db.add(
            Message(
                conversation_id=conversation.id,
                owner_id=alice_id,
                family_id=family_id,
                role="user",
                content="Private transcript",
                status="complete",
            )
        )
        db.commit()
    with engine.begin() as connection:
        connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        connection.execute(text(f'GRANT SELECT ON users TO "{role}"'))
        connection.execute(
            text(
                f'GRANT SELECT, INSERT, UPDATE ON memories, conversations, messages, assets, immich_connections TO "{role}"'
            )
        )
    try:
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            assert connection.scalar(text("SELECT count(*) FROM memories")) == 0
            assert connection.scalar(text("SELECT count(*) FROM assets")) == 0
            assert connection.scalar(text("SELECT count(*) FROM immich_connections")) == 0
            connection.execute(
                text(
                    "SELECT set_config('claire.user_id', :user, true), "
                    "set_config('claire.family_id', :family, true)"
                ),
                {"user": bob_id, "family": family_id},
            )
            assert connection.scalars(text("SELECT title FROM memories")).all() == ["shared"]
            assert connection.scalars(text("SELECT title FROM assets")).all() == ["shared"]
            assert connection.scalar(text("SELECT count(*) FROM immich_connections")) == 1
            assert (
                connection.execute(
                    text("UPDATE assets SET visibility='private' WHERE title='shared'")
                ).rowcount
                == 0
            )
            assert connection.scalar(text("SELECT count(*) FROM conversations")) == 0
            assert connection.scalar(text("SELECT count(*) FROM messages")) == 0
            assert (
                connection.execute(text("UPDATE memories SET title='forged' WHERE title='shared'")).rowcount
                == 0
            )
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            connection.execute(
                text(
                    "SELECT set_config('claire.user_id', :user, true), "
                    "set_config('claire.family_id', :family, true)"
                ),
                {"user": bob_id, "family": family_id},
            )
            connection.execute(
                text(
                    "INSERT INTO memories (id,family_id,owner_id,title,visibility,revision,deleted,updated_at) "
                    "VALUES (:id,:family,:owner,'forged','private',1,false,now())"
                ),
                {"id": str(uuid4()), "family": family_id, "owner": alice_id},
            )
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            connection.execute(
                text(
                    "SELECT set_config('claire.user_id', :user, true), "
                    "set_config('claire.family_id', :family, true)"
                ),
                {"user": bob_id, "family": family_id},
            )
            connection.execute(
                text(
                    "INSERT INTO messages (id,conversation_id,owner_id,family_id,role,content,status,created_at) "
                    "VALUES (:id,:conversation,:owner,:family,'user','forged','complete',now())"
                ),
                {"id": str(uuid4()), "conversation": conversation_id, "owner": bob_id, "family": family_id},
            )
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            connection.execute(
                text(
                    "SELECT set_config('claire.user_id', :user, true), "
                    "set_config('claire.family_id', :family, true)"
                ),
                {"user": alice_id, "family": family_id},
            )
            assert connection.scalar(text("SELECT content FROM messages")) == "Private transcript"
            assert connection.scalar(text("SELECT count(*) FROM immich_connections")) == 0
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'REVOKE ALL ON users FROM "{role}"'))
            connection.execute(
                text(
                    f'REVOKE ALL ON memories, conversations, messages, assets, immich_connections FROM "{role}"'
                )
            )
            connection.execute(text(f'REVOKE USAGE ON SCHEMA public FROM "{role}"'))
            connection.execute(text(f'DROP ROLE "{role}"'))
        engine.dispose()
