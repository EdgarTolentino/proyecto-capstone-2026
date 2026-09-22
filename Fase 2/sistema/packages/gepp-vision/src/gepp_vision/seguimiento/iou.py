"""Seguidor por IoU, codicioso. Provisional hasta el adaptador de ByteTrack.

Por qué no ByteTrack todavía: `trackers` (roboflow, Apache-2.0) exige `opencv-python`, que
choca con el `opencv-python-headless` del proyecto (los dos instalan el módulo `cv2`), y
arrastra `supervision`, `rich` y `requests`. Resolverlo es parte de PT-08, cuando haya
detecciones reales con las que medir si ByteTrack fragmenta menos. Este seguidor cumple el
mismo protocolo, así que el cambio no toca nada aguas abajo.

Tres decisiones heredadas de `00-arquitectura.md` para 5 fps:

- **Umbral de IoU bajo (0,15 por defecto):** a 5 fps una persona que camina se desplaza
  bastante entre cuadros; con 0,5 el track se parte en cada paso.
- **`track_buffer` en SEGUNDOS**, medido con `capture_ts`: el mismo valor significa lo
  mismo a cualquier cadencia (ADR-005).
- **Solo se siguen personas.** Los EPP salen con `track_id=None` y el agregador los asocia
  a la persona por geometría (`gepp_core.asociacion`).

Los identificadores son efímeros: empiezan en 1 y se reinician con cada video (ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from gepp_core import Caja, ClaseDetectada, Deteccion

IOU_MINIMO = 0.15
TRACK_BUFFER_SEGUNDOS = 1.5


@dataclass(slots=True)
class _Track:
    id: int
    caja: Caja
    visto_en: datetime


class SeguidorIoU:
    def __init__(
        self,
        *,
        iou_minimo: float = IOU_MINIMO,
        track_buffer_segundos: float = TRACK_BUFFER_SEGUNDOS,
        confianza_minima: float = 0.25,
    ) -> None:
        if not 0 < iou_minimo < 1:
            raise ValueError("iou_minimo debe estar entre 0 y 1")
        if track_buffer_segundos < 0:
            raise ValueError("track_buffer_segundos no puede ser negativo")
        self._iou_minimo = iou_minimo
        self._buffer = track_buffer_segundos
        self._confianza_minima = confianza_minima
        self._tracks: list[_Track] = []
        self._siguiente = 1

    def reiniciar(self) -> None:
        self._tracks.clear()
        self._siguiente = 1

    def actualizar(self, detecciones: list[Deteccion]) -> list[Deteccion]:
        if not detecciones:
            return []
        ahora = detecciones[0].capture_ts
        self._tracks = [
            t for t in self._tracks if (ahora - t.visto_en).total_seconds() <= self._buffer
        ]

        personas = [
            (i, d)
            for i, d in enumerate(detecciones)
            if d.clase is ClaseDetectada.PERSONA and d.confianza >= self._confianza_minima
        ]
        # Pares candidatos de mayor a menor IoU: asignación codiciosa.
        pares = sorted(
            ((d.caja.iou(t.caja), i, k) for i, d in personas for k, t in enumerate(self._tracks)),
            reverse=True,
        )
        asignado: dict[int, int] = {}
        usados: set[int] = set()
        for iou, i, k in pares:
            if iou < self._iou_minimo:
                break
            if i in asignado or k in usados:
                continue
            asignado[i] = k
            usados.add(k)

        salida = list(detecciones)
        for i, d in personas:
            if i in asignado:
                track = self._tracks[asignado[i]]
                track.caja, track.visto_en = d.caja, d.capture_ts
            else:
                track = _Track(self._siguiente, d.caja, d.capture_ts)
                self._siguiente += 1
                self._tracks.append(track)
            salida[i] = replace(d, track_id=track.id)
        # Todo lo que no es persona sale sin identidad, venga como venga.
        return [
            d if d.clase is ClaseDetectada.PERSONA else replace(d, track_id=None) for d in salida
        ]
