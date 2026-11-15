import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from claire.db import Family, Memory, User, now
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
        db.commit()
    with engine.begin() as connection:
        connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        connection.execute(text(f'GRANT SELECT, INSERT, UPDATE ON memories TO "{role}"'))
    try:
        with engine.begin() as connection:
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            assert connection.scalar(text("SELECT count(*) FROM memories")) == 0
            connection.execute(
                text(
                    "SELECT set_config('claire.user_id', :user, true), "
                    "set_config('claire.family_id', :family, true)"
                ),
                {"user": bob_id, "family": family_id},
            )
            assert connection.scalars(text("SELECT title FROM memories")).all() == ["shared"]
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
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'REVOKE ALL ON memories FROM "{role}"'))
            connection.execute(text(f'REVOKE USAGE ON SCHEMA public FROM "{role}"'))
            connection.execute(text(f'DROP ROLE "{role}"'))
        engine.dispose()
