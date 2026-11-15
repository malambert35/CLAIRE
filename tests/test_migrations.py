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
