"""Cuadro de la vista en vivo: imagen nítida con las cajas de persona, casco y chaleco.

Es una excepción acotada a «nunca cuadros completos» (`02-privacidad-y-cumplimiento.md`, sección
«Excepción: vista en vivo del procesamiento»). La imagen sale NÍTIDA (reducida a 640 px) y **sin
tapar ningún rostro**, por decisión de Edgar Tolentino del 2026-10-09 (ver ADR-006): todas las
caras quedan visibles. Lo único que se ennegrece son los polígonos de privacidad.

Función pura: no abre archivos, no lee el reloj, no conoce al trabajador. La imagen que recibe debe
ser la que vio el detector (con los polígonos de privacidad ya en negro), no el cuadro original.
"""

from __future__ import annotations

from collections.abc import Iterable

import cv2
import numpy as np
from gepp_core import Caja, ClaseDetectada, Deteccion

ANCHO_VIVO = 640
CALIDAD_VIVO = 70
#: BGR. Solo se dibujan estas clases; lo demás no se muestra.
COLORES = {
    ClaseDetectada.PERSONA: (0, 200, 255),
    ClaseDetectada.CASCO: (0, 200, 0),
    ClaseDetectada.CHALECO: (255, 160, 0),
}


def _a_px(caja: Caja, alto: int, ancho: int) -> tuple[int, int, int, int]:
    return (
        round(caja.x1 * ancho),
        round(caja.y1 * alto),
        round(caja.x2 * ancho),
        round(caja.y2 * alto),
    )


def componer_vista(
    imagen_bgr: np.ndarray, detecciones: Iterable[Deteccion], *, ancho: int = ANCHO_VIVO
) -> np.ndarray:
    """La imagen de la vista antes de codificarla: reducida y con las cajas."""
    detecciones = list(detecciones)
    alto0, ancho0 = imagen_bgr.shape[:2]
    if ancho0 > ancho:  # se reduce, nunca se agranda
        imagen_bgr = cv2.resize(
            imagen_bgr, (ancho, max(1, round(alto0 * ancho / ancho0))), interpolation=cv2.INTER_AREA
        )
    vista = imagen_bgr.copy()
    alto, ancho_px = vista.shape[:2]
    for d in detecciones:
        color = COLORES.get(d.clase)
        if color is not None:
            x1, y1, x2, y2 = _a_px(d.caja, alto, ancho_px)
            cv2.rectangle(vista, (x1, y1), (x2, y2), color, 2)
    return vista


def cuadro_en_vivo(
    imagen_bgr: np.ndarray,
    detecciones: Iterable[Deteccion],
    *,
    ancho: int = ANCHO_VIVO,
    calidad: int = CALIDAD_VIVO,
) -> bytes:
    """El JPEG de la vista en vivo de un cuadro. `imagen_bgr` ya lleva los polígonos de
    privacidad aplicados (la copia que vio el detector)."""
    vista = componer_vista(imagen_bgr, detecciones, ancho=ancho)
    ok, codificado = cv2.imencode(".jpg", vista, [cv2.IMWRITE_JPEG_QUALITY, calidad])
    if not ok:
        raise RuntimeError("no se pudo codificar el cuadro en vivo")
    return codificado.tobytes()
