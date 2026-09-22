"""Detector falso: pasa la batería común y respeta su guion en segundos."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from gepp_core import ClaseDetectada
from gepp_vision import Detector
from gepp_vision.detectores import DetectorFalso, Guion, Segmento

from .conftest import T0
from .contrato_detector import ContratoDetector

FIXTURES = Path(__file__).parent / "fixtures"
IMAGEN = np.zeros((120, 160, 3), dtype=np.uint8)


class TestDetectorFalso(ContratoDetector):
    @pytest.fixture
    def detector(self) -> Detector:
        return DetectorFalso(Guion.desde_json(FIXTURES / "guion_con_casco.json"))


def test_el_guion_es_en_segundos_desde_el_primer_cuadro() -> None:
    detector = DetectorFalso(Guion.desde_json(FIXTURES / "guion_sin_casco.json"))
    dentro = detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=T0)
    casi = detector.detectar(IMAGEN, cuadro_idx=74, capture_ts=T0 + timedelta(seconds=2.96))
    fuera = detector.detectar(IMAGEN, cuadro_idx=75, capture_ts=T0 + timedelta(seconds=3.0))
    assert {d.clase for d in dentro} == {ClaseDetectada.PERSONA, ClaseDetectada.CHALECO}
    assert len(casi) == 2
    assert fuera == []


def test_reiniciar_mueve_el_origen_al_siguiente_video() -> None:
    detector = DetectorFalso(Guion.desde_json(FIXTURES / "guion_sin_casco.json"))
    detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=T0)
    otro_video = T0 + timedelta(hours=1)
    assert detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=otro_video) == []
    detector.reiniciar()
    assert len(detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=otro_video)) == 2


def test_la_version_nombra_el_guion() -> None:
    assert DetectorFalso(Guion.desde_json(FIXTURES / "guion_sin_casco.json")).version == (
        "falso:sin-casco-3s"
    )


def test_un_segmento_invertido_se_rechaza() -> None:
    with pytest.raises(ValueError, match="segmento inválido"):
        Segmento(3.0, 1.0, ())
