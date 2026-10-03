"""RF-DETR con PyTorch, para la máquina con GPU (PT-08): entrenamiento y evaluación.

`rfdetr` arrastra torch y CUDA (varios GB), así que es un extra opcional: `make setup-gpu`
lo instala y el CI no. Por eso se importa dentro del constructor y no arriba.

Solo las variantes N, S, M y L: las XL y 2XL no son Apache-2.0 (ADR-002).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from gepp_core import Caja, Deteccion

from gepp_vision.detectores.rfdetr_comun import UMBRAL_CONFIANZA, MapaDeClases

#: Variante -> clase de `rfdetr`. Nada más: las XL y 2XL tienen otra licencia.
VARIANTES = {
    "nano": "RFDETRNano",
    "small": "RFDETRSmall",
    "medium": "RFDETRMedium",
    "large": "RFDETRLarge",
}


def usar_precision_completa() -> None:
    """Apaga TF32 en la GPU, para que PyTorch dé las mismas confianzas que el ONNX en CPU.

    Con TF32, PyTorch se aparta del ONNX hasta 0,146 de confianza (558 de 574 imágenes iguales
    en la validación del modelo v1); sin él, 574 de 574 (#109). Se evaluaría un modelo distinto
    del que se despliega. TF32 tiene dos interruptores y cada uno basta para desviar la
    confianza: el de matmul lo enciende `import rfdetr` (`set_float32_matmul_precision("high")`
    en su `detr.py`) y el de cuDNN viene encendido en torch. Afecta a todo el proceso, así que
    se llama después de `import rfdetr`."""
    import torch

    torch.set_float32_matmul_precision("highest")
    torch.backends.cudnn.allow_tf32 = False


class DetectorRFDETR:
    """Cumple el protocolo `Detector`."""

    def __init__(
        self,
        pesos: Path,
        *,
        variante: str = "nano",
        mapa: MapaDeClases | None = None,
        umbral: float = UMBRAL_CONFIANZA,
    ) -> None:
        if variante not in VARIANTES:
            raise ValueError(f"variante {variante!r} no permitida; use una de {sorted(VARIANTES)}")
        if not 0 < umbral < 1:
            raise ValueError("umbral debe estar entre 0 y 1")
        import rfdetr  # extra `gpu`: ver el docstring del módulo

        usar_precision_completa()
        self._mapa = mapa or MapaDeClases.desde_json(MapaDeClases.junto_a(pesos))
        self._umbral = umbral
        self._modelo: Any = getattr(rfdetr, VARIANTES[variante])(pretrain_weights=str(pesos))
        huella = hashlib.sha256(pesos.read_bytes()).hexdigest()[:12]
        self._version = f"rfdetr-{variante}:{self._mapa.version}:{huella}"

    @property
    def version(self) -> str:
        return self._version

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        from PIL import Image

        alto, ancho = imagen.shape[:2]
        rgb = Image.fromarray(cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB))
        resultado = self._modelo.predict(rgb, threshold=self._umbral)
        salida = []
        for xyxy, clase_idx, confianza in zip(
            resultado.xyxy, resultado.class_id, resultado.confidence, strict=True
        ):
            clase = self._mapa.clases.get(int(clase_idx))
            if clase is None:
                continue
            x1, y1 = max(float(xyxy[0]) / ancho, 0.0), max(float(xyxy[1]) / alto, 0.0)
            x2, y2 = min(float(xyxy[2]) / ancho, 1.0), min(float(xyxy[3]) / alto, 1.0)
            if x2 <= x1 or y2 <= y1:
                continue
            salida.append(
                Deteccion(
                    capture_ts=capture_ts,
                    cuadro_idx=cuadro_idx,
                    clase=clase,
                    caja=Caja(x1, y1, x2, y2),
                    confianza=float(confianza),
                )
            )
        return salida
