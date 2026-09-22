"""Detector guionizado: devuelve lo que dice un JSON, sin mirar la imagen.

Sirve para probar todo lo que está aguas abajo del modelo —seguidor, agregador, ingesta,
persistencia, API— sin GPU y sin pesos. Es el detector de CI y el de la H2 si el modelo de
la S8 no llega a tiempo (`09-plan-de-desarrollo-vision.md`, §6).

El guion se escribe en SEGUNDOS desde el primer cuadro, no en índices de cuadro: así el
mismo guion describe la misma escena a 24, 25 o 30 fps de origen, que es justo lo que
necesita la prueba de invariancia a la cadencia (ADR-005).

Formato (ejemplo en `tests/fixtures/guion_sin_casco.json`):

    {
      "version": "falso-1",
      "segmentos": [
        {"desde_s": 0.0, "hasta_s": 3.0, "detecciones": [
          {"clase": "persona", "caja": [0.40, 0.20, 0.52, 0.80], "confianza": 0.9}
        ]}
      ]
    }

Un segmento vale en `[desde_s, hasta_s)`. Si dos se solapan, se suman sus detecciones.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from gepp_core import Caja, ClaseDetectada, Deteccion


@dataclass(frozen=True, slots=True)
class DeteccionGuionada:
    clase: ClaseDetectada
    caja: Caja
    confianza: float


@dataclass(frozen=True, slots=True)
class Segmento:
    desde_s: float
    hasta_s: float
    detecciones: tuple[DeteccionGuionada, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.desde_s < self.hasta_s:
            raise ValueError(f"segmento inválido: {self.desde_s}-{self.hasta_s} s")

    def cubre(self, t: float) -> bool:
        return self.desde_s <= t < self.hasta_s


@dataclass(frozen=True, slots=True)
class Guion:
    version: str
    segmentos: tuple[Segmento, ...]

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> Guion:
        segmentos = []
        for s in datos["segmentos"]:
            dets = tuple(
                DeteccionGuionada(
                    clase=ClaseDetectada(d["clase"]),
                    caja=Caja(*d["caja"]),
                    confianza=float(d["confianza"]),
                )
                for d in s["detecciones"]
            )
            segmentos.append(Segmento(float(s["desde_s"]), float(s["hasta_s"]), dets))
        return cls(version=str(datos.get("version", "falso")), segmentos=tuple(segmentos))

    @classmethod
    def desde_json(cls, ruta: Path) -> Guion:
        return cls.desde_dict(json.loads(ruta.read_text(encoding="utf-8")))


class DetectorFalso:
    """Cumple el protocolo `Detector`. El origen del tiempo es el primer cuadro que ve.

    Para reutilizarlo en otro video, `reiniciar()`.
    """

    def __init__(self, guion: Guion | Sequence[Segmento]) -> None:
        self._guion = guion if isinstance(guion, Guion) else Guion("falso", tuple(guion))
        self._origen: datetime | None = None

    @property
    def version(self) -> str:
        return f"falso:{self._guion.version}"

    def reiniciar(self) -> None:
        self._origen = None

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        del imagen  # el guion no mira la imagen: es el punto
        if self._origen is None:
            self._origen = capture_ts
        t = (capture_ts - self._origen).total_seconds()
        return [
            Deteccion(
                capture_ts=capture_ts,
                cuadro_idx=cuadro_idx,
                clase=d.clase,
                caja=d.caja,
                confianza=d.confianza,
            )
            for s in self._guion.segmentos
            if s.cubre(t)
            for d in s.detecciones
        ]
