"""
Alembic environment configuration for the Fee Management System.

This file is loaded by Alembic when running migration commands.  It
imports the Flask application factory and SQLAlchemy ``db`` instance so
that Alembic can discover all model metadata and use the same
``DATABASE_URL`` that Flask uses at runtime.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import the Flask app and db so that all models are registered with
# SQLAlchemy's metadata before Alembic inspects it.
# ---------------------------------------------------------------------------
# We need to be on the Python path that includes the backend package.
import sys

# Ensure the backend directory is on sys.path so `app` and `config` are importable.
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app, db  # noqa: E402
import app.models  # noqa: E402, F401 — side-effect: registers all models

# Create a minimal Flask app to access config (uses FLASK_ENV or "default")
flask_app = create_app(os.environ.get("FLASK_ENV", "development"))

# Override the sqlalchemy.url in alembic.ini with the value from Flask config
# so that a single DATABASE_URL env var drives both Flask and Alembic.
config.set_main_option(
    "sqlalchemy.url",
    flask_app.config["SQLALCHEMY_DATABASE_URI"],
)

# Target metadata for autogenerate support
target_metadata = db.metadata


# ---------------------------------------------------------------------------
# Offline migration mode
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migration mode
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
