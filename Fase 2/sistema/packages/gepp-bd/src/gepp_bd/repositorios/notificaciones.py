"""Lado del despachador del outbox: tomar pendientes, marcar el resultado, acusar recibo.

Las marcas de tiempo las pone PostgreSQL (`now()`): son hora de envío, no de captura, y así
ningún módulo de Python necesita leer el reloj del sistema (ADR-005).
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from gepp_bd.modelos import Notificacion

#: Tras este número de intentos fallidos la notificación queda `fallida` y deja de reintentarse.
MAXIMO_INTENTOS = 5


def tomar_pendientes(sesion: Session, limite: int = 20) -> list[Notificacion]:
    """Bloquea y devuelve las pendientes más antiguas.

    `SKIP LOCKED` deja que dos despachadores corran a la vez sin enviar el mismo aviso dos
    veces: cada uno se salta las filas que el otro ya tomó.
    """
    consulta = (
        select(Notificacion)
        .where(Notificacion.estado == "pendiente")
        .order_by(Notificacion.creada_en, Notificacion.id)
        .limit(limite)
        .with_for_update(skip_locked=True)
    )
    return list(sesion.execute(consulta).scalars())


def marcar_enviada(sesion: Session, notificacion_id: int) -> None:
    sesion.execute(
        update(Notificacion)
        .where(Notificacion.id == notificacion_id)
        .values(estado="enviada", intentos=Notificacion.intentos + 1, enviada_en=func.now())
    )


def marcar_fallo(sesion: Session, notificacion_id: int) -> str:
    """Cuenta un intento fallido. Devuelve el estado resultante."""
    intentos = sesion.execute(
        update(Notificacion)
        .where(Notificacion.id == notificacion_id)
        .values(intentos=Notificacion.intentos + 1)
        .returning(Notificacion.intentos)
    ).scalar_one()
    estado = "fallida" if intentos >= MAXIMO_INTENTOS else "pendiente"
    sesion.execute(
        update(Notificacion).where(Notificacion.id == notificacion_id).values(estado=estado)
    )
    return estado


def acusar(sesion: Session, notificacion_id: int, usuario_id: int | None) -> None:
    """Cierra el ciclo: alguien recibió el aviso. Solo se acusa lo que se envió."""
    resultado = sesion.execute(
        update(Notificacion)
        .where(Notificacion.id == notificacion_id, Notificacion.estado == "enviada")
        .values(estado="acusada", acusada_en=func.now(), acusada_por=usuario_id)
        .returning(Notificacion.id)
    ).scalar_one_or_none()
    if resultado is None:
        raise ValueError(f"la notificación {notificacion_id} no está enviada: no se puede acusar")
