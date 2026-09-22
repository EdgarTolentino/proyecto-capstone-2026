"""Batería común del puerto `Detector` (PT-07).

Todo detector —el falso hoy, RF-DETR y ONNX con el primer modelo (PT-08)— hereda esta
clase y define la fixture `detector`. Si un adaptador nuevo no la pasa, no entra: así el
cambio de backend no cambia el comportamiento que ven el seguidor y el agregador.

    class TestDetectorOnnx(ContratoDetector):
        @pytest.fixture
        def detector(self) -> Detector:
            return DetectorOnnx(RUTA_MODELO)
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from gepp_vision import Detector

from .conftest import T0

IMAGEN = np.zeros((120, 160, 3), dtype=np.uint8)


class ContratoDetector:
    @pytest.fixture
    def detector(self) -> Detector:
        raise NotImplementedError("cada adaptador define su fixture `detector`")

    def test_cumple_el_protocolo(self, detector: Detector) -> None:
        assert isinstance(detector, Detector)

    def test_declara_una_version_para_auditar(self, detector: Detector) -> None:
        assert isinstance(detector.version, str)
        assert detector.version.strip()

    def test_fecha_con_el_cuadro_que_recibe_y_no_con_el_reloj(self, detector: Detector) -> None:
        for i in range(3):
            ts = T0 + timedelta(seconds=i * 0.2)
            for d in detector.detectar(IMAGEN, cuadro_idx=100 + i, capture_ts=ts):
                assert d.capture_ts == ts
                assert d.cuadro_idx == 100 + i

    def test_no_asigna_identidad(self, detector: Detector) -> None:
        """La identidad es trabajo del seguidor; un detector que la inventa la rompe."""
        for d in detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=T0):
            assert d.track_id is None

    def test_cajas_normalizadas_y_confianza_en_rango(self, detector: Detector) -> None:
        for d in detector.detectar(IMAGEN, cuadro_idx=0, capture_ts=T0):
            assert 0.0 <= d.caja.x1 < d.caja.x2 <= 1.0
            assert 0.0 <= d.caja.y1 < d.caja.y2 <= 1.0
            assert 0.0 <= d.confianza <= 1.0
