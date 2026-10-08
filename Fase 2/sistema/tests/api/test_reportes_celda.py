"""La serie semanal de una celda visible no puede delatar semanas con menos de cinco casos."""

from __future__ import annotations

import pytest
from gepp_api.servicios.reportes import N_MINIMO, celda

SEMANAS = 8


def _serie(*valores: float) -> list[float]:
    return [0.0] * (SEMANAS - len(valores)) + list(valores)


def test_una_semana_justo_en_el_umbral_deja_la_serie() -> None:
    assert celda("Zona A", 5, _serie(N_MINIMO))["serie"] == _serie(5)


def test_una_semana_bajo_el_umbral_quita_la_serie_entera() -> None:
    # Con el total visible, quitar solo esa semana la dejaría despejable por diferencia.
    fila = celda("Zona A", 9, _serie(N_MINIMO - 1, N_MINIMO))
    assert "serie" not in fila
    assert fila["valor"] == 9 and fila["datos_insuficientes"] is False


def test_las_semanas_en_cero_no_delatan_a_nadie() -> None:
    assert celda("Zona A", 12, _serie(6, 0, 6))["serie"] == _serie(6, 0, 6)


@pytest.mark.parametrize("semana", [1.0, 2.0, 3.0, 4.0])
def test_cualquier_semana_de_uno_a_cuatro_quita_la_serie(semana: float) -> None:
    assert "serie" not in celda("Zona A", 10, _serie(semana, 10 - semana))


def test_una_celda_suprimida_nunca_trae_serie() -> None:
    assert "serie" not in celda("Zona A", N_MINIMO - 1, _serie(N_MINIMO - 1))


def test_sin_serie_pedida_no_hay_serie() -> None:
    assert "serie" not in celda("Zona A", 7)
