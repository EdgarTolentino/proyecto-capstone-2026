"""Deduplicación perceptual y partición del dataset (`02-plan-de-evaluacion.md`).

A 5 fps dos cuadros vecinos son casi copias. Si uno cae en entrenamiento y el otro en
prueba, la métrica sale optimista y falsa. Dos reglas duras viven aquí:

1. **La unidad de partición es el video**, nunca el cuadro.
2. **Un mismo hash perceptual no puede aparecer en dos particiones.** `verificar_particion`
   lo comprueba y CI la corre sobre el manifiesto versionado.

El hash es un dHash de 64 bits: compara el brillo de píxeles vecinos en una miniatura de
9 x 8. No se puede reconstruir la imagen desde él, así que el manifiesto puede vivir en un
repositorio público aunque las imágenes no.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import cv2
import numpy as np

#: Distancia de Hamming bajo la cual dos imágenes se consideran la misma escena.
#: 6 de 64 bits: absorbe ruido de compresión y pequeños movimientos, no un cambio de escena.
UMBRAL_DUPLICADO = 6


class Particion(StrEnum):
    ENTRENAMIENTO = "entrenamiento"
    VALIDACION = "validacion"
    PRUEBA = "prueba"


def dhash(imagen: np.ndarray) -> int:
    """Hash perceptual de 64 bits de una imagen BGR o en grises."""
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY) if imagen.ndim == 3 else imagen
    mini = cv2.resize(gris, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (mini[:, 1:] > mini[:, :-1]).flatten()
    return int(sum(1 << i for i, b in enumerate(bits) if b))


def distancia(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def deduplicar(hashes: Sequence[int], umbral: int = UMBRAL_DUPLICADO) -> list[int]:
    """Índices de las imágenes que se conservan, en orden.

    Voraz: una imagen se descarta si se parece a alguna ya conservada. Cuadrático, pero el
    lote 0 son cientos de imágenes, no millones.
    """
    conservados: list[int] = []
    for i, h in enumerate(hashes):
        if all(distancia(h, hashes[j]) > umbral for j in conservados):
            conservados.append(i)
    return conservados


@dataclass(frozen=True, slots=True)
class Imagen:
    """Una fila del manifiesto: qué imagen, de qué video, en qué partición."""

    archivo: str
    video: str
    particion: Particion
    hash: int


class ParticionInvalida(ValueError):
    pass


def verificar_particion(imagenes: Iterable[Imagen], umbral: int = UMBRAL_DUPLICADO) -> None:
    """Falla si un video aparece en dos particiones o si dos particiones comparten escena.

    La segunda comprobación usa la misma distancia que la deduplicación: no basta con que
    el hash sea distinto, tiene que estar lejos.
    """
    lista = list(imagenes)
    particion_de_video: dict[str, Particion] = {}
    for img in lista:
        previa = particion_de_video.setdefault(img.video, img.particion)
        if previa != img.particion:
            raise ParticionInvalida(
                f"el video {img.video!r} está en {previa} y en {img.particion}: "
                "la unidad de partición es el video"
            )
    for i, a in enumerate(lista):
        for b in lista[i + 1 :]:
            if a.particion != b.particion and distancia(a.hash, b.hash) <= umbral:
                raise ParticionInvalida(
                    f"{a.archivo} ({a.particion}) y {b.archivo} ({b.particion}) son la misma "
                    f"escena (distancia {distancia(a.hash, b.hash)} ≤ {umbral})"
                )
