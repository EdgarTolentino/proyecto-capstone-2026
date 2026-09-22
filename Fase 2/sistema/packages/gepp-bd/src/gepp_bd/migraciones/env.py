"""Entorno de Alembic. La URL la pone `gepp_bd.migrar`; los modelos, `gepp_bd.modelos`."""

from __future__ import annotations

from alembic import context
from gepp_bd.modelos import Base
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = Base.metadata


def correr_sin_conexion() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def correr_con_conexion() -> None:
    motor = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with motor.connect() as conexion:
        context.configure(connection=conexion, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    correr_sin_conexion()
else:
    correr_con_conexion()
