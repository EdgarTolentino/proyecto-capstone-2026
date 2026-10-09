"""Avance del análisis de un video, publicado en su fila mientras se procesa.

Es telemetría del procesamiento, no dato del video (ADR-005): el ritmo se mide con el reloj
monotónico que se inyecta y `avance_actualizado` lo pone la base; nada de esto fecha una detección
ni un hallazgo.

- **Unidad:** segundos DE VIDEO de origen por posición de captura (`capture_ts - inicio`), no
  cuadros contados. Con un video de 25 fps muestreado a 5, contar cuadros daría 20 % al terminar.
- **Frecuencia:** como mucho una publicación cada `cada_s` (2 s por defecto), más la primera y la
  final.
- **Transacciones:** cada publicación va en una propia y corta, nunca dentro de la del resultado
  (que toma la misma fila). La final (`guardando`, avance = total) se hace ANTES de abrir la del
  resultado, no después del UPDATE de estado: si no, las dos se bloquearían entre sí.
- **Fallas:** si publicar falla, se dice por stderr y el análisis sigue. El avance nunca detiene
  el procesamiento.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterable

from gepp_bd.repositorios import videos
from gepp_bd.sesion import transaccion
from gepp_core import ClaseDetectada, Deteccion
from sqlalchemy import Engine
from sqlalchemy.orm import Session

PERIODO_S = 2.0
CLASES_DEL_AVANCE = (ClaseDetectada.PERSONA, ClaseDetectada.CASCO, ClaseDetectada.CHALECO)


def contar(detecciones: Iterable[Deteccion]) -> dict[str, int]:
    """Las detecciones de UN cuadro por clase. Es lo que hay en ese cuadro, no un acumulado."""
    cuenta = dict.fromkeys((str(c) for c in CLASES_DEL_AVANCE), 0)
    for d in detecciones:
        if str(d.clase) in cuenta:
            cuenta[str(d.clase)] += 1
    return cuenta


class PublicadorDeAvance:
    def __init__(
        self,
        motor: Engine,
        video_id: int,
        duracion_s: float | None,
        *,
        reloj: Callable[[], float] = time.monotonic,
        cada_s: float = PERIODO_S,
    ) -> None:
        self._motor = motor
        self._video_id = video_id
        # Un video de duración desconocida o 0 no tiene total: no hay porcentaje que mostrar.
        self._total = duracion_s if duracion_s is not None and duracion_s > 0 else None
        self._reloj = reloj
        self._cada = cada_s
        self._inicio = reloj()
        self._ultima_publicacion: float | None = None
        self._posicion_s = 0.0
        self._ultimo = contar(())

    def cuadro(self, posicion_s: float, detecciones: Iterable[Deteccion]) -> None:
        """Un cuadro analizado, en la posición `posicion_s` del video. Publica si toca."""
        self._posicion_s = self._acotar(posicion_s)
        self._ultimo = contar(detecciones)
        ahora = self._reloj()
        if self._ultima_publicacion is None or ahora - self._ultima_publicacion >= self._cada:
            self._publicar("analizando", self._posicion_s, ahora)

    def final(self) -> None:
        """Lo último antes de guardar: `guardando` con el avance en el total (o, sin total, en
        la última posición vista). Siempre publica, aunque el video dure menos que `cada_s`."""
        llegado = self._total if self._total is not None else self._posicion_s
        self._publicar("guardando", llegado, self._reloj())

    def _acotar(self, posicion_s: float) -> float:
        posicion_s = max(posicion_s, 0.0)
        return min(posicion_s, self._total) if self._total is not None else posicion_s

    def _publicar(self, fase: str, avance_s: float, ahora: float) -> None:
        transcurrido = ahora - self._inicio
        velocidad = avance_s / transcurrido if transcurrido > 0 else None
        self._ultima_publicacion = ahora
        self._intentar(
            lambda s: videos.publicar_avance(
                s,
                self._video_id,
                fase=fase,
                avance_s=avance_s,
                total_s=self._total,
                velocidad=velocidad,
                ultimo=self._ultimo,
            )
        )

    def _intentar(self, accion: Callable[[Session], None]) -> None:
        try:
            with transaccion(self._motor) as s:
                accion(s)
        except Exception as e:
            print(f"[trabajador] no se pudo publicar el avance: {e!r}", file=sys.stderr)
