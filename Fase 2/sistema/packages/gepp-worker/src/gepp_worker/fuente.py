"""El puerto `FrameSource` (ADR-005).

La diferencia entre procesar un archivo (v1) y una cámara RTSP en vivo (v2) cabe en
tres decisiones, no en dos arquitecturas:

1. de dónde sale el timestamp del cuadro,
2. qué se hace cuando el consumidor no da abasto,
3. quién reinicia la fuente cuando deja de entregar cuadros.

Este módulo declara el contrato. `FileFrameSource` lo implementa en la v1;
`RtspFrameSource` se añade en la v2 sin tocar nada aguas abajo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

import numpy as np


class PoliticaBuffer(StrEnum):
    """Qué hacer cuando la cola de inferencia está llena."""

    ESPERAR = "esperar"  # archivo: nadie se pierde nada, el productor espera
    DESCARTAR_VIEJO = "descartar_viejo"  # vivo: mejor un cuadro fresco que uno atrasado


@dataclass(frozen=True, slots=True)
class PropiedadesFuente:
    es_archivo: bool
    fps: float
    ancho: int
    alto: int
    cuadros_totales: int | None
    #: Instante real de inicio de la captura, en UTC. Es el origen del reloj del sistema.
    inicio_captura: datetime
    #: De dónde salió `inicio_captura`. Se persiste para poder auditar la analítica temporal.
    origen_reloj: str
    reconectable: bool

    @property
    def politica_buffer(self) -> PoliticaBuffer:
        """El ÚNICO punto del código que distingue archivo de flujo en vivo."""
        return PoliticaBuffer.ESPERAR if self.es_archivo else PoliticaBuffer.DESCARTAR_VIEJO


@dataclass(frozen=True, slots=True)
class Cuadro:
    """Un cuadro con su instante de captura. Inmutable."""

    indice: int
    capture_ts: datetime
    imagen: np.ndarray

    def __post_init__(self) -> None:
        if self.capture_ts.tzinfo is None:
            raise ValueError("capture_ts debe llevar zona horaria (ver ADR-005)")


@runtime_checkable
class FuenteDeCuadros(Protocol):
    """Cinco métodos. Ni uno más."""

    def abrir(self) -> None: ...
    def tomar(self) -> bool:
        """Avanza al siguiente cuadro sin decodificarlo. Devuelve False al terminar."""
        ...

    def recuperar(self) -> Cuadro | None:
        """Decodifica y devuelve el cuadro tomado."""
        ...

    def cerrar(self) -> None: ...
    def propiedades(self) -> PropiedadesFuente: ...


def instante_de_captura(props: PropiedadesFuente, indice: int) -> datetime:
    """Deriva el instante real de un cuadro. NUNCA `datetime.now()`.

    En archivo: inicio de la grabación más el desplazamiento del cuadro.
    En vivo: el llamador pasa el reloj de recepción como `inicio_captura`.
    """
    if props.fps <= 0:
        raise ValueError("fps debe ser positivo para derivar el instante de captura")
    return props.inicio_captura + timedelta(seconds=indice / props.fps)
