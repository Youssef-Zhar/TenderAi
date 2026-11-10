
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.base import Base

# Import all models so SQLAlchemy registers their tables.
import app.models.tender
import app.models.tender_condition
import app.models.tender_criterion
import app.models.tender_document
import app.models.tender_evidence
import app.models.user


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_migration_url() -> URL:
    """Build a dedicated database URL for Alembic migrations."""

    if not settings.db_migration_user.strip():
        raise RuntimeError("DB_MIGRATION_USER must be configured.")

    if not settings.db_migration_password:
        raise RuntimeError("DB_MIGRATION_PASSWORD must be configured.")

    return URL.create(
        drivername="mysql+pymysql",
        username=settings.db_migration_user,
        password=settings.db_migration_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        query={"charset": "utf8mb4"},
    )


def run_migrations_offline() -> None:
    url = get_migration_url().render_as_string(hide_password=True)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    migration_engine = create_engine(
        get_migration_url(),
        poolclass=NullPool,
        pool_pre_ping=True,
    )

    try:
        with migration_engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
