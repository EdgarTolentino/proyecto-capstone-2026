"""Nivel 0 del plan de evaluación (#31): ¿coinciden los dos etiquetadores?

Kappa de Cohen sobre las clases de las cajas emparejadas e IoU medio de los pares, en los
cuadros del doble etiquetado. Python puro, sin pycocotools. Especificación:
`docs/arquitectura/04-evaluar-niveles-0-1.md`, §Nivel 0.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from gepp_vision.entrenamiento import _asignar
from gepp_vision.evaluacion.coco import ArchivoCoco, EntradaInvalida

#: Dos cajas son la misma si su IoU llega a esto, sin mirar la clase. Es el mismo valor que
#: `deteccion.UMBRAL_IOU`; no se importa de ahí porque `deteccion` arrastra pycocotools.
UMBRAL_IOU = 0.5
#: Guía de etiquetado §6: bajo esto se para, se discuten las diferencias y se anotan en la §7.
KAPPA_MINIMO = 0.7
#: La categoría de la caja que marcó solo uno de los dos.
SIN_CAJA = "sin caja"


@dataclass(frozen=True, slots=True)
class Acuerdo:
    imagenes: tuple[str, ...]
    kappa: float | None  # None: indefinido (sin pares, o una sola categoría en las dos)
    iou_medio: float | None  # None: ninguna caja emparejada
    pares: int  # cajas emparejadas por IoU, con la misma o distinta clase
    solo_primera: int
    solo_segunda: int
    matriz: dict[str, dict[str, int]]  # clase en la primera -> clase en la segunda -> cuenta


def imagenes_de_la_segunda(primera: ArchivoCoco, segunda: ArchivoCoco) -> list[str]:
    """Las imágenes que se comparan: las de la segunda exportación, en orden. La primera puede
    traer más, porque CVAT exporta la tarea entera; cada imagen de la segunda tiene que estar en
    la primera, con el mismo tamaño."""
    nombres = sorted(segunda.imagenes)
    if not nombres:
        raise EntradaInvalida("la segunda exportación no trae imágenes")
    for nombre in nombres:
        if nombre not in primera.imagenes:
            raise EntradaInvalida(f"{nombre} no está en la primera exportación")
        if primera.imagenes[nombre] != segunda.imagenes[nombre]:
            raise EntradaInvalida(
                f"{nombre}: tamaño distinto en la primera {primera.imagenes[nombre]} "
                f"y en la segunda {segunda.imagenes[nombre]}"
            )
    return nombres


def emparejar_clases(
    primera: ArchivoCoco, segunda: ArchivoCoco, imagenes: Sequence[str]
) -> list[tuple[str, str, float | None]]:
    """(clase en la primera, clase en la segunda, IoU) por caja. Las cajas de cada imagen se
    emparejan por IoU sin mirar la clase; la que se queda sin pareja va contra `SIN_CAJA`, con
    IoU None, para que una omisión baje el acuerdo en vez de desaparecer de la cuenta."""
    resultado: list[tuple[str, str, float | None]] = []
    for nombre in imagenes:
        a = [c for c in primera.cajas if c.archivo == nombre]
        b = [c for c in segunda.cajas if c.archivo == nombre]
        iou = np.array([[x.iou(y) for y in b] for x in a])
        pares = _asignar(iou, UMBRAL_IOU)
        resultado += [(a[f].clase, b[c].clase, float(iou[f, c])) for f, c in pares]
        con_pareja_a = {f for f, _ in pares}
        con_pareja_b = {c for _, c in pares}
        resultado += [(x.clase, SIN_CAJA, None) for i, x in enumerate(a) if i not in con_pareja_a]
        resultado += [(SIN_CAJA, y.clase, None) for j, y in enumerate(b) if j not in con_pareja_b]
    return resultado


def kappa_cohen(pares: Sequence[tuple[str, str]]) -> float | None:
    """(acuerdo observado - acuerdo por azar) / (1 - acuerdo por azar).

    None si no hay pares, o si el azar ya lo explica todo (las dos personas usaron una sola y
    la misma categoría): ahí el kappa no está definido.
    """
    n = len(pares)
    if n == 0:
        return None
    observado = sum(a == b for a, b in pares) / n
    primera = Counter(a for a, _ in pares)
    segunda = Counter(b for _, b in pares)
    azar = sum(primera[c] * segunda[c] for c in primera) / (n * n)
    if azar == 1:
        return None
    return (observado - azar) / (1 - azar)


def bajo_el_minimo(kappa: float | None) -> bool:
    """Si hay que parar y discutir (guía §6). Un kappa indefinido no dispara la alerta."""
    return kappa is not None and kappa < KAPPA_MINIMO


def acuerdo(primera: ArchivoCoco, segunda: ArchivoCoco) -> Acuerdo:
    """Nivel 0 completo sobre las imágenes de la segunda exportación."""
    imagenes = imagenes_de_la_segunda(primera, segunda)
    pares = emparejar_clases(primera, segunda, imagenes)
    ious = [iou for _, _, iou in pares if iou is not None]
    matriz: dict[str, dict[str, int]] = {}
    for a, b, _ in pares:
        fila = matriz.setdefault(a, {})
        fila[b] = fila.get(b, 0) + 1
    return Acuerdo(
        imagenes=tuple(imagenes),
        kappa=kappa_cohen([(a, b) for a, b, _ in pares]),
        iou_medio=sum(ious) / len(ious) if ious else None,
        pares=len(ious),
        solo_primera=sum(b == SIN_CAJA for _, b, _ in pares),
        solo_segunda=sum(a == SIN_CAJA for a, _, _ in pares),
        matriz=matriz,
    )
