"""Los umbrales de una `Regla` se validan al construirla (regla 5: entrada inválida).

Antes el dominio aceptaba `cierre_segundos=0`: la regla terminaba sin hallazgos y sin error,
mientras la API sí rechazaba el cero. Ahora la construcción falla con `ValueError`.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from gepp_core import Regla, Severidad, TipoEPP, agregar

from .conftest import cuadro


def _regla(**umbrales: float) -> Regla:
    return Regla(
        id=1,
        version=1,
        nombre="r",
        epp_exigido=frozenset({TipoEPP.CASCO}),
        severidad=Severidad.ALTA,
        **umbrales,
    )


@pytest.mark.parametrize("cierre", [0.0, -0.25, -1.0, math.nan, math.inf, -math.inf])
def test_un_cierre_que_no_es_positivo_y_finito_se_rechaza(cierre: float) -> None:
    with pytest.raises(ValueError, match="cierre_segundos"):
        _regla(cierre_segundos=cierre)


@pytest.mark.parametrize("confirmacion", [-0.25, -1.0, math.nan, math.inf, -math.inf])
def test_una_confirmacion_negativa_o_no_finita_se_rechaza(confirmacion: float) -> None:
    with pytest.raises(ValueError, match="confirmacion_segundos"):
        _regla(confirmacion_segundos=confirmacion)


def test_el_minimo_positivo_de_cierre_se_construye() -> None:
    """El borde válido de `cierre_segundos > 0`: el menor positivo representable aquí."""
    assert _regla(cierre_segundos=2.0**-20).cierre_segundos == 2.0**-20


@pytest.mark.parametrize("cierre", [0.5, 3.0])
def test_con_un_cierre_mayor_que_el_paso_un_incumplimiento_continuo_es_un_hallazgo(
    cierre: float,
) -> None:
    cuadros = [cuadro(t=i * 0.25, idx=i, con_casco=False) for i in range(13)]  # 3 s, a 4 fps
    regla = _regla(cierre_segundos=cierre, confirmacion_segundos=2.0)
    (h,) = agregar(regla, cuadros)
    assert (h.cuadros_confirmados, h.duracion_segundos) == (13, 3.0)


def test_una_confirmacion_de_cero_es_valida() -> None:
    """El borde de `confirmacion_segundos ≥ 0`: cero confirma con el primer cuadro."""
    regla = _regla(confirmacion_segundos=0.0)
    (h,) = agregar(regla, [cuadro(t=0.0, idx=0, con_casco=False)])
    assert h.cuadros_confirmados == 1


def test_replace_tambien_valida() -> None:
    """`dataclasses.replace` construye de nuevo: un umbral inválido no entra por ahí."""
    with pytest.raises(ValueError, match="cierre_segundos"):
        replace(_regla(), cierre_segundos=0.0)
