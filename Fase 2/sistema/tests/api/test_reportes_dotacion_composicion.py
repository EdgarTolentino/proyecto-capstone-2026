# ruff: noqa: F811 — `api` es un fixture importado del archivo de la tasa y se usa como argumento
"""Composición de la dotación (KPI 7): total y conteos, TODO O NADA.

Ocultar solo lo chico con el total a la vista se despeja por diferencia (5, 4, 4 con total 13) y
entre ventanas (un día con 2 mujeres y otro con 10 dan un promedio que obliga al 2).
"""

from __future__ import annotations

from datetime import date

import pytest
from gepp_api.servicios.reportes import _promedio
from sqlalchemy import Engine

from .conftest import Cliente
from .test_reportes_dotacion import (  # noqa: F401 — fixtures compartidos
    ACCESO,
    TURNO_A,
    _dotacion,
    _dotacion_dias,
    _filas,
    _hallazgos,
    _tokens,
    api,
)

pytestmark = pytest.mark.integration
SEP1, SEP2 = date(2026, 9, 1), date(2026, 9, 2)
FILA = f"{ACCESO} · Turno A"


def _dot(api: Cliente, ventana: str = "") -> dict[str, int | bool | None]:
    ruta = "/reportes/dotacion" + (f"?{ventana}" if ventana else "?desde=2026-09-01T00:00:00Z")
    return _filas(api, ruta)[FILA]["dotacion"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("h", "m", "o", "esperado"),
    [
        (24, 8, 8, (40, 24, 8, 8)),  # nada chico: todo
        (18, 6, 0, (24, 18, 6, 0)),  # un 0 es publicable
        (9, 6, 0, (15, 9, 6, 0)),
        (20, 0, 0, (20, 20, 0, 0)),
        (5, 0, 0, (5, 5, 0, 0)),  # total justo en 5
        (5, 4, 4, (13, None, None, None)),  # ocultar solo los 4 delataría los dos
        (18, 4, 0, (22, None, None, None)),  # 22 - 18 = 4
        (30, 12, 1, (43, None, None, None)),
        (20, 3, 2, (25, None, None, None)),
        (4, 0, 0, (None, None, None, None)),  # total < 5: ni el total
    ],
)
def test_la_composicion_se_publica_entera_o_no_se_publica(
    api: Cliente, bd: Engine, h: int, m: int, o: int, esperado: tuple[int | None, ...]
) -> None:
    _hallazgos(bd, 1, 10, TURNO_A)
    _dotacion(bd, 1, "A", h, m, o)
    dot = _dot(api, "desde=2026-09-01T00:00:00Z&hasta=2026-09-03T00:00:00Z")
    assert (dot["total"], dot["hombres"], dot["mujeres"], dot["otro"]) == esperado
    assert dot["datos_insuficientes"] is (esperado[1] is None)


@pytest.mark.parametrize("campo", [1, 2, 3])
@pytest.mark.parametrize(("valor", "publica"), [(4, False), (5, True), (6, True)])
def test_cada_categoria_se_suprime_justo_bajo_cinco(
    api: Cliente, bd: Engine, campo: int, valor: int, publica: bool
) -> None:
    conteos = [20, 20, 20]
    conteos[campo - 1] = valor
    _dotacion(bd, 1, "A", *conteos)
    dot = _dot(api, "desde=2026-09-01T00:00:00Z&hasta=2026-09-03T00:00:00Z")
    assert dot["total"] == sum(conteos)
    assert (dot["hombres"] is not None) is publica


def test_ni_la_combinacion_de_ventanas_despeja_un_conteo_chico(api: Cliente, bd: Engine) -> None:
    _dotacion_dias(bd, 1, "A", {SEP1: (20, 2, 0), SEP2: (20, 10, 0)})
    dia1 = _dot(api, "desde=2026-09-01T04:00:00Z&hasta=2026-09-02T04:00:00Z")
    dia2 = _dot(api, "desde=2026-09-02T04:00:00Z&hasta=2026-09-03T04:00:00Z")
    junto = _dot(api, "desde=2026-09-01T04:00:00Z&hasta=2026-09-03T04:00:00Z")
    assert (dia1["total"], dia1["mujeres"]) == (22, None)
    assert (dia2["total"], dia2["hombres"], dia2["mujeres"]) == (30, 20, 10)
    # Con los dos días el promedio de mujeres (6) obligaría a que el día 1 tuviera 2.
    assert (junto["total"], junto["hombres"], junto["mujeres"]) == (26, None, None)


def test_un_promedio_publicado_bajo_cinco_tampoco_se_publica(api: Cliente, bd: Engine) -> None:
    # Cada día es 0 o >= 5, pero el promedio de mujeres (3,33 → 3) sería un 3 publicado.
    _dotacion_dias(bd, 1, "A", {date(2026, 8, 31): (20, 10, 0), SEP1: (20, 0, 0), SEP2: (20, 0, 0)})
    dot = _dot(api, "desde=2026-08-31T04:00:00Z&hasta=2026-09-03T04:00:00Z")
    assert (dot["total"], dot["hombres"], dot["mujeres"]) == (23, None, None)


def test_con_dias_distintos_se_publica_el_promedio_de_cada_categoria(
    api: Cliente, bd: Engine
) -> None:
    _dotacion_dias(
        bd, 1, "A", {date(2026, 8, 31): (20, 10, 0), SEP1: (20, 10, 0), SEP2: (20, 5, 0)}
    )
    dot = _dot(api, "desde=2026-08-31T04:00:00Z&hasta=2026-09-03T04:00:00Z")
    assert (dot["total"], dot["hombres"], dot["mujeres"], dot["otro"]) == (28, 20, 8, 0)


def test_sin_dotacion_registrada_no_hay_objeto_dotacion(api: Cliente, bd: Engine) -> None:
    _hallazgos(bd, 2, 10, TURNO_A)
    assert "dotacion" not in _filas(api)["Frente de obra gruesa · Turno A"]


def test_el_promedio_redondea_la_mitad_hacia_arriba() -> None:
    assert _promedio([4, 4, 5]) == 4  # 4,33
    assert _promedio([4, 5]) == 5  # 4,5: justo en el umbral
    assert _promedio([4, 4, 4, 5]) == 4  # 4,25
    assert _promedio([5]) == 5
