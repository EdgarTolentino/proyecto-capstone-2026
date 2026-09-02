"""Entidades del dominio.

Este módulo es Python puro a propósito: sin torch, sin cv2, sin framework web.
Es lo que permite probar el corazón del sistema en CI, sin GPU y en segundos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum

from gepp_core.geometria import Caja


class Severidad(IntEnum):
    """Severidad del incumplimiento. Independiente de la confianza del modelo.

    Son dos ejes distintos y no se mezclan nunca: "sin arnés en altura" con
    confianza 0,62 sigue siendo crítico.
    """

    BAJA = 1
    MEDIA = 2
    ALTA = 3
    CRITICA = 4


class TipoEPP(StrEnum):
    CASCO = "casco"
    CHALECO = "chaleco"
    LENTES = "lentes"
    GUANTES = "guantes"
    ARNES = "arnes"
    CALZADO = "calzado"


class ClaseDetectada(StrEnum):
    PERSONA = "persona"
    CASCO = "casco"
    CHALECO = "chaleco"
    LENTES = "lentes"
    GUANTES = "guantes"
    ARNES = "arnes"
    CALZADO = "calzado"


#: Franja vertical de la persona donde se espera cada EPP, en fracción de su alto.
#: Se usa para asociar un EPP suelto a la persona correcta cuando hay varias en el cuadro.
FRANJA_ESPERADA: dict[TipoEPP, tuple[float, float]] = {
    TipoEPP.CASCO: (0.00, 0.30),
    TipoEPP.LENTES: (0.00, 0.25),
    TipoEPP.CHALECO: (0.15, 0.70),
    TipoEPP.ARNES: (0.15, 0.75),
    TipoEPP.GUANTES: (0.30, 0.85),
    TipoEPP.CALZADO: (0.80, 1.00),
}


@dataclass(frozen=True, slots=True)
class Deteccion:
    """Una detección cruda, tal como se persiste en la tabla `deteccion`."""

    capture_ts: datetime
    cuadro_idx: int
    clase: ClaseDetectada
    caja: Caja
    confianza: float
    track_id: int | None = None

    def __post_init__(self) -> None:
        if self.capture_ts.tzinfo is None:
            raise ValueError("capture_ts debe llevar zona horaria (ver ADR-005)")


@dataclass(frozen=True, slots=True)
class Regla:
    """Regla de EPP por área. Vive en la base de datos, versionada.

    Todos los umbrales están en SEGUNDOS, nunca en cuadros: al cambiar la cadencia
    de muestreo en v2, una regla expresada en cuadros cambiaría de significado en
    silencio (ADR-005).
    """

    id: int
    version: int
    nombre: str
    epp_exigido: frozenset[TipoEPP]
    severidad: Severidad
    confirmacion_segundos: float = 2.0
    cierre_segundos: float = 3.0
    confianza_minima: float = 0.45
    solape_zona_minimo: float = 0.50

    def cuadros_de_confirmacion(self, fps: float) -> int:
        """Convierte el umbral temporal a cuadros, en tiempo de ejecución."""
        if fps <= 0:
            raise ValueError("fps debe ser positivo")
        return max(1, math.ceil(self.confirmacion_segundos * fps))


@dataclass(frozen=True, slots=True)
class Hallazgo:
    """La unidad del sistema: una persona, un incumplimiento, un intervalo (ADR-004)."""

    track_id: int
    regla_id: int
    regla_version: int
    epp_faltante: frozenset[TipoEPP]
    severidad: Severidad
    ts_inicio: datetime
    ts_fin: datetime
    cuadros_confirmados: int
    confianza_media: float
    cuadros_evidencia: tuple[int, ...] = field(default_factory=tuple)

    @property
    def duracion_segundos(self) -> float:
        return (self.ts_fin - self.ts_inicio).total_seconds()
