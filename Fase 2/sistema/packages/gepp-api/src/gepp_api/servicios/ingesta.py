"""Pedir que se procese un video de la carpeta de entrada (el trabajador lo atiende después).

La API nunca devuelve rutas del servidor: solo nombres. Tampoco habla con Redis; deja un pedido
en la base (ADR-012) y el trabajador calcula el hash, registra el video y lo encola.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from gepp_bd.modelos import Fuente, PedidoIngesta, Video
from gepp_bd.repositorios import auditoria, pedidos
from gepp_core.archivos import (
    EXTENSIONES_VIDEO,
    ArchivoNoEncontrado,
    ErrorArchivo,
    NombreInvalido,
    validar_nombre_en_carpeta,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from gepp_api.auth import SesionActual
from gepp_api.errores import ErrorApi
from gepp_api.servicios.hallazgos import iso


def carpeta_de_entrada(carpeta: Path | None) -> Path:
    if carpeta is None:
        raise ErrorApi(
            409,
            "entrada_no_configurada",
            "El servidor no tiene carpeta de entrada (GEPP_CARPETA_ENTRADA)",
        )
    return carpeta


def listar_entrada(bd: Session, carpeta: Path, tz: ZoneInfo) -> list[dict[str, Any]]:
    """Los videos pedibles, del más reciente al más antiguo. Un nombre que no pasaría el POST
    (enlace, oculto, vacío, no video…) no se lista."""
    try:
        nombres = sorted(p.name for p in carpeta.iterdir())
    except OSError:
        raise ErrorApi(
            409, "entrada_no_configurada", "La carpeta de entrada no se puede leer"
        ) from None
    hallados: list[tuple[str, int, int]] = []
    for nombre in nombres:
        if Path(nombre).suffix.lower() not in EXTENSIONES_VIDEO:
            continue
        try:
            info = validar_nombre_en_carpeta(carpeta, nombre).lstat()
        except (ErrorArchivo, OSError):
            continue
        hallados.append((nombre, info.st_size, info.st_mtime_ns))
    conocidos = {
        (Path(ruta).name, tamano)
        for ruta, tamano in bd.execute(
            select(Video.ruta, Video.bytes).where(Video.bytes.in_({h[1] for h in hallados}))
        ).tuples()
    }
    hallados.sort(key=lambda h: (-h[2], h[0]))
    return [
        {
            "archivo": nombre,
            "bytes": tamano,
            "modificado": iso(datetime.fromtimestamp(mtime_ns / 1e9, tz=UTC), tz),
            "posible_duplicado": (nombre, tamano) in conocidos,
        }
        for nombre, tamano, mtime_ns in hallados
    ]


def pedido_a_json(p: PedidoIngesta, fuente: Fuente | None, tz: ZoneInfo) -> dict[str, Any]:
    return {
        "id": p.id,
        "archivo": p.archivo,
        "fuente": {"id": fuente.id, "nombre": fuente.nombre} if fuente else None,
        "estado": p.estado,
        "motivo": p.motivo,
        "video_id": p.video_id,
        "creado_en": iso(p.creado_en, tz),
    }


def listar_pedidos(bd: Session, tz: ZoneInfo) -> list[dict[str, Any]]:
    filas = pedidos.recientes(bd, 50)
    fuentes = {f.id: f for f in bd.execute(select(Fuente)).scalars()}
    return [pedido_a_json(p, fuentes.get(p.fuente_id), tz) for p in filas]


def pedir(
    bd: Session, sesion: SesionActual, carpeta: Path, archivo: str, fuente_id: int, tz: ZoneInfo
) -> dict[str, Any]:
    try:
        validar_nombre_en_carpeta(carpeta, archivo)
    except NombreInvalido as e:
        raise ErrorApi(422, "peticion_invalida", str(e)) from None
    except ArchivoNoEncontrado as e:
        raise ErrorApi(404, "archivo_no_encontrado", str(e)) from None
    fuente = bd.get(Fuente, fuente_id)
    if fuente is None:
        raise ErrorApi(404, "fuente_no_encontrada", f"No existe la fuente {fuente_id}")
    if not fuente.activa:
        raise ErrorApi(409, "fuente_inactiva", f"La fuente {fuente.nombre} está desactivada")
    try:
        pedido = pedidos.crear(bd, archivo=archivo, fuente_id=fuente.id, usuario_id=sesion.id)
    except pedidos.PedidoExistente:
        raise ErrorApi(
            409, "pedido_existente", "Ese archivo ya tiene un pedido pendiente o en proceso"
        ) from None
    auditoria.registrar(
        bd,
        usuario_id=sesion.id,
        rol=sesion.rol,
        accion="video:ingesta",
        entidad="pedido_ingesta",
        entidad_id=pedido.id,
        motivo=f"archivo={archivo} fuente_id={fuente.id}",
    )
    return pedido_a_json(pedido, fuente, tz)
