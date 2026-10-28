import importlib
import importlib.util
import os
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.modules

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def import_all_models() -> None:
    """Populate ``SQLModel.metadata`` with every module, not only the imported ones.

    Listing the modules by hand is what let the metadata drift from the schema: a
    table missing here makes autogenerate resolve foreign keys against incomplete
    metadata and ``alembic check`` dies instead of reporting drift.
    """
    for package in pkgutil.iter_modules(app.modules.__path__):
        if not package.ispkg:
            continue
        module_name = f"app.modules.{package.name}.models"
        if importlib.util.find_spec(module_name) is None:
            continue
        importlib.import_module(module_name)


import_all_models()


def get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set to run database migrations")
    return database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
