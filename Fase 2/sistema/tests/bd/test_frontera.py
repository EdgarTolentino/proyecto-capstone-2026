"""Las fronteras del monorepo se cumplen por test, no por convención (ADR-007, ADR-012).

En el espacio de trabajo todos los paquetes comparten un solo entorno virtual, así que nada
impide `import gepp_vision` desde `gepp_api`: lo único que lo detiene es este test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PAQUETES = Path(__file__).resolve().parents[2] / "packages"

#: paquete -> módulos de primer nivel que no puede importar.
PROHIBIDOS: dict[str, set[str]] = {
    # ADR-012: solo depende de `gepp-core`; ni visión, ni trabajador, ni web.
    "gepp-bd": {"gepp_vision", "gepp_worker", "gepp_api", "fastapi", "cv2", "torch"},
    # ADR-007: la API corre sin GPU y no importa visión. Se comunica con el trabajador por la
    # base de datos, no por Redis, y no procesa imágenes (hoy no usa numpy ni cv2).
    "gepp-api": {"gepp_vision", "gepp_worker", "cv2", "torch", "numpy", "redis"},
}


def _infracciones(paquete: str) -> tuple[int, list[str]]:
    """(archivos revisados, `archivo:línea importa módulo` de cada import prohibido)."""
    raiz = PAQUETES / paquete / "src"
    archivos = sorted(raiz.rglob("*.py"))
    infractores: list[str] = []
    for archivo in archivos:
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres = [nodo.module]
            else:
                continue
            for n in nombres:
                if n.split(".")[0] in PROHIBIDOS[paquete]:
                    ruta = archivo.relative_to(raiz)
                    infractores.append(f"{ruta}:{nodo.lineno} importa {n}")
    return len(archivos), infractores


@pytest.mark.parametrize("paquete", sorted(PROHIBIDOS))
def test_el_paquete_no_cruza_su_frontera(paquete: str) -> None:
    revisados, infractores = _infracciones(paquete)
    assert revisados > 0, f"no hay fuentes en packages/{paquete}/src: el test no vigila nada"
    assert not infractores, f"{paquete} cruza su frontera (ADR-007/012): {infractores}"
