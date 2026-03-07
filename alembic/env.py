"""Alembic environment configuration."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment if available
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Import all models so Alembic sees them
from app.database import Base
from app.auth.models import User  # noqa: F401
from app.core.models import Site, Unit, Tenant, RecurringCostItem, WaterRule  # noqa: F401
from app.sources.models import (  # noqa: F401
    SourceConnection, EntityMapping, ImportJob, ImportedFile,
    RawMeasurement, NormalizedMeasurement,
)
from app.billing.models import HourlyPrice, PricingRule, CalculationRun, CalculationLineItem  # noqa: F401
from app.audit.models import AuditLog  # noqa: F401
from app.documents.models import Document  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
