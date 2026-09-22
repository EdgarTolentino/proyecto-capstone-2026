"""Valida respuestas reales contra `contracts/openapi.yaml`. El contrato manda (ADR-003)."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

CONTRATO = Path(__file__).resolve().parents[2] / "contracts" / "openapi.yaml"
URI = "urn:gepp:contrato"


@cache
def contrato() -> dict[str, Any]:
    return yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))


@cache
def _registro() -> Registry:
    return Registry().with_resource(URI, DRAFT202012.create_resource(contrato()))


def operaciones() -> dict[str, tuple[str, str]]:
    """operationId -> (método, ruta) de todas las operaciones del contrato."""
    salida = {}
    for ruta, metodos in contrato()["paths"].items():
        for metodo, op in metodos.items():
            salida[op["operationId"]] = (metodo.upper(), ruta)
    return salida


def _esquema_respuesta(operation_id: str, estado: int) -> dict[str, Any] | None:
    metodo, ruta = operaciones()[operation_id]
    respuestas = contrato()["paths"][ruta][metodo.lower()]["responses"]
    respuesta = respuestas.get(str(estado)) or respuestas.get(f"{str(estado)[0]}XX")
    if respuesta is None:
        raise AssertionError(f"{operation_id} no declara la respuesta {estado} en el contrato")
    if "$ref" in respuesta:
        nombre = respuesta["$ref"].rsplit("/", 1)[-1]
        respuesta = contrato()["components"]["responses"][nombre]
    contenido = respuesta.get("content", {}).get("application/json")
    return contenido["schema"] if contenido else None


def _reescribir(nodo: Any) -> Any:
    """Las referencias internas `#/components/...` pasan a apuntar al documento registrado."""
    if isinstance(nodo, dict):
        return {
            k: (URI + v if k == "$ref" and v.startswith("#") else _reescribir(v))
            for k, v in nodo.items()
        }
    if isinstance(nodo, list):
        return [_reescribir(v) for v in nodo]
    return nodo


def validar(operation_id: str, estado: int, cuerpo: Any) -> None:
    esquema = _esquema_respuesta(operation_id, estado)
    if esquema is None:
        return
    validador = Draft202012Validator(_reescribir(esquema), registry=_registro())
    errores = sorted(validador.iter_errors(cuerpo), key=lambda e: list(e.path))
    assert not errores, f"{operation_id} {estado} no cumple el contrato: " + "; ".join(
        f"{'/'.join(map(str, e.path))}: {e.message}" for e in errores[:5]
    )
