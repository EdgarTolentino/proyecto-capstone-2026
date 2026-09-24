"""RF-DETR exportado a ONNX, sobre ONNX Runtime (PT-08).

Es el detector de las máquinas sin GPU: los compañeros corren el pipeline completo con el
mismo modelo que se entrenó en la máquina con GPU (`detectores/rfdetr.py`), exportado con
`model.export(format="onnx")`. El mapa de clases va en `<modelo>.clases.json`
(`rfdetr_comun.MapaDeClases`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import numpy as np
import onnxruntime as ort
from gepp_core import Deteccion

from gepp_vision.detectores.rfdetr_comun import (
    UMBRAL_CONFIANZA,
    MapaDeClases,
    decodificar,
    preprocesar,
)


class DetectorOnnx:
    """Cumple el protocolo `Detector`."""

    def __init__(
        self,
        modelo: Path,
        *,
        mapa: MapaDeClases | None = None,
        umbral: float = UMBRAL_CONFIANZA,
        proveedores: Sequence[str] = ("CPUExecutionProvider",),
    ) -> None:
        if not 0 < umbral < 1:
            raise ValueError("umbral debe estar entre 0 y 1")
        self._mapa = mapa or MapaDeClases.desde_json(MapaDeClases.junto_a(modelo))
        self._umbral = umbral
        self._sesion = ort.InferenceSession(str(modelo), providers=list(proveedores))
        entrada = self._sesion.get_inputs()[0]
        self._entrada = entrada.name
        self._alto, self._ancho = int(entrada.shape[2]), int(entrada.shape[3])
        # Las salidas se buscan por NOMBRE: con 3 clases, `labels` tiene la misma forma que
        # `dets` y el orden no está garantizado (documentación de RF-DETR).
        nombres = [s.name for s in self._sesion.get_outputs()]
        self._salida_cajas = next((n for n in nombres if "dets" in n), None)
        self._salida_logits = next((n for n in nombres if "labels" in n), None)
        if self._salida_cajas is None or self._salida_logits is None:
            raise ValueError(f"{modelo}: se esperaban salidas 'dets' y 'labels', hay {nombres}")
        huella = hashlib.sha256(modelo.read_bytes()).hexdigest()[:12]
        self._version = f"onnx:{self._mapa.version}:{huella}"

    @property
    def version(self) -> str:
        return self._version

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        tensor = preprocesar(imagen, self._alto, self._ancho)
        cajas, logits = self._sesion.run(
            [self._salida_cajas, self._salida_logits], {self._entrada: tensor}
        )
        return decodificar(
            np.asarray(cajas)[0],
            np.asarray(logits)[0],
            self._mapa,
            umbral=self._umbral,
            cuadro_idx=cuadro_idx,
            capture_ts=capture_ts,
        )
