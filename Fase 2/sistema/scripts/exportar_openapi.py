"""Compara las operaciones que sirve la API con las de `contracts/openapi.yaml`.

    make contrato

Falla si falta una operación, si sobra una o si una cambió de método, ruta u `operationId`.
La FORMA de cada respuesta la verifican las pruebas de `tests/api/`, que validan cada JSON
real contra los esquemas del YAML. Entre las dos cosas, el contrato manda (ADR-003).

Con `--escribir RUTA` guarda además el OpenAPI que genera FastAPI, para inspeccionarlo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi.openapi.utils import get_openapi
from gepp_api.config import PREFIJO

RAIZ = Path(__file__).resolve().parents[1]
CONTRATO = RAIZ / "contracts" / "openapi.yaml"


def operaciones_contrato() -> set[tuple[str, str, str]]:
    paths = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))["paths"]
    return {(m.upper(), r, op["operationId"]) for r, ms in paths.items() for m, op in ms.items()}


def openapi_app() -> dict[str, Any]:
    from fastapi import FastAPI
    from gepp_api.app import incluir_routers

    app = FastAPI()
    incluir_routers(app)  # sin base de datos: solo interesa la forma de las rutas
    return get_openapi(title="gepp-api", version="0", routes=app.routes)


def operaciones_app(especificacion: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {
        (m.upper(), r.removeprefix(PREFIJO), op["operationId"])
        for r, ms in especificacion["paths"].items()
        if r.startswith(PREFIJO)
        for m, op in ms.items()
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--escribir", type=Path)
    args = p.parse_args(argv)
    especificacion = openapi_app()
    if args.escribir:
        args.escribir.write_text(json.dumps(especificacion, indent=2, ensure_ascii=False))
    contrato, app = operaciones_contrato(), operaciones_app(especificacion)
    for falta in sorted(contrato - app):
        print(f"FALTA en la API: {falta[0]} {falta[1]} ({falta[2]})", file=sys.stderr)
    for sobra in sorted(app - contrato):
        print(f"SOBRA en la API: {sobra[0]} {sobra[1]} ({sobra[2]})", file=sys.stderr)
    if contrato != app:
        return 1
    print(f"Contrato cumplido: {len(contrato)} operaciones")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
