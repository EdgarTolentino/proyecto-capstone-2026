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
from gepp_vision.evaluacion.deteccion import (
    MAX_DETS,
    TAMANOS,
    UMBRAL_IOU,
    UMBRAL_REGLA,
    MetricasClase,
    MetricasRegion,
    evaluar,
    evaluar_regiones,
)
from gepp_vision.evaluacion.reporte import ORIGENES, estado_git, reporte, sha256, tabla_markdown

__all__ = [
    "CLASES",
    "MAX_DETS",
    "ORIGENES",
    "TAMANOS",
    "UMBRAL_IOU",
    "UMBRAL_REGLA",
    "ArchivoCoco",
    "CajaPx",
    "EntradaInvalida",
    "MetricasClase",
    "MetricasRegion",
    "Recorte",
    "en_region",
    "estado_git",
    "evaluar",
    "evaluar_regiones",
    "imagenes_comunes",
    "leer_coco",
    "reporte",
    "sha256",
    "tabla_markdown",
]
