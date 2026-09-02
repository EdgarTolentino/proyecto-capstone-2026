"""El reloj del sistema nace en la captura, no en el procesamiento (ADR-005).

Este test es la barrera que impide el error más caro del proyecto: fechar un evento
con la hora en que se procesó el video en vez de la hora en que ocurrió. Funciona
perfecto en la v1 y vuelve inservible toda la analítica temporal en la v2.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion

PAQUETES = Path(__file__).resolve().parents[1] / "packages"


def test_una_deteccion_sin_zona_horaria_no_se_construye() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        Deteccion(
            capture_ts=datetime(2026, 9, 2, 2, 10),  # noqa: DTZ001 — es lo que se prueba
            cuadro_idx=0,
            clase=ClaseDetectada.PERSONA,
            caja=Caja(0.1, 0.1, 0.2, 0.5),
            confianza=0.9,
        )


def test_ningun_modulo_de_dominio_llama_al_reloj_del_sistema() -> None:
    """Prohibido `datetime.now()` fuera del ingestor.

    Se comprueba sobre el árbol sintáctico, no con una búsqueda de texto: así no
    lo saltan ni un alias ni un comentario.
    """
    infractores: list[str] = []
    for archivo in (PAQUETES / "gepp-core" / "src").rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            es_llamada_al_reloj = (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr in {"now", "utcnow", "today"}
            )
            if es_llamada_al_reloj:
                infractores.append(f"{archivo.name}:{nodo.lineno}")

    assert not infractores, (
        "El dominio no puede leer el reloj del sistema; el timestamp viene del "
        f"cuadro capturado. Ver ADR-005. Infractores: {infractores}"
    )
