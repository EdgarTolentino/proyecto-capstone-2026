"""`gepp-bd` depende solo de `gepp-core` (ADR-012): ni visión ni web."""

from __future__ import annotations

import ast
from pathlib import Path

FUENTES = Path(__file__).resolve().parents[2] / "packages" / "gepp-bd" / "src"
PROHIBIDOS = {"gepp_vision", "gepp_worker", "gepp_api", "fastapi", "cv2", "torch"}


def test_gepp_bd_no_importa_vision_trabajador_ni_web() -> None:
    infractores: list[str] = []
    for archivo in FUENTES.rglob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres = [nodo.module]
            else:
                continue
            for n in nombres:
                if n.split(".")[0] in PROHIBIDOS:
                    infractores.append(f"{archivo.name}:{nodo.lineno} importa {n}")
    assert not infractores, f"gepp-bd cruza la frontera de ADR-012: {infractores}"
