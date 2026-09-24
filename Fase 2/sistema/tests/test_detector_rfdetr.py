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
from gepp_core import Deteccion
from gepp_vision import Detector
from scipy.optimize import linear_sum_assignment

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


#: Solo se comparan las detecciones con margen sobre el corte del detector: una a 0,251 en un
#: adaptador puede salir a 0,249 en el otro y caerse del corte, y eso no es una diferencia.
MARGEN = 0.05


def _emparejar(a: list[Deteccion], b: list[Deteccion]) -> list[tuple[Deteccion, Deteccion]]:
    """Emparejamiento óptimo (húngaro) por IoU dentro de cada clase, con IoU >= 0,9."""
    iou = np.array([[x.caja.iou(y.caja) if x.clase is y.clase else 0.0 for y in b] for x in a])
    if iou.size == 0:
        return []
    filas, columnas = linear_sum_assignment(-iou)
    return [(a[f], b[c]) for f, c in zip(filas, columnas, strict=True) if iou[f, c] >= 0.9]


def test_onnx_y_pytorch_ven_lo_mismo() -> None:
    """Las mismas detecciones (IoU >= 0,9 con su par) y confianzas a menos de 0,02, en tres
    cuadros. Verificado el 24-sep en los cinco videos de `pruebas_videos`."""
    from gepp_vision.detectores import DetectorOnnx
    from gepp_vision.detectores.rfdetr import DetectorRFDETR
    from gepp_vision.detectores.rfdetr_comun import UMBRAL_CONFIANZA

    pytorch = DetectorRFDETR(_ruta("GEPP_PESOS_RFDETR"))
    onnx = DetectorOnnx(_ruta("GEPP_MODELO_RUTA"))
    captura = cv2.VideoCapture(str(_ruta("GEPP_VIDEO_PRUEBA")))
    total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
    ts = datetime(2026, 9, 24, tzinfo=UTC)
    firme = UMBRAL_CONFIANZA + MARGEN
    for idx in (total // 4, total // 2, 3 * total // 4):
        captura.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, imagen = captura.read()
        assert ok
        de_pytorch = [
            d
            for d in pytorch.detectar(imagen, cuadro_idx=idx, capture_ts=ts)
            if d.confianza >= firme
        ]
        de_onnx = [
            d for d in onnx.detectar(imagen, cuadro_idx=idx, capture_ts=ts) if d.confianza >= firme
        ]
        assert de_pytorch, "el cuadro de prueba debería tener al menos una persona"
        pares = _emparejar(de_onnx, de_pytorch)
        assert len(pares) == len(de_onnx) == len(de_pytorch), f"cuadro {idx}"
        for x, y in pares:
            assert x.confianza == pytest.approx(y.confianza, abs=0.02)
