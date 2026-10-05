"""Evaluación del modelo (#31). Especificación: `docs/arquitectura/04-evaluar-niveles-0-1.md`."""

from gepp_vision.evaluacion.coco import (
    CLASES,
    ArchivoCoco,
    CajaPx,
    EntradaInvalida,
    Recorte,
    en_region,
    imagenes_comunes,
    leer_coco,
)

__all__ = [
    "CLASES",
    "ArchivoCoco",
    "CajaPx",
    "EntradaInvalida",
    "Recorte",
    "en_region",
    "imagenes_comunes",
    "leer_coco",
]
