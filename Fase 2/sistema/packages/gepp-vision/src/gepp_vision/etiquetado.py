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

#: Etiquetas de imagen (*tags*) de CVAT, guía §5. No son cajas: la exportación COCO 1.0 las trae
#: como categorías sin anotaciones. Un solo lugar para la revisión de etiquetas (que las valida) y
#: para `evaluacion.coco` (que las ignora): si CVAT gana una etiqueta, se agrega aquí.
ETIQUETAS_IMAGEN = frozenset({"tiene_pequenos", "negativo_duro", "grupo_denso"})

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


#: Holgura, en px, de la comparación con el mínimo. Pasar de coordenadas a lado resta dos flotantes
#: y un casco de 8 px exactos puede salir como 7,999999999999993. CVAT guarda 2 decimales, así que
#: 1e-6 px absorbe el error de redondeo sin dejar pasar ni un centésimo de píxel de más.
TOLERANCIA_PX = 1e-6


def bajo_minimo(ancho: float, alto: float, clase: str) -> bool:
    """¿La caja queda bajo el mínimo de su clase? Un solo criterio para `a_coco` y la revisión de
    etiquetas: estar justo en el mínimo (dentro de `TOLERANCIA_PX`) cuenta como llegar a él."""
    return min(ancho, alto) < minimo_px(clase) - TOLERANCIA_PX


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
            if d.clase not in CLASES_V1 or bajo_minimo(w, h, d.clase):
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
