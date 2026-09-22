"""Panel de la portada."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

from gepp_api.auth import Bd, Sesion
from gepp_api.servicios.panel import panel

router = APIRouter(tags=["Panel"])


@router.get("/panel", operation_id="obtenerPanel")
def obtener_panel(
    request: Request,
    bd: Bd,
    sesion: Sesion,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    turno: str | None = None,
    obra_id: int | None = None,
) -> dict[str, Any]:
    sesion.exigir("ver_hallazgos")
    return panel(
        bd,
        sesion,
        request.app.state.config.zona_horaria,
        desde=desde,
        hasta=hasta,
        turno=turno,
        obra_id=obra_id,
    )
