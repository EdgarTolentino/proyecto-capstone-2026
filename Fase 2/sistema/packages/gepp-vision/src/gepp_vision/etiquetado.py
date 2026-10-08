"""Pre-etiquetas para CVAT (#27): el modelo propone, una persona corrige.

Corregir es más rápido que dibujar desde cero, pero una pre-etiqueta no es verdad: la
persona que etiqueta revisa cada caja, agrega lo que falta y fija los atributos (`puesto`,
`ocluida`), que el modelo no infiere. Las reglas de la caja son las de
`docs/datos/guia-etiquetado.md`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from gepp_core import Caja, Deteccion

from gepp_vision.entrenamiento import CLASES_V1

#: Guía de etiquetado §4: lo de menos de 10 px de lado no lleva caja, salvo lo que diga
#: `MINIMO_PX_POR_CLASE`.
MINIMO_PX = 10

#: Decisión de Edgar del 2026-10-08 (guía §7): el casco se etiqueta desde 8 px. Persona y chaleco
#: siguen en `MINIMO_PX`.
MINIMO_PX_POR_CLASE: dict[str, int] = {"casco": 8}


def minimo_px(clase: str) -> int:
    """Lado mínimo, en px de la imagen original, de la caja de una clase de la v1. Un solo lugar
    de verdad para `a_coco` y la revisión de etiquetas. Una clase fuera de la v1 es un error:
    devolver el general escondería un nombre mal escrito."""
    if clase not in CLASES_V1:
        raise ValueError(f"clase fuera de la v1: {clase!r}")
    return MINIMO_PX_POR_CLASE.get(clase, MINIMO_PX)


def combinar(
    del_mosaico: Sequence[Deteccion], del_cuadro: Sequence[Deteccion], recorte: Caja
) -> list[Deteccion]:
    """Lo del mosaico, que cubre el recorte, más lo del pase sobre el cuadro entero cuyo centro
    cae fuera del recorte (personas junto a la cámara). Puede quedar alguna caja repetida:
    en el lote de prueba hubo 71 pares, del propio mosaico y no de esta unión (la tolerancia
    de contención del #107 los reduce). Son sugerencias y se corrigen al revisar."""
    fuera = [d for d in del_cuadro if not recorte.contiene(d.caja.centro)]
    return [*del_mosaico, *fuera]


def a_coco(imagenes: Iterable[tuple[str, int, int, Sequence[Deteccion]]]) -> dict[str, Any]:
    """COCO 1.0 para importar en CVAT. Cada tupla: (archivo, ancho, alto, detecciones)."""
    salida: dict[str, Any] = {
        "categories": [
            {"id": i, "name": str(c), "supercategory": ""} for c, i in CLASES_V1.items()
        ],
        "images": [],
        "annotations": [],
    }
    for img_id, (archivo, ancho, alto, detecciones) in enumerate(imagenes, start=1):
        salida["images"].append(
            {"id": img_id, "file_name": archivo, "width": ancho, "height": alto}
        )
        for d in detecciones:
            w, h = d.caja.ancho * ancho, d.caja.alto * alto
            if d.clase not in CLASES_V1 or min(w, h) < minimo_px(d.clase):
                continue
            salida["annotations"].append(
                {
                    "id": len(salida["annotations"]) + 1,
                    "image_id": img_id,
                    "category_id": CLASES_V1[d.clase],
                    "bbox": [d.caja.x1 * ancho, d.caja.y1 * alto, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                    "score": d.confianza,
                }
            )
    return salida
