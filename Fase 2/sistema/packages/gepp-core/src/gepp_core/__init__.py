"""Guardián EPP — dominio.

Python puro: sin torch, sin cv2, sin framework web. Ver ADR-007.
"""

from gepp_core.agregador import AgregadorDeHallazgos, agregar
from gepp_core.asociacion import epp_faltante, epp_puesto
from gepp_core.dominio import (
    ClaseDetectada,
    Deteccion,
    Hallazgo,
    Regla,
    Severidad,
    TipoEPP,
    Ventana,
)
from gepp_core.geometria import Caja, Poligono, fraccion_en_poligono, punto_en_poligono

__all__ = [
    "AgregadorDeHallazgos",
    "Caja",
    "ClaseDetectada",
    "Deteccion",
    "Hallazgo",
    "Poligono",
    "Regla",
    "Severidad",
    "TipoEPP",
    "Ventana",
    "agregar",
    "epp_faltante",
    "epp_puesto",
    "fraccion_en_poligono",
    "punto_en_poligono",
]
