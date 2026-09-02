from __future__ import annotations

import pytest
from gepp_core import Caja


def test_caja_degenerada_no_se_construye() -> None:
    with pytest.raises(ValueError, match="degenerada"):
        Caja(0.5, 0.5, 0.5, 0.9)


def test_franja_superior_es_el_tercio_de_arriba() -> None:
    persona = Caja(0.0, 0.0, 1.0, 1.0)
    cabeza = persona.franja(0.0, 0.30)
    assert cabeza.y1 == pytest.approx(0.0)
    assert cabeza.y2 == pytest.approx(0.30)
    assert cabeza.x1 == persona.x1 and cabeza.x2 == persona.x2


def test_franja_rechaza_rangos_invalidos() -> None:
    persona = Caja(0.0, 0.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="franja"):
        persona.franja(0.5, 0.2)


def test_iou_de_cajas_identicas_es_uno() -> None:
    caja = Caja(0.1, 0.1, 0.3, 0.3)
    assert caja.iou(caja) == pytest.approx(1.0)


def test_iou_de_cajas_disjuntas_es_cero() -> None:
    assert Caja(0.0, 0.0, 0.1, 0.1).iou(Caja(0.5, 0.5, 0.6, 0.6)) == 0.0


def test_fraccion_dentro_de_zona() -> None:
    persona = Caja(0.0, 0.0, 0.2, 0.2)
    zona = Caja(0.1, 0.0, 1.0, 1.0)
    assert persona.fraccion_dentro_de(zona) == pytest.approx(0.5)
