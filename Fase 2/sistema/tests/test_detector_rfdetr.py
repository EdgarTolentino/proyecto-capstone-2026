"""RF-DETR con PyTorch (PT-08): batería común y paridad con el ONNX exportado.

Solo en la máquina con GPU (`make setup-gpu`), con pesos reales:

    GEPP_PESOS_RFDETR=modelos/rfdetr-nano.pth     (con su rfdetr-nano.clases.json al lado)
    GEPP_MODELO_RUTA=modelos/rfdetr-nano.onnx     (el mismo modelo, exportado)
    GEPP_VIDEO_PRUEBA=pruebas_videos/generativa.mp4

    uv run pytest -m gpu tests/test_detector_rfdetr.py

Verificado el 24-sep-2026 con RF-DETR Nano de COCO sobre cuatro cuadros de dos videos de
obra: las mismas personas, cajas y confianzas en los dos adaptadores (a dos decimales).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from gepp_vision import Detector

from .contrato_detector import ContratoDetector

pytestmark = pytest.mark.gpu
pytest.importorskip("rfdetr", reason="necesita el extra gpu: make setup-gpu")


def _ruta(variable: str) -> Path:
    valor = os.environ.get(variable)
    if not valor or not Path(valor).is_file():
        pytest.skip(f"falta {variable} con un archivo real")
    return Path(valor)


class TestDetectorRFDETR(ContratoDetector):
    @pytest.fixture(scope="class")
    def detector(self) -> Detector:
        from gepp_vision.detectores.rfdetr import DetectorRFDETR

        return DetectorRFDETR(_ruta("GEPP_PESOS_RFDETR"))


def _huella(
    d: Detector, imagen: np.ndarray, idx: int
) -> list[tuple[str, float, float, float, float, float]]:
    ts = datetime(2026, 9, 24, tzinfo=UTC)
    return sorted(
        (
            x.clase.value,
            round(x.caja.x1, 2),
            round(x.caja.y1, 2),
            round(x.caja.x2, 2),
            round(x.caja.y2, 2),
            round(x.confianza, 2),
        )
        for x in d.detectar(imagen, cuadro_idx=idx, capture_ts=ts)
    )


def test_onnx_y_pytorch_ven_lo_mismo() -> None:
    from gepp_vision.detectores import DetectorOnnx
    from gepp_vision.detectores.rfdetr import DetectorRFDETR

    pytorch = DetectorRFDETR(_ruta("GEPP_PESOS_RFDETR"))
    onnx = DetectorOnnx(_ruta("GEPP_MODELO_RUTA"))
    captura = cv2.VideoCapture(str(_ruta("GEPP_VIDEO_PRUEBA")))
    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    for idx in (total // 4, total // 2):
        captura.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, imagen = captura.read()
        assert ok
        esperado = _huella(pytorch, imagen, idx)
        assert esperado, "el cuadro de prueba debería tener al menos una persona"
        assert _huella(onnx, imagen, idx) == esperado
