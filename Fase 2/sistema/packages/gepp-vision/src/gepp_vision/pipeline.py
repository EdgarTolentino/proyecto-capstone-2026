"""Etapa 1 completa, sin E/S: cuadro → máscara → detector → seguidor → agregador.

Recibe cuadros ya fechados y devuelve objetos; no abre archivos, no toca la base, no lee
el reloj. Por eso se prueba con un guion JSON y un video sintético (ADR-009).

`gepp-vision` no depende de `gepp-worker`, así que el cuadro de entrada es un protocolo
mínimo: cualquier objeto con `indice`, `capture_ts` e `imagen` sirve, incluido
`gepp_worker.fuente.Cuadro`.

Los umbrales de la regla están en segundos y el agregador los mide con `capture_ts`: el
pipeline no convierte nada a cuadros, y por eso da el mismo hallazgo a cualquier cadencia.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import numpy as np
from gepp_core import AgregadorDeHallazgos, Deteccion, Hallazgo, Regla

from gepp_vision.privacidad import MascaraPrivacidad
from gepp_vision.puertos import Detector, Seguidor


class CuadroFechado(Protocol):
    @property
    def indice(self) -> int: ...
    @property
    def capture_ts(self) -> datetime: ...
    @property
    def imagen(self) -> np.ndarray: ...


@dataclass(slots=True)
class ResultadoCuadro:
    """Lo que produce un cuadro: sus detecciones con identidad y los hallazgos que cerró."""

    detecciones: list[Deteccion]
    hallazgos: list[Hallazgo]


@dataclass(slots=True)
class ResultadoVideo:
    detecciones: list[Deteccion] = field(default_factory=list)
    hallazgos: list[Hallazgo] = field(default_factory=list)
    cuadros: int = 0


class PipelineEtapa1:
    """Una instancia por video: el seguidor y el agregador guardan estado del video."""

    def __init__(
        self,
        detector: Detector,
        seguidor: Seguidor,
        reglas: Sequence[Regla],
        mascara: MascaraPrivacidad | None = None,
    ) -> None:
        if not reglas:
            raise ValueError("el pipeline necesita al menos una regla")
        self._detector = detector
        self._seguidor = seguidor
        self._mascara = mascara
        self._agregadores = [AgregadorDeHallazgos(r) for r in reglas]

    @property
    def version_modelo(self) -> str:
        return self._detector.version

    def procesar(self, cuadro: CuadroFechado) -> ResultadoCuadro:
        imagen = cuadro.imagen
        if self._mascara is not None and len(self._mascara):
            imagen = self._mascara.aplicar(imagen)  # ANTES de inferir (ADR-006)
        crudas = self._detector.detectar(
            imagen, cuadro_idx=cuadro.indice, capture_ts=cuadro.capture_ts
        )
        seguidas = self._seguidor.actualizar(crudas)
        hallazgos = [h for a in self._agregadores for h in a.procesar_cuadro(seguidas)]
        return ResultadoCuadro(seguidas, hallazgos)

    def cerrar(self) -> list[Hallazgo]:
        """Cierra lo pendiente al terminar la fuente y deja el seguidor limpio."""
        hallazgos = [h for a in self._agregadores for h in a.cerrar()]
        self._seguidor.reiniciar()
        return hallazgos

    def procesar_todo(self, cuadros: Iterable[CuadroFechado]) -> ResultadoVideo:
        resultado = ResultadoVideo()
        for cuadro in cuadros:
            r = self.procesar(cuadro)
            resultado.detecciones.extend(r.detecciones)
            resultado.hallazgos.extend(r.hallazgos)
            resultado.cuadros += 1
        resultado.hallazgos.extend(self.cerrar())
        return resultado
