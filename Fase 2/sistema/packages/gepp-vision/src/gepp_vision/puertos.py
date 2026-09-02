"""Puertos de visión: el detector y el seguidor son intercambiables.

Que sean protocolos y no clases concretas es lo que permite (a) cambiar RF-DETR por
D-FINE sin tocar el resto, (b) tener un backend PyTorch en la máquina con GPU y uno
ONNX en las que no la tienen, y (c) usar un detector falso en las pruebas.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from gepp_core import Deteccion


@runtime_checkable
class Detector(Protocol):
    """Cualquier cosa que mire una imagen y devuelva detecciones."""

    def detectar(self, imagen: np.ndarray) -> list[Deteccion]: ...

    @property
    def version(self) -> str:
        """Identificador del modelo. Se persiste con cada detección, para auditar."""
        ...


@runtime_checkable
class Seguidor(Protocol):
    """Asigna identidad temporal a las detecciones entre cuadros.

    Los identificadores son EFÍMEROS: viven dentro de un video y se destruyen al
    cerrarlo. No se cruzan entre fuentes ni entre días (ADR-006).
    """

    def actualizar(self, detecciones: list[Deteccion]) -> list[Deteccion]: ...
    def reiniciar(self) -> None: ...


@runtime_checkable
class Descriptor(Protocol):
    """El modelo de lenguaje visual de la Etapa 2.

    Describe hallazgos ya confirmados. No crea, no suprime y no cambia la severidad
    de ningún hallazgo (ADR-001).
    """

    def describir(self, recortes: list[np.ndarray], contexto: str) -> dict[str, object]: ...
