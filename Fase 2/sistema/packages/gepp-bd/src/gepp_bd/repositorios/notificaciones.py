"""Lado del despachador del outbox: tomar pendientes, marcar el resultado, acusar recibo.

Las marcas de tiempo las pone PostgreSQL (`now()`): son hora de envío, no de captura, y así
ningún módulo de Python necesita leer el reloj del sistema (ADR-005).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from gepp_bd.modelos import Notificacion

#: Tras este número de intentos fallidos la notificación queda `fallida` y deja de reintentarse.
MAXIMO_INTENTOS = 5


def tomar_pendientes(
    sesion: Session, limite: int = 20, *, tipo: str | None = None
) -> list[Notificacion]:
    """Bloquea y devuelve las pendientes más antiguas que ya pueden intentarse.

    `SKIP LOCKED` deja que dos despachadores corran a la vez sin enviar el mismo aviso dos
    veces: cada uno se salta las filas que el otro ya tomó. Las que fallaron hace poco esperan
    su `reintentar_despues`.
    """
    consulta = (
        select(Notificacion)
        .where(
            Notificacion.estado == "pendiente",
            (Notificacion.reintentar_despues.is_(None))
            | (Notificacion.reintentar_despues <= func.now()),
        )
        .order_by(Notificacion.creada_en, Notificacion.id)
        .limit(limite)
        .with_for_update(skip_locked=True)
    )
    if tipo is not None:
        consulta = consulta.where(Notificacion.tipo == tipo)
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


# ── Operaciones por grupo: un aviso de Telegram puede cubrir varias filas ──────────────────


def marcar_grupo_enviado(
    sesion: Session, ids: Sequence[int], *, id_externo: str, token_acuse: str
) -> None:
    sesion.execute(
        update(Notificacion)
        .where(Notificacion.id.in_(ids))
        .values(
            estado="enviada",
            intentos=Notificacion.intentos + 1,
            enviada_en=func.now(),
            id_externo=id_externo,
            token_acuse=token_acuse,
            reintentar_despues=None,
        )
    )


def marcar_grupo_fallido(
    sesion: Session, ids: Sequence[int], *, reintentar_en_s: float, motivo: str
) -> None:
    """Fallo transitorio: suma un intento y espera. Al llegar al máximo queda `fallida`."""
    sesion.execute(
        update(Notificacion)
        .where(Notificacion.id.in_(ids))
        .values(
            intentos=Notificacion.intentos + 1,
            reintentar_despues=func.now() + timedelta(seconds=reintentar_en_s),
            motivo=motivo,
        )
    )
    sesion.execute(
        update(Notificacion)
        .where(Notificacion.id.in_(ids), Notificacion.intentos >= MAXIMO_INTENTOS)
        .values(estado="fallida")
    )


def marcar_grupo_rechazado(sesion: Session, ids: Sequence[int], *, motivo: str) -> None:
    """Rechazo permanente del canal (destino inválido, bot bloqueado): no se reintenta."""
    sesion.execute(
        update(Notificacion)
        .where(Notificacion.id.in_(ids))
        .values(estado="fallida", intentos=Notificacion.intentos + 1, motivo=motivo)
    )


def bajar_al_resumen(sesion: Session, ids: Sequence[int], *, motivo: str) -> None:
    sesion.execute(
        update(Notificacion)
        .where(Notificacion.id.in_(ids))
        .values(tipo="resumen_turno", motivo=motivo)
    )


def acusar_por_token(sesion: Session, token: str) -> int:
    """El toque en "Acuso recibo". Acusa TODO el grupo del aviso y devuelve cuántas filas.

    Solo se acusa lo enviado; un token repetido no hace nada (un solo uso).
    """
    filas = sesion.execute(
        update(Notificacion)
        .where(Notificacion.token_acuse == token, Notificacion.estado == "enviada")
        .values(estado="acusada", acusada_en=func.now())
        .returning(Notificacion.id)
    ).scalars()
    return len(list(filas))
