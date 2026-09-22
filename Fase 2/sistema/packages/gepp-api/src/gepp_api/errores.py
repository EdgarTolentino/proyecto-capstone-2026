"""Errores con la forma `{codigo, mensaje, detalle}` del esquema `Error` del contrato."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorApi(Exception):
    def __init__(
        self, estado: int, codigo: str, mensaje: str, detalle: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mensaje)
        self.estado, self.codigo, self.mensaje, self.detalle = estado, codigo, mensaje, detalle


def no_encontrado(que: str, id_: int) -> ErrorApi:
    return ErrorApi(404, f"{que}_no_encontrado", f"No existe {que.replace('_', ' ')} {id_}")


def sin_permiso(mensaje: str = "Tu rol no alcanza para esta acción") -> ErrorApi:
    return ErrorApi(403, "sin_permiso", mensaje)


def registrar(app: FastAPI) -> None:
    @app.exception_handler(ErrorApi)
    async def _error_api(_: Request, e: ErrorApi) -> JSONResponse:
        return JSONResponse(
            {"codigo": e.codigo, "mensaje": e.mensaje, "detalle": e.detalle}, status_code=e.estado
        )

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, e: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "codigo": "peticion_invalida",
                "mensaje": "La petición no cumple el contrato",
                "detalle": {"errores": e.errors()},
            },
            status_code=422,
        )
