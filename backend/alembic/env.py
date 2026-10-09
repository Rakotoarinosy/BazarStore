"""Environnement Alembic : URL depuis les settings (.env), métadonnées depuis les modèles SQLAlchemy."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.infrastructure.config import get_settings

# Importer models enregistre toutes les tables dans Base.metadata (requis pour --autogenerate).
from src.infrastructure.persistence import models  # noqa: F401
from src.infrastructure.persistence.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Le dépôt contient encore des modèles de l'ancien service citoyen pour
# compatibilité, mais les migrations BazarStore ne gèrent que l'authentification.
ACTIVE_TABLES = {
    "users", "refresh_tokens", "product_categories", "products", "storefront_settings",
    "orders", "order_items",
}


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    table = obj if type_ == "table" else getattr(obj, "table", None)
    return table is None or table.name in ACTIVE_TABLES

# SQLite ne sait pas faire ALTER TABLE : le mode batch recrée la table à la place.
IS_SQLITE = get_settings().database_url.startswith("sqlite")


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=IS_SQLITE,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            render_as_batch=IS_SQLITE,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
