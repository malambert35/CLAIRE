from alembic import context
from claire.config import Settings
from claire.db import Base
from sqlalchemy import create_engine

engine = create_engine(Settings().db_url())
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
