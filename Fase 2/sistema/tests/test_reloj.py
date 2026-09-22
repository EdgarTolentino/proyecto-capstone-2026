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

#: El reloj nace en `FuenteArchivo` leyendo metadatos o mtime, nunca la hora de proceso:
#: por eso la ingesta y la visión entran en la vigilancia igual que el dominio.
PAQUETES_VIGILADOS = ("gepp-core", "gepp-worker", "gepp-vision")


def _modulos_vigilados() -> list[Path]:
    return [
        archivo
        for paquete in PAQUETES_VIGILADOS
        for archivo in sorted((PAQUETES / paquete / "src").rglob("*.py"))
    ]


def test_una_deteccion_sin_zona_horaria_no_se_construye() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        Deteccion(
            capture_ts=datetime(2026, 9, 2, 2, 10),  # noqa: DTZ001 — es lo que se prueba
            cuadro_idx=0,
            clase=ClaseDetectada.PERSONA,
            caja=Caja(0.1, 0.1, 0.2, 0.5),
            confianza=0.9,
        )


def test_la_vigilancia_cubre_ingesta_y_vision() -> None:
    nombres = {archivo.name for archivo in _modulos_vigilados()}
    assert {
        "dominio.py",
        "fuente_archivo.py",
        "muestreo.py",
        "privacidad.py",
        "vigilante.py",
        "cola.py",
        "trabajador.py",
        "evidencia.py",
    } <= nombres


def test_ningun_modulo_de_dominio_llama_al_reloj_del_sistema() -> None:
    """Prohibido `datetime.now()` en el dominio, la ingesta y la visión.

    Se comprueba sobre el árbol sintáctico, no con una búsqueda de texto: así no
    lo saltan ni un alias ni un comentario.
    """
    infractores: list[str] = []
    for archivo in _modulos_vigilados():
        arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
        for nodo in ast.walk(arbol):
            es_llamada_al_reloj = (
                isinstance(nodo, ast.Call)
                and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr in {"now", "utcnow", "today"}
            )
            if es_llamada_al_reloj:
                infractores.append(f"{archivo.relative_to(PAQUETES)}:{nodo.lineno}")

    assert not infractores, (
        "El dominio no puede leer el reloj del sistema; el timestamp viene del "
        f"cuadro capturado. Ver ADR-005. Infractores: {infractores}"
    )
