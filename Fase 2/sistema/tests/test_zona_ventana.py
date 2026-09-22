"""La regla mira solo dentro de su zona y de su horario (PT-12)."""

from __future__ import annotations

from dataclasses import replace
from datetime import time, timedelta

import pytest
from gepp_core import Caja, Regla, Ventana, agregar, fraccion_en_poligono, punto_en_poligono

from .conftest import PERSONA, T0, cuadro

CUADRADO = ((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0))  # mitad izquierda del cuadro
#: En L: la esquina superior derecha queda FUERA. Prueba que no es un rectángulo envolvente.
ELE = ((0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (1.0, 0.5), (1.0, 1.0), (0.0, 1.0))


def test_punto_en_poligono_concavo() -> None:
    assert punto_en_poligono((0.25, 0.25), ELE)
    assert punto_en_poligono((0.75, 0.75), ELE)
    assert not punto_en_poligono((0.75, 0.25), ELE)


@pytest.mark.parametrize(
    ("caja", "esperado"),
    [
        (Caja(0.1, 0.1, 0.3, 0.9), 1.0),
        (Caja(0.4, 0.1, 0.6, 0.9), 0.5),
        (Caja(0.6, 0.1, 0.9, 0.9), 0.0),
    ],
)
def test_fraccion_de_la_caja_en_la_zona(caja: Caja, esperado: float) -> None:
    assert fraccion_en_poligono(caja, CUADRADO) == pytest.approx(esperado, abs=1 / 64)


def _secuencia(segundos: float = 6.0, fps: float = 5.0, persona: Caja = PERSONA):  # type: ignore[no-untyped-def]
    return [
        cuadro(t=i / fps, idx=i, con_casco=False, persona=persona)
        for i in range(int(segundos * fps))
    ]


def test_dentro_de_la_zona_dispara_y_fuera_no(regla: Regla) -> None:
    # PERSONA ocupa x 0,40-0,52: dentro de la mitad izquierda solo en parte (~83 %).
    en_zona = replace(regla, zona=CUADRADO)
    assert len(list(agregar(en_zona, _secuencia()))) == 1
    fuera = replace(regla, zona=((0.6, 0.0), (1.0, 0.0), (1.0, 1.0), (0.6, 1.0)))
    assert list(agregar(fuera, _secuencia())) == []


def test_salir_de_la_zona_cierra_la_racha(regla: Regla) -> None:
    """3 s dentro sin casco y después afuera: el hallazgo dura lo que estuvo dentro."""
    dentro, afuera = PERSONA, Caja(0.70, 0.20, 0.82, 0.80)
    cuadros = [
        cuadro(t=i / 5, idx=i, con_casco=False, persona=dentro if i < 15 else afuera)
        for i in range(40)
    ]
    (h,) = agregar(replace(regla, zona=CUADRADO), cuadros)
    assert h.duracion_segundos == pytest.approx(2.8)


# T0 = 02:10 UTC del 2-sep = 22:10 en Santiago (UTC-4).
@pytest.mark.parametrize(
    ("desde", "hasta", "dispara"),
    [
        (time(20), time(8), True),  # turno B, cruza la medianoche
        (time(8), time(20), False),  # turno A
        (time(22, 10), time(23), True),  # borde: `desde` incluido
        (time(21), time(22, 10), False),  # borde: `hasta` excluido
    ],
)
def test_la_ventana_se_mide_en_hora_local(
    regla: Regla, desde: time, hasta: time, dispara: bool
) -> None:
    con_ventana = replace(regla, ventana=Ventana(desde, hasta, "America/Santiago"))
    assert bool(list(agregar(con_ventana, _secuencia()))) is dispara


def test_la_ventana_en_utc_daria_otra_respuesta(regla: Regla) -> None:
    """Guarda contra comparar en UTC: 02:10 UTC cae en 00-08 UTC, pero no en 00-08 local."""
    ventana_local = replace(regla, ventana=Ventana(time(0), time(8), "America/Santiago"))
    ventana_utc = replace(regla, ventana=Ventana(time(0), time(8), "UTC"))
    assert list(agregar(ventana_local, _secuencia())) == []
    assert len(list(agregar(ventana_utc, _secuencia()))) == 1


@pytest.mark.parametrize("fps", [5.0, 10.0])
def test_zona_y_ventana_son_invariantes_a_la_cadencia(regla: Regla, fps: float) -> None:
    """Terminado significa (#35): la misma regla en segundos da lo mismo a 5 y a 10 fps."""
    r = replace(regla, zona=CUADRADO, ventana=Ventana(time(20), time(8)))
    (h,) = agregar(r, _secuencia(fps=fps))
    assert h.ts_inicio == T0
    assert h.duracion_segundos == pytest.approx(6.0 - 1 / fps)
    assert h.ts_inicio + timedelta(seconds=h.duracion_segundos) == h.ts_fin
