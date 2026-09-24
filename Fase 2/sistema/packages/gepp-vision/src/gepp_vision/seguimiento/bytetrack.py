"""ByteTrack, implementación propia (PT-08).

El algoritmo es el de Zhang et al., *ByteTrack: Multi-Object Tracking by Associating Every
Detection Box* (ECCV 2022): la idea es no botar las detecciones de confianza baja, porque
suelen ser la misma persona parcialmente tapada. Se asocia en dos pasadas:

1. las detecciones de confianza **alta** contra todos los tracks vivos, usando la posición
   que **predice** un filtro de Kalman (no la última vista);
2. las de confianza **baja** contra los tracks que quedaron sin pareja. Estas mantienen viva
   una identidad, pero nunca crean una nueva.

Por qué propia y no `roboflow/trackers`: esa biblioteca exige `opencv-python`, que choca con
el `opencv-python-headless` del proyecto (los dos instalan el módulo `cv2`), y arrastra
`matplotlib`, `supervision`, `rich`, `requests` y `av`. Decisión de Edgar, 24-sep-2026.

Adaptaciones a 5 fps (`00-arquitectura.md` §5.4), las mismas que `SeguidorIoU`:

- **El tiempo se mide en segundos**, con `capture_ts`: el filtro de Kalman avanza `dt`
  segundos reales y el `track_buffer` está en segundos. El mismo valor significa lo mismo a
  cualquier cadencia (ADR-005).
- **IoU de emparejamiento bajo** (0,15): a 5 fps una persona se desplaza mucho entre cuadros.
- **Sin compensación de movimiento de cámara:** las cámaras son fijas.
- **Un track nace confirmado.** El original espera un segundo cuadro; a 5 fps eso es
  0,2 s de retraso, y el agregador ya exige duración mínima antes de abrir un hallazgo.
- **Solo se siguen personas.** Los EPP salen con `track_id=None` y el agregador los asocia
  por geometría (`gepp_core.asociacion`).

Los identificadores son efímeros: empiezan en 1 y se reinician con cada video (ADR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

import numpy as np
from gepp_core import Caja, ClaseDetectada, Deteccion
from scipy.optimize import linear_sum_assignment

IOU_MINIMO = 0.15
IOU_MINIMO_BAJA = 0.5
UMBRAL_ALTO = 0.5
UMBRAL_BAJO = 0.1
UMBRAL_NUEVO = 0.6
TRACK_BUFFER_SEGUNDOS = 1.5

# Ruido del filtro, proporcional al alto de la caja como en el original. Por segundo, no
# por cuadro: los del original (1/20 y 1/160 por cuadro a 30 fps) llevados a segundos.
_RUIDO_POSICION = 1 / 20
_RUIDO_VELOCIDAD = 30 / 160


class _Kalman:
    """Velocidad constante sobre (cx, cy, ancho, alto). Estado de 8: posición y velocidad."""

    def __init__(self, caja: Caja) -> None:
        self.x = np.array([*_centro(caja), 0.0, 0.0, 0.0, 0.0])
        h = caja.alto
        std = [2 * _RUIDO_POSICION * h] * 4 + [10 * _RUIDO_VELOCIDAD * h] * 4
        self.p = np.diag(np.square(std))

    def predecir(self, dt: float) -> None:
        if dt <= 0:
            return
        f = np.eye(8)
        f[:4, 4:] = dt * np.eye(4)
        h = max(self.x[3], 1e-3)
        q = np.diag(np.square([_RUIDO_POSICION * h] * 4 + [_RUIDO_VELOCIDAD * h] * 4) * dt)
        self.x = f @ self.x
        self.p = f @ self.p @ f.T + q

    def corregir(self, caja: Caja) -> None:
        h_obs = np.hstack([np.eye(4), np.zeros((4, 4))])
        r = np.diag(np.square([_RUIDO_POSICION * caja.alto] * 4))
        s = h_obs @ self.p @ h_obs.T + r
        k = self.p @ h_obs.T @ np.linalg.inv(s)
        self.x = self.x + k @ (np.array(_centro(caja)) - h_obs @ self.x)
        self.p = (np.eye(8) - k @ h_obs) @ self.p

    def caja(self) -> Caja | None:
        cx, cy, w, h = self.x[:4]
        if w <= 0 or h <= 0:
            return None
        x1, y1 = max(cx - w / 2, 0.0), max(cy - h / 2, 0.0)
        x2, y2 = min(cx + w / 2, 1.0), min(cy + h / 2, 1.0)
        return Caja(x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def _centro(caja: Caja) -> tuple[float, float, float, float]:
    return ((caja.x1 + caja.x2) / 2, (caja.y1 + caja.y2) / 2, caja.ancho, caja.alto)


@dataclass(slots=True)
class _Track:
    id: int
    kalman: _Kalman
    visto_en: datetime
    predicho_en: datetime


class SeguidorByteTrack:
    """Cumple el protocolo `Seguidor`."""

    def __init__(
        self,
        *,
        iou_minimo: float = IOU_MINIMO,
        iou_minimo_baja: float = IOU_MINIMO_BAJA,
        umbral_alto: float = UMBRAL_ALTO,
        umbral_bajo: float = UMBRAL_BAJO,
        umbral_nuevo: float = UMBRAL_NUEVO,
        track_buffer_segundos: float = TRACK_BUFFER_SEGUNDOS,
    ) -> None:
        if not (0 < iou_minimo < 1 and 0 < iou_minimo_baja < 1):
            raise ValueError("los umbrales de IoU deben estar entre 0 y 1")
        if not 0 <= umbral_bajo < umbral_alto <= 1:
            raise ValueError("debe cumplirse 0 <= umbral_bajo < umbral_alto <= 1")
        if track_buffer_segundos < 0:
            raise ValueError("track_buffer_segundos no puede ser negativo")
        self._iou_minimo = iou_minimo
        self._iou_minimo_baja = iou_minimo_baja
        self._umbral_alto = umbral_alto
        self._umbral_bajo = umbral_bajo
        self._umbral_nuevo = umbral_nuevo
        self._buffer = track_buffer_segundos
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
        for t in self._tracks:
            t.kalman.predecir((ahora - t.predicho_en).total_seconds())
            t.predicho_en = ahora

        personas = [
            i
            for i, d in enumerate(detecciones)
            if d.clase is ClaseDetectada.PERSONA and d.confianza >= self._umbral_bajo
        ]
        altas = [i for i in personas if detecciones[i].confianza >= self._umbral_alto]
        bajas = [i for i in personas if detecciones[i].confianza < self._umbral_alto]

        asignado: dict[int, _Track] = {}
        libres = list(self._tracks)
        for grupo, umbral in ((altas, self._iou_minimo), (bajas, self._iou_minimo_baja)):
            pares = self._emparejar([detecciones[i] for i in grupo], libres, umbral)
            for fila, columna in pares:
                asignado[grupo[fila]] = libres[columna]
            usados = {columna for _, columna in pares}
            libres = [t for k, t in enumerate(libres) if k not in usados]

        salida = [replace(d, track_id=None) for d in detecciones]
        for i, track in asignado.items():
            track.kalman.corregir(detecciones[i].caja)
            track.visto_en = ahora
            salida[i] = replace(detecciones[i], track_id=track.id)
        for i in altas:
            if i not in asignado and detecciones[i].confianza >= self._umbral_nuevo:
                track = _Track(self._siguiente, _Kalman(detecciones[i].caja), ahora, ahora)
                self._siguiente += 1
                self._tracks.append(track)
                salida[i] = replace(detecciones[i], track_id=track.id)
        return salida

    @staticmethod
    def _emparejar(
        dets: list[Deteccion], tracks: list[_Track], iou_minimo: float
    ) -> list[tuple[int, int]]:
        """Asignación óptima (húngaro) sobre 1 - IoU, descartando pares bajo el umbral."""
        if not dets or not tracks:
            return []
        predichas = [t.kalman.caja() for t in tracks]
        iou = np.array([[d.caja.iou(p) if p is not None else 0.0 for p in predichas] for d in dets])
        filas, columnas = linear_sum_assignment(1.0 - iou)
        return [
            (int(f), int(c))
            for f, c in zip(filas, columnas, strict=True)
            if iou[f, c] >= iou_minimo
        ]
