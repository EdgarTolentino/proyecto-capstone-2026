"""Lo que comparten los dos adaptadores de RF-DETR: el mapa de clases y la decodificación.

RF-DETR no trae nombres de clase en sus salidas: da un índice por columna de logits. El
mapa dice qué `ClaseDetectada` es cada índice, y vive en un JSON junto a los pesos:

    modelos/rfdetr-n-epp-v1.onnx
    modelos/rfdetr-n-epp-v1.clases.json   ->  {"version": "rfdetr-n-epp-v1",
                                               "clases": {"1": "persona", "2": "casco"}}

Un índice que no está en el mapa se ignora. Así, un modelo preentrenado en COCO sirve para
probar el recorrido con `{"1": "persona"}`: las otras 90 clases de COCO no entran.

Salidas crudas (`docs/learn/export.md` de RF-DETR): `dets` con cajas (cx, cy, w, h)
normalizadas y `labels` con logits de `num_clases + 1` columnas; la última es "sin objeto".
Las probabilidades son sigmoides por clase, no softmax. RF-DETR no necesita NMS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from gepp_core import Caja, ClaseDetectada, Deteccion

UMBRAL_CONFIANZA = 0.5
#: Normalización de ImageNet, con la que se entrenó el backbone de RF-DETR.
MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIACION = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass(frozen=True, slots=True)
class MapaDeClases:
    version: str
    clases: dict[int, ClaseDetectada]

    @classmethod
    def desde_json(cls, ruta: Path) -> MapaDeClases:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        clases = {int(k): ClaseDetectada(v) for k, v in datos["clases"].items()}
        if not clases:
            raise ValueError(f"{ruta}: el mapa de clases está vacío")
        return cls(version=str(datos.get("version", ruta.stem)), clases=clases)

    @staticmethod
    def junto_a(pesos: Path) -> Path:
        """`modelo.onnx` -> `modelo.clases.json`."""
        return pesos.with_name(f"{pesos.stem}.clases.json")


def preprocesar(imagen_bgr: np.ndarray, alto: int, ancho: int) -> np.ndarray:
    """Cuadro BGR de OpenCV -> tensor NCHW float32 normalizado, del tamaño del modelo."""
    rgb = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB)
    redimensionada = cv2.resize(rgb, (ancho, alto), interpolation=cv2.INTER_LINEAR)
    normalizada = (redimensionada.astype(np.float32) / 255.0 - MEDIA) / DESVIACION
    return np.ascontiguousarray(normalizada.transpose(2, 0, 1)[np.newaxis])


def decodificar(
    cajas_cxcywh: np.ndarray,
    logits: np.ndarray,
    mapa: MapaDeClases,
    *,
    umbral: float,
    cuadro_idx: int,
    capture_ts: datetime,
) -> list[Deteccion]:
    """Salidas crudas de UNA imagen (`(consultas, 4)` y `(consultas, clases + 1)`) ->
    detecciones con la clase del mapa, cajas recortadas a la imagen y `track_id=None`."""
    probabilidades = 1.0 / (1.0 + np.exp(-np.clip(logits[:, :-1], -88, 88)))
    clase_idx = probabilidades.argmax(axis=1)
    confianza = probabilidades.max(axis=1)
    salida = []
    for q in np.flatnonzero(confianza >= umbral):
        clase = mapa.clases.get(int(clase_idx[q]))
        if clase is None:
            continue
        cx, cy, w, h = (float(v) for v in cajas_cxcywh[q])
        x1, y1 = max(cx - w / 2, 0.0), max(cy - h / 2, 0.0)
        x2, y2 = min(cx + w / 2, 1.0), min(cy + h / 2, 1.0)
        if x2 <= x1 or y2 <= y1:
            continue  # caja degenerada o fuera de la imagen
        salida.append(
            Deteccion(
                capture_ts=capture_ts,
                cuadro_idx=cuadro_idx,
                clase=clase,
                caja=Caja(x1, y1, x2, y2),
                confianza=float(confianza[q]),
            )
        )
    return salida
