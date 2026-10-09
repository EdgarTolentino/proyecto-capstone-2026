"""Pedidos de ingesta: la API los crea, el trabajador los toma y los cierra (ADR-012).

Ciclo: `pendiente` → `tomado` → `registrado` | `rechazado`. Un archivo tiene a lo sumo un pedido
abierto (`pendiente` o `tomado`): lo impone un índice único parcial, no un chequeo previo, así
que dos pedidos simultáneos del mismo archivo no pueden crear dos.

Los tiempos los pone la base (`now()`); este módulo no mira el reloj (ADR-005).
"""

from __future__ import annotations

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gepp_bd.modelos import PedidoIngesta

LIMITE_RECIENTES = 50


class PedidoExistente(Exception):
    """Ya hay un pedido `pendiente` o `tomado` para ese archivo."""


def crear(
    sesion: Session, *, archivo: str, fuente_id: int, usuario_id: int | None = None
) -> PedidoIngesta:
    """Crea un pedido `pendiente`. Lanza `PedidoExistente` si el archivo ya tiene uno abierto.

    Un pedido `registrado` o `rechazado` no cuenta: se puede volver a pedir el archivo.
    """
    sentencia = (
        insert(PedidoIngesta)
        .values(archivo=archivo, fuente_id=fuente_id, usuario_id=usuario_id)
        .on_conflict_do_nothing(
            index_elements=["archivo"], index_where=text("estado IN ('pendiente','tomado')")
        )
        .returning(PedidoIngesta.id)
    )
    nuevo_id = sesion.execute(sentencia).scalar_one_or_none()
    if nuevo_id is None:
        raise PedidoExistente(archivo)
    pedido = sesion.get(PedidoIngesta, nuevo_id)
    assert pedido is not None
    return pedido


def tomar_siguiente(sesion: Session) -> PedidoIngesta | None:
    """El `pendiente` más antiguo pasa a `tomado`. Dos trabajadores a la vez no toman el mismo:
    `FOR UPDATE SKIP LOCKED` salta la fila que otro ya reservó."""
    pedido = sesion.execute(
        select(PedidoIngesta)
        .where(PedidoIngesta.estado == "pendiente")
        .order_by(PedidoIngesta.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if pedido is None:
        return None
    pedido.estado = "tomado"
    pedido.actualizado_en = func.now()
    sesion.flush()
    sesion.refresh(pedido)
    return pedido


def _cerrar(
    sesion: Session,
    pedido_id: int,
    estado: str,
    *,
    motivo: str | None,
    video_id: int | None,
    bytes_: int | None,
    mtime_ns: int | None,
) -> bool:
    valores: dict[str, object] = {
        "estado": estado,
        "motivo": motivo,
        "video_id": video_id,
        "actualizado_en": func.now(),
    }
    # Lo medido al tomarlo solo se pisa si quien cierra lo trae.
    if bytes_ is not None:
        valores["bytes"] = bytes_
    if mtime_ns is not None:
        valores["mtime_ns"] = mtime_ns
    cerrado = sesion.execute(
        update(PedidoIngesta)
        .where(PedidoIngesta.id == pedido_id, PedidoIngesta.estado == "tomado")
        .values(**valores)
        .returning(PedidoIngesta.id)
    ).scalar_one_or_none()
    sesion.expire_all()
    return cerrado is not None


def registrar(
    sesion: Session,
    pedido_id: int,
    video_id: int,
    *,
    bytes: int | None = None,
    mtime_ns: int | None = None,
) -> bool:
    """`tomado` → `registrado`, con la fila `video` que lo atiende. False si no estaba `tomado`."""
    return _cerrar(
        sesion,
        pedido_id,
        "registrado",
        motivo=None,
        video_id=video_id,
        bytes_=bytes,
        mtime_ns=mtime_ns,
    )


def rechazar(
    sesion: Session,
    pedido_id: int,
    motivo: str,
    *,
    bytes: int | None = None,
    mtime_ns: int | None = None,
) -> bool:
    """`tomado` → `rechazado`. `motivo` no debe llevar rutas del servidor. False si no estaba
    `tomado`."""
    return _cerrar(
        sesion,
        pedido_id,
        "rechazado",
        motivo=motivo,
        video_id=None,
        bytes_=bytes,
        mtime_ns=mtime_ns,
    )


def recuperar_tomados(sesion: Session) -> int:
    """Los `tomado` vuelven a `pendiente`: el trabajador murió a la mitad. Se llama al arrancar,
    antes de tomar nada. Devuelve cuántos recuperó."""
    resultado = sesion.execute(
        update(PedidoIngesta)
        .where(PedidoIngesta.estado == "tomado")
        .values(estado="pendiente", actualizado_en=func.now())
        .returning(PedidoIngesta.id)
    ).all()
    sesion.expire_all()
    return len(resultado)


def recientes(sesion: Session, limite: int = LIMITE_RECIENTES) -> list[PedidoIngesta]:
    """Los pedidos más nuevos primero, de cualquier estado."""
    return list(
        sesion.execute(
            select(PedidoIngesta).order_by(PedidoIngesta.id.desc()).limit(limite)
        ).scalars()
    )
