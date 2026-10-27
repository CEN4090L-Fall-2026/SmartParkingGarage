"""Migrations use the configured database or an explicitly supplied test connection."""

import os

import sqlalchemy as sa
from alembic import context

from smart_parking_backend.storage import schema

config = context.config


def run_migrations(connection: sa.Connection) -> None:
    context.configure(connection=connection, target_metadata=schema.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=os.environ["SPG_DATABASE_URL"],
        target_metadata=schema.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
elif "connection" in config.attributes:
    run_migrations(config.attributes["connection"])
else:
    engine = sa.create_engine(os.environ["SPG_DATABASE_URL"], poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            run_migrations(connection)
    finally:
        engine.dispose()
