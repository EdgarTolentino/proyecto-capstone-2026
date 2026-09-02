"""Guardián EPP — ingesta.

Es el único paquete que cambia entre la v1 (carpeta vigilada) y la v2 (RTSP).
"""

from gepp_worker.fuente import (
    Cuadro,
    FuenteDeCuadros,
    PoliticaBuffer,
    PropiedadesFuente,
    instante_de_captura,
)

__all__ = [
    "Cuadro",
    "FuenteDeCuadros",
    "PoliticaBuffer",
    "PropiedadesFuente",
    "instante_de_captura",
]
