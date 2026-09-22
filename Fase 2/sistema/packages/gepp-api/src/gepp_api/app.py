"""La aplicación FastAPI. Cumple `contracts/openapi.yaml` y no importa la visión (ADR-007).

uv run python -m gepp_api          # http://localhost:8000/api/v1
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gepp_bd.sesion import crear_motor, fabrica_de_sesiones
from sqlalchemy import Engine

from gepp_api import errores
from gepp_api.config import PREFIJO, Configuracion
from gepp_api.routers import catalogos, hallazgos, metricas, panel, reglas, reportes, videos


def crear_app(motor: Engine | None = None, config: Configuracion | None = None) -> FastAPI:
    config = config or Configuracion()
    app = FastAPI(
        title="Guardián EPP — API",
        version="0.1.0",
        description="Ver contracts/openapi.yaml: el contrato manda.",
    )
    app.state.config = config
    app.state.motor = motor or crear_motor()
    app.state.fabrica = fabrica_de_sesiones(app.state.motor)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.origenes_cors),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )
    errores.registrar(app)
    incluir_routers(app)
    metricas.montar(app)
    return app


def incluir_routers(app: FastAPI) -> None:
    """Separado de `crear_app` para que `make contrato` inspeccione las rutas sin base."""
    for modulo in (hallazgos, catalogos, videos, reglas, panel, reportes):
        app.include_router(modulo.router, prefix=PREFIJO)
