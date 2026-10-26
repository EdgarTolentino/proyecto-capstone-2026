"""La zona `mosaico` y sus parámetros, sin base de datos (#203)."""

from __future__ import annotations

import pytest
from gepp_core import Caja
from gepp_worker.trabajador import ParametrosMosaico, recorte_de_mosaico

RECTANGULO = [[0.25, 0.25], [0.75, 0.25], [0.75, 0.5], [0.25, 0.5]]


def test_sin_zona_de_mosaico_se_analiza_el_cuadro_entero() -> None:
    assert recorte_de_mosaico([]) is None


def test_el_recorte_es_la_caja_que_encierra_el_poligono() -> None:
    assert recorte_de_mosaico([RECTANGULO]) == Caja(0.25, 0.25, 0.75, 0.5)
    triangulo = [[0.5, 0.25], [0.75, 0.75], [0.25, 0.5]]
    assert recorte_de_mosaico([triangulo]) == Caja(0.25, 0.25, 0.75, 0.75)


def test_los_bordes_del_cuadro_valen() -> None:
    entero = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    assert recorte_de_mosaico([entero]) == Caja(0.0, 0.0, 1.0, 1.0)


@pytest.mark.parametrize("fuera", [-0.25, 1.25])
def test_un_vertice_fuera_del_cuadro_detiene(fuera: float) -> None:
    with pytest.raises(ValueError, match=r"fuera de 0\.\.1"):
        recorte_de_mosaico([[*RECTANGULO[:3], [fuera, 0.5]]])


def test_dos_zonas_de_mosaico_detienen_en_vez_de_elegir_una() -> None:
    with pytest.raises(LookupError, match="2 zonas de mosaico"):
        recorte_de_mosaico([RECTANGULO, RECTANGULO])


def test_un_poligono_sin_area_detiene() -> None:
    with pytest.raises(ValueError, match="degenerada"):
        recorte_de_mosaico([[[0.5, 0.25], [0.5, 0.75], [0.5, 0.5]]])


# ── Entorno del trabajador ──────────────────────────────────────────────────────


def test_los_parametros_del_mosaico_salen_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    from gepp_worker.__main__ import _parametros_mosaico

    for v in ("FACTOR", "LADO", "OBJETO_MAX_PX"):
        monkeypatch.delenv(f"GEPP_MOSAICO_{v}", raising=False)
    assert _parametros_mosaico() == ParametrosMosaico(factor=2.0, lado=384, objeto_max_px=100)
    monkeypatch.setenv("GEPP_MOSAICO_FACTOR", "2.5")
    monkeypatch.setenv("GEPP_MOSAICO_LADO", "512")
    monkeypatch.setenv("GEPP_MOSAICO_OBJETO_MAX_PX", "120")
    assert _parametros_mosaico() == ParametrosMosaico(factor=2.5, lado=512, objeto_max_px=120)


@pytest.mark.parametrize(
    ("variable", "texto"),
    [
        ("GEPP_MOSAICO_FACTOR", "0"),
        ("GEPP_MOSAICO_FACTOR", "-0.5"),
        ("GEPP_MOSAICO_FACTOR", "2,5"),  # coma decimal
        ("GEPP_MOSAICO_LADO", "512.5"),  # entero
        ("GEPP_MOSAICO_OBJETO_MAX_PX", "cien"),
    ],
)
def test_un_parametro_invalido_detiene_el_arranque_con_su_variable(
    monkeypatch: pytest.MonkeyPatch, variable: str, texto: str
) -> None:
    from gepp_worker.__main__ import _parametros_mosaico

    monkeypatch.setenv(variable, texto)
    with pytest.raises(SystemExit, match=variable):
        _parametros_mosaico()


def test_el_parametro_justo_sobre_cero_vale(monkeypatch: pytest.MonkeyPatch) -> None:
    from gepp_worker.__main__ import _parametros_mosaico

    monkeypatch.setenv("GEPP_MOSAICO_FACTOR", "0.25")
    assert _parametros_mosaico().factor == 0.25
