"""Reportes agregados. La supresión de celdas pequeñas es del servidor."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from gepp_api.auth import Bd, Sesion
from gepp_api.servicios.reportes import a_csv, reporte

router = APIRouter(tags=["Reportes"])


@router.get("/reportes/{tipo}", operation_id="obtenerReporte")
def obtener_reporte(
    tipo: Literal["ranking-epp", "zonas", "mapa-calor", "tendencia"],
    request: Request,
    bd: Bd,
    sesion: Sesion,
    segmentacion: Literal["zona", "turno", "camara", "epp"] | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    area_id: int | None = None,
    formato: Literal["json", "csv"] = "json",
) -> Response:
    sesion.exigir("ver_reportes")
    datos = reporte(
        bd,
        tipo,
        request.app.state.config.zona_horaria,
        segmentacion=segmentacion,
        desde=desde,
        hasta=hasta,
        area_id=area_id,
    )
    if formato == "csv":
        return Response(
            a_csv(datos),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="reporte-{tipo}.csv"'},
        )
    return JSONResponse(datos)
