"""Cuadro de la vista en vivo: imagen nítida con las cajas de persona, casco y chaleco, y en rojo
con su etiqueta las de la falta que el modelo vio (`cabeza`, `sin_chaleco`; ADR-013).

Es una excepción acotada a «nunca cuadros completos» (`02-privacidad-y-cumplimiento.md`, sección
«Excepción: vista en vivo del procesamiento»). La imagen sale NÍTIDA (reducida a 640 px) y **sin
tapar ningún rostro**, por decisión de Edgar Tolentino del 2026-10-09 (ver ADR-006): todas las
caras quedan visibles. Lo único que se ennegrece son los polígonos de privacidad.

Función pura: no abre archivos, no lee el reloj, no conoce al trabajador. La imagen que recibe debe
ser la que vio el detector (con los polígonos de privacidad ya en negro), no el cuadro original.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import cv2
import numpy as np
from gepp_core import Caja, ClaseDetectada, Deteccion

from gepp_vision.evidencia import zona_de_rostro

ANCHO_VIVO = 640
CALIDAD_VIVO = 70
#: BGR. Solo se dibujan estas clases; lo demás no se muestra.
COLORES = {
    ClaseDetectada.PERSONA: (0, 200, 255),
    ClaseDetectada.CASCO: (0, 200, 0),
    ClaseDetectada.CHALECO: (255, 160, 0),
    ClaseDetectada.CABEZA: (0, 0, 230),
    ClaseDetectada.SIN_CHALECO: (0, 0, 230),
}
#: Texto de las cajas de falta, en blanco sobre el rojo de la caja.
ETIQUETAS = {
    ClaseDetectada.CABEZA: "SIN CASCO",
    ClaseDetectada.SIN_CHALECO: "SIN CHALECO",
}
_FUENTE, _ESCALA, _GROSOR, _RELLENO = cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1, 3


def _a_px(caja: Caja, alto: int, ancho: int) -> tuple[int, int, int, int]:
    return (
        round(caja.x1 * ancho),
        round(caja.y1 * alto),
        round(caja.x2 * ancho),
        round(caja.y2 * alto),
    )


def _a_px_por_fuera(caja: Caja, alto: int, ancho: int) -> tuple[int, int, int, int]:
    """Como `_a_px`, pero redondeando hacia afuera: un píxel tocado por la caja queda adentro.

    Para las caras, que el rótulo no puede tocar ni en un borde fraccionario (revisión de Codex)."""
    return (
        math.floor(caja.x1 * ancho),
        math.floor(caja.y1 * alto),
        math.ceil(caja.x2 * ancho),
        math.ceil(caja.y2 * alto),
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
    # Las etiquetas van después de todas las cajas, para que ninguna caja las tape.
    rostros = [
        _a_px_por_fuera(zona_de_rostro(d.caja), alto, ancho_px)
        for d in detecciones
        if d.clase is ClaseDetectada.PERSONA
    ]
    ocupados: list[_Rect] = []
    for d in detecciones:
        if (texto := ETIQUETAS.get(d.clase)) is not None:
            _etiquetar(vista, d, texto, evitar=rostros, ocupados=ocupados)
    return vista


_Rect = tuple[int, int, int, int]


def _se_tocan(a: _Rect, b: _Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _etiquetar(
    vista: np.ndarray, d: Deteccion, texto: str, *, evitar: list[_Rect], ocupados: list[_Rect]
) -> None:
    """Rótulo blanco sobre fondo rojo en el primer lugar libre: dentro del cuadro, sin tocar
    ninguna cara (`zona_de_rostro`) ni otro rótulo. `cabeza`: encima de la caja, si no debajo;
    `sin_chaleco`: abajo por dentro (la cintura), si no debajo de la caja, si no arriba por
    dentro. Si ningún lugar sirve, la caja queda roja sin rótulo: nunca se tapa una cara."""
    alto, ancho = vista.shape[:2]
    c = d.caja  # antes de redondear: una caja que asoma 1 px y al reducir queda en ⅓ px, cuenta
    if c.x2 <= 0 or c.x1 >= 1 or c.y2 <= 0 or c.y1 >= 1:
        return  # la caja cae entera fuera del cuadro: no hay a quién rotular
    x1, y1, _, y2 = _a_px(c, alto, ancho)
    (w, h), base = cv2.getTextSize(texto, _FUENTE, _ESCALA, _GROSOR)
    ancho_rotulo, alto_rotulo = w + 2 * _RELLENO, h + base + 2 * _RELLENO
    if d.clase is ClaseDetectada.CABEZA:
        candidatos = [y1 - alto_rotulo, y2]
    else:
        candidatos = [y2 - alto_rotulo, y2, y1]
    izquierda = min(max(x1, 0), max(ancho - ancho_rotulo, 0))
    for arriba in candidatos:
        rotulo = (izquierda, arriba, izquierda + ancho_rotulo, arriba + alto_rotulo)
        if arriba < 0 or rotulo[3] > alto or rotulo[2] > ancho:
            continue
        if any(_se_tocan(rotulo, otro) for otro in (*evitar, *ocupados)):
            continue
        ocupados.append(rotulo)
        cv2.rectangle(
            vista, rotulo[:2], (rotulo[2] - 1, rotulo[3] - 1), COLORES[d.clase], cv2.FILLED
        )
        cv2.putText(
            vista,
            texto,
            (izquierda + _RELLENO, arriba + _RELLENO + h),
            _FUENTE,
            _ESCALA,
            (255, 255, 255),
            _GROSOR,
            cv2.LINE_AA,
        )
        return


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
