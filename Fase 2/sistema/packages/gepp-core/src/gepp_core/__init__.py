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
)
from gepp_core.geometria import Caja

__all__ = [
    "AgregadorDeHallazgos",
    "Caja",
    "ClaseDetectada",
    "Deteccion",
    "Hallazgo",
    "Regla",
    "Severidad",
    "TipoEPP",
    "agregar",
    "epp_faltante",
    "epp_puesto",
]
