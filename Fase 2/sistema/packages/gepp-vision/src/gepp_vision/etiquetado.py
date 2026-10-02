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

#: Guía de etiquetado §4: lo de menos de 10 px de lado no lleva caja.
MINIMO_PX = 10


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
            if min(w, h) < MINIMO_PX or d.clase not in CLASES_V1:
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
