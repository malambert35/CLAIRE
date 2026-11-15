import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migrations_round_trip(tmp_path, monkeypatch):
    url = os.environ.get("CLAIRE_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'migration.db'}")
    monkeypatch.setenv("CLAIRE_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(url)
    assert {"families", "users", "sessions", "audit"} <= set(inspect(engine).get_table_names())
    command.downgrade(config, "base")
    assert "users" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    engine.dispose()


def test_memory_upgrade_preserves_existing_identity(tmp_path, monkeypatch):
    from claire.db import Family, User
    from sqlalchemy.orm import Session

    url = f"sqlite:///{tmp_path / 'existing.db'}"
    monkeypatch.setenv("CLAIRE_DATABASE_URL", url)
    config = Config("alembic.ini")
    command.upgrade(config, "0001")
    engine = create_engine(url)
    with Session(engine) as db:
        family = Family(name="Existing family")
        db.add(family)
        db.flush()
        user = User(email="existing@example.test", family_id=family.id, password_hash="unchanged-hash")
        db.add(user)
        db.commit()
        user_id, family_id = user.id, family.id
    command.upgrade(config, "head")
    with Session(engine) as db:
        user = db.get(User, user_id)
        assert user.family_id == family_id and user.password_hash == "unchanged-hash"
    assert "memories" in inspect(engine).get_table_names()
    engine.dispose()
