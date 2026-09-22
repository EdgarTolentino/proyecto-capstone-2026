"""Motor y sesión desde `GEPP_BD_URL`.

Ningún módulo abre conexiones por su cuenta: todos piden el motor aquí, para que la
URL se lea en un solo lugar y las pruebas puedan apuntar a otra base.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

VARIABLE_URL = "GEPP_BD_URL"


def url_desde_entorno() -> str:
    url = os.environ.get(VARIABLE_URL)
    if not url:
        raise RuntimeError(
            f"Falta {VARIABLE_URL}. Copia .env.example a .env o expórtala "
            "(p. ej. postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp)."
        )
    return url


def crear_motor(url: str | None = None) -> Engine:
    return create_engine(url or url_desde_entorno(), pool_pre_ping=True)


def fabrica_de_sesiones(motor: Engine) -> sessionmaker[Session]:
    return sessionmaker(motor, expire_on_commit=False)


@contextmanager
def transaccion(motor: Engine) -> Iterator[Session]:
    """Una unidad de trabajo: confirma al salir, deshace si algo falla.

    Es lo que sostiene el patrón outbox: el hallazgo y su notificación se escriben en la
    misma transacción o no se escribe ninguno (ADR-008).
    """
    with fabrica_de_sesiones(motor)() as sesion, sesion.begin():
        yield sesion
