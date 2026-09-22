"""PostgreSQL real para las pruebas de persistencia (ADR-012).

Se usa una base aparte, `<base>_pruebas`, creada desde cero en cada corrida: las pruebas
nunca tocan los datos de desarrollo. Sin PostgreSQL disponible se omiten, salvo que
`GEPP_EXIGIR_BD=1` (así corre CI): ahí una base caída es un fallo, no un salto silencioso.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from gepp_bd.migrar import subir
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

URL_POR_DEFECTO = "postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp"

TABLAS = (
    "accion_correctiva",
    "area",
    "auditoria",
    "deteccion",
    "dotacion",
    "evidencia",
    "faena",
    "fuente",
    "hallazgo",
    "notificacion",
    "regla",
    "usuario",
    "video",
    "zona",
)


def _url_de_pruebas() -> str:
    base = make_url(os.environ.get("GEPP_BD_URL", URL_POR_DEFECTO))
    return base.set(database=f"{base.database}_pruebas").render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def url_bd() -> Iterator[str]:
    url = _url_de_pruebas()
    nombre = make_url(url).database
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{nombre}"'))
    except OperationalError as e:
        if os.environ.get("GEPP_EXIGIR_BD") == "1":
            raise
        pytest.skip(f"PostgreSQL no disponible ({e.orig}); `make up` para correr estas pruebas")
    finally:
        admin.dispose()
    subir(url)
    yield url


@pytest.fixture(scope="session")
def motor(url_bd: str) -> Iterator[Engine]:
    m = create_engine(url_bd)
    yield m
    m.dispose()


@pytest.fixture
def bd(motor: Engine) -> Engine:
    """Motor con las tablas vacías. Cada prueba parte de cero."""
    with motor.begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(TABLAS)} RESTART IDENTITY CASCADE"))
    return motor
