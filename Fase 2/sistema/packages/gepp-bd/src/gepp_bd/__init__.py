"""Guardián EPP — persistencia compartida.

Dueño del esquema (ADR-012): modelos, migraciones y repositorios. Depende solo de
`gepp-core`; `gepp-api` y `gepp-worker` dependen de él y nunca uno del otro.
"""

from gepp_bd.modelos import Base
from gepp_bd.sesion import crear_motor, transaccion

__all__ = ["Base", "crear_motor", "transaccion"]
