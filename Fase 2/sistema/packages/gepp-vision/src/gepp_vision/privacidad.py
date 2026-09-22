"""Privacidad aplicada sobre la imagen (ADR-006).

Dos operaciones distintas, en dos momentos distintos:

- **Máscaras de fuente**, ANTES de inferir: los polígonos de tipo `privacidad` de la tabla
  `zona` (baños, casino, tránsito público) se ennegrecen en el cuadro. Lo que no se ve no se
  detecta, no se persiste y no puede aparecer en una evidencia.
- **Difuminado de rostros**, al escribir la evidencia: el recorte llega a disco ya
  anonimizado. Aquí se reciben las cajas; quién las detecta es asunto de `evidencia.py`.

Coordenadas normalizadas 0..1 respecto del cuadro, como en todo el sistema.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np
from gepp_core import Caja

Punto = tuple[float, float]
Poligono = Sequence[Punto]

#: Bloques por lado del rostro pixelado. Con 6 no se reconoce a nadie y el recorte sigue
#: mostrando que hay una cabeza (y si lleva casco, que es lo que importa).
BLOQUES_POR_LADO = 6


def _validar_poligono(poligono: Poligono) -> None:
    if len(poligono) < 3:
        raise ValueError(f"un polígono necesita al menos 3 vértices, tiene {len(poligono)}")
    for x, y in poligono:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"vértice fuera de 0..1: ({x}, {y})")


class MascaraPrivacidad:
    """Los polígonos de privacidad de UNA fuente. La máscara en píxeles se calcula una vez
    por tamaño de cuadro y se reutiliza: el costo por cuadro es una sola asignación."""

    def __init__(self, poligonos: Sequence[Poligono]) -> None:
        for poligono in poligonos:
            _validar_poligono(poligono)
        self._poligonos = [tuple(p) for p in poligonos]
        self._cache: dict[tuple[int, int], np.ndarray] = {}

    def __len__(self) -> int:
        return len(self._poligonos)

    def _mascara(self, alto: int, ancho: int) -> np.ndarray:
        clave = (alto, ancho)
        if clave not in self._cache:
            mascara = np.zeros((alto, ancho), dtype=np.uint8)
            puntos = [
                np.array([[round(x * ancho), round(y * alto)] for x, y in p], dtype=np.int32)
                for p in self._poligonos
            ]
            if puntos:
                cv2.fillPoly(mascara, puntos, 255)
            self._cache[clave] = mascara.astype(bool)
        return self._cache[clave]

    def aplicar(self, imagen: np.ndarray) -> np.ndarray:
        """Devuelve una copia con los polígonos en negro. La imagen original no se toca."""
        salida = imagen.copy()
        if self._poligonos:
            salida[self._mascara(imagen.shape[0], imagen.shape[1])] = 0
        return salida


def aplicar_mascaras(imagen: np.ndarray, poligonos: Sequence[Poligono]) -> np.ndarray:
    """Atajo sin caché, para un cuadro suelto."""
    return MascaraPrivacidad(poligonos).aplicar(imagen)


def _a_pixeles(caja: Caja, alto: int, ancho: int, margen: float) -> tuple[int, int, int, int]:
    mx, my = caja.ancho * margen, caja.alto * margen
    x1 = max(0, int(np.floor((caja.x1 - mx) * ancho)))
    y1 = max(0, int(np.floor((caja.y1 - my) * alto)))
    x2 = min(ancho, int(np.ceil((caja.x2 + mx) * ancho)))
    y2 = min(alto, int(np.ceil((caja.y2 + my) * alto)))
    return x1, y1, x2, y2


def difuminar_regiones(
    imagen: np.ndarray,
    cajas: Sequence[Caja],
    *,
    margen: float = 0.15,
    bloques: int = BLOQUES_POR_LADO,
) -> np.ndarray:
    """Pixela cada caja (más un margen) y devuelve una copia.

    Se pixela en vez de aplicar un desenfoque gaussiano porque el gaussiano es en parte
    reversible con deconvolución; promediar bloques destruye la información.
    """
    if bloques < 1:
        raise ValueError("bloques debe ser al menos 1")
    salida = imagen.copy()
    alto, ancho = imagen.shape[:2]
    for caja in cajas:
        x1, y1, x2, y2 = _a_pixeles(caja, alto, ancho, margen)
        if x2 <= x1 or y2 <= y1:
            continue
        region = salida[y1:y2, x1:x2]
        chica = cv2.resize(
            region,
            (min(bloques, x2 - x1), min(bloques, y2 - y1)),
            interpolation=cv2.INTER_AREA,
        )
        salida[y1:y2, x1:x2] = cv2.resize(
            chica, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST
        )
    return salida
