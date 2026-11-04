"""Los `n` visibles de un reporte salen redondeados al múltiplo de 5 más cercano (#140).

Sin el redondeo, restar dos consultas con `desde`/`hasta` distintos despejaba una celda chica:
5 casos en la primera semana y 1 en la segunda daban `n = 5` y `n = 6`.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

import pytest
from gepp_api.servicios.reportes import N_MINIMO, a_csv, celda, redondear_a_multiplo
from gepp_bd import transaccion
from gepp_bd.repositorios import hallazgos
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine

from ..conftest import T0
from .conftest import Cliente

SEMANAS = 8


@pytest.mark.parametrize(
    ("n", "esperado"),
    [(5, 5), (6, 5), (7, 5), (8, 10), (9, 10), (10, 10), (12, 10), (13, 15), (100, 100)],
)
def test_redondea_al_multiplo_de_5_mas_cercano(n: int, esperado: int) -> None:
    fila = celda("Zona A", n)
    assert (fila["n"], fila["valor"]) == (esperado, float(esperado))
    assert fila["datos_insuficientes"] is False


@pytest.mark.parametrize("n", [-1, 0, 1, 4])
def test_bajo_el_umbral_sigue_suprimido_sin_n_ni_valor(n: int) -> None:
    assert celda("Zona A", n) == {
        "etiqueta": "Zona A",
        "valor": None,
        "n": None,
        "datos_insuficientes": True,
    }
    assert N_MINIMO == 5  # el umbral no cambió; solo lo que se muestra


@pytest.mark.parametrize(
    ("x", "esperado"),
    [(0.0, 0), (2.25, 0), (2.5, 5), (2.75, 5), (7.25, 5), (7.5, 10), (12.5, 15), (17.5, 20)],
)
def test_el_empate_sube_en_vez_de_ir_al_par(x: float, esperado: int) -> None:
    # 2,5 es el empate entre 0 y 5; 7,5 entre 5 y 10; `round()` los mandaría al par (0, 10, 10, 20).
    assert redondear_a_multiplo(x) == esperado


@pytest.mark.parametrize("x", [-1.0, -0.25, float("nan"), float("inf")])
def test_un_conteo_invalido_no_se_corrige_en_silencio(x: float) -> None:
    with pytest.raises(ValueError, match="redondear"):
        redondear_a_multiplo(x)


def test_la_serie_semanal_tambien_se_redondea_y_el_cero_sigue_en_cero() -> None:
    serie = [0.0, 0.0, 5.0, 6.0, 7.0, 8.0, 12.0, 13.0]
    assert celda("Zona A", 60, serie)["serie"] == [0.0, 0.0, 5.0, 5.0, 5.0, 10.0, 10.0, 15.0]


def test_una_semana_de_uno_a_cuatro_sigue_quitando_la_serie_entera() -> None:
    # La regla de la serie mira los valores exactos, no los redondeados.
    assert "serie" not in celda("Zona A", 14, [0.0] * 6 + [4.0, 10.0])


def test_el_escenario_del_140_las_dos_respuestas_dan_lo_mismo() -> None:
    # 5 casos en [01-01, 01-08) y 1 en [01-08, 01-15): ventana larga n = 6, ventana corta n = 5.
    larga, corta = celda("Cámara 02", 6), celda("Cámara 02", 5)
    assert larga["n"] == corta["n"] == 5
    assert larga["valor"] - corta["valor"] == 0  # la resta ya no revela el 1


def test_el_csv_hereda_el_redondeo() -> None:
    datos = {"filas": [celda("casco", 7), celda("chaleco", 3), celda("botas", 13)]}
    filas = {f["etiqueta"]: f for f in csv.DictReader(io.StringIO(a_csv(datos)))}
    assert (filas["casco"]["n"], filas["casco"]["valor"]) == ("5", "5.0")
    assert (filas["botas"]["n"], filas["botas"]["valor"]) == ("15", "15.0")
    assert filas["chaleco"]["n"] == "" and filas["chaleco"]["datos_insuficientes"] == "true"


@pytest.mark.integration
def test_con_la_api_real_la_resta_de_dos_ventanas_no_despeja_nada(
    api: Cliente, bd: Engine, datos: dict[str, Any]
) -> None:
    """Escenario exacto del #140, contra la base: 5 casos la primera semana y 1 la segunda."""
    del datos
    with transaccion(bd) as s:
        for i, dias in enumerate([0, 0, 0, 0, 0, 8]):
            inicio = T0 + timedelta(days=dias, hours=3, minutes=i)
            hallazgos.guardar(
                s,
                Hallazgo(
                    track_id=i + 1,
                    regla_id=2,
                    regla_version=1,
                    epp_faltante=frozenset({TipoEPP.CHALECO}),
                    severidad=Severidad.CRITICA,
                    ts_inicio=inicio,
                    ts_fin=inicio + timedelta(seconds=10),
                    cuadros_confirmados=50,
                    confianza_media=0.8,
                ),
                hallazgos.Contexto(fuente_id=2, area_id=2),
            )

    def fila(hasta: str) -> dict[str, Any]:
        ruta = f"/reportes/zonas?desde=2026-09-01T00:00:00Z&hasta={hasta}&segmentacion=camara"
        r = api.llamar("obtenerReporte", "GET", ruta, headers={"Authorization": "Bearer demo"})
        return {f["etiqueta"]: f for f in r["filas"]}["Cámara 02 · obra gruesa"]

    larga = fila("2026-09-15T00:00:00Z")  # 6 casos reales
    corta = fila("2026-09-08T00:00:00Z")  # 5 casos reales
    assert larga["n"] == corta["n"] == 5
    assert larga["valor"] == corta["valor"] == 5.0
