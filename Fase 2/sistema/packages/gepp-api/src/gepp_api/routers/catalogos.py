"""Catálogos, estado de la cabecera y sesión."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from gepp_bd.modelos import Area, Faena, Fuente, Hallazgo, Video, Zona
from sqlalchemy import func, select

from gepp_api.auth import Bd, Sesion
from gepp_api.config import TURNOS
from gepp_api.servicios.cobertura import cobertura

router = APIRouter(tags=["Catálogos"])

EPP = ["casco", "chaleco", "lentes", "guantes", "arnes", "calzado"]


def _refs(bd: Bd, modelo: Any) -> list[dict[str, Any]]:
    filas = bd.execute(select(modelo.id, modelo.nombre).order_by(modelo.id)).all()
    return [{"id": f.id, "nombre": f.nombre} for f in filas]


@router.get("/catalogos", operation_id="obtenerCatalogos")
def obtener_catalogos(bd: Bd, sesion: Sesion) -> dict[str, Any]:
    del sesion  # basta con estar autenticado
    return {
        "obras": _refs(bd, Faena),
        "areas": _refs(bd, Area),
        "zonas": _refs(bd, Zona),
        "fuentes": _refs(bd, Fuente),
        "turnos": [{"codigo": t.codigo, "etiqueta": t.etiqueta} for t in TURNOS],
        "epp": EPP,
    }


@router.get("/estado", operation_id="obtenerEstado")
def obtener_estado(request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    """Barata: la cabecera la consulta cada pocos segundos."""
    por_estado = dict(
        bd.execute(select(Video.estado, func.count()).group_by(Video.estado)).tuples().all()
    )
    pendientes = select(func.count()).where(Hallazgo.estado == "por_revisar")
    if sesion.rol == "supervisor":
        pendientes = pendientes.where(Hallazgo.area_id == sesion.area_id)
    # Lo que falló y volvió a la cola también espera turno.
    en_cola = por_estado.get("en_cola", 0) + por_estado.get("reintentando", 0)
    return {
        "ingesta": {
            "activa": por_estado.get("procesando", 0) + en_cola > 0,
            "en_proceso": por_estado.get("procesando", 0),
            "en_cola": en_cola,
        },
        "cobertura": cobertura(bd, request.app.state.config.zona_horaria),
        "pendientes_por_revisar": bd.scalar(pendientes) or 0,
    }


@router.get("/yo", operation_id="obtenerSesion")
def obtener_sesion(sesion: Sesion) -> dict[str, Any]:
    return {
        "id": sesion.id,
        "nombre": sesion.nombre,
        "rol": sesion.rol,
        "area_id": sesion.area_id,
        "permisos": list(sesion.permisos),
    }
