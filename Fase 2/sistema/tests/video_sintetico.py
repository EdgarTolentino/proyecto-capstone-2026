"""Video sintético para las pruebas: cuadros de colores con un rectángulo que se mueve.

Sin personas, sin descargas, sin GPU: se genera con NumPy y se escribe con OpenCV en
`tmp_path` (ver `09-plan-de-desarrollo-vision.md`, §2.3).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ANCHO = 160
ALTO = 120


def cuadro_sintetico(indice: int, ancho: int = ANCHO, alto: int = ALTO) -> np.ndarray:
    """Fondo que cambia de color con el índice y un rectángulo blanco que avanza."""
    imagen = np.zeros((alto, ancho, 3), dtype=np.uint8)
    imagen[:, :] = ((indice * 7) % 256, (indice * 3) % 256, 90)
    x = (indice * 4) % (ancho - 30)
    imagen[40:80, x : x + 30] = 255
    return imagen


def escribir_video(ruta: Path, *, fps: float, segundos: float) -> Path:
    """Escribe un .mp4 de `segundos` a `fps` y devuelve la ruta."""
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), fps, (ANCHO, ALTO))
    if not escritor.isOpened():
        raise RuntimeError("OpenCV no pudo abrir el escritor de video")
    for indice in range(round(fps * segundos)):
        escritor.write(cuadro_sintetico(indice))
    escritor.release()
    return ruta
