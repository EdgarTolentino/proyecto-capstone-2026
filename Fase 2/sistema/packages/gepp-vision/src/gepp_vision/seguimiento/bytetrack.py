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
#: Umbrales alineados (decisión de Edgar, revisión del #76): la banda baja empieza donde corta
#: el detector (`rfdetr_comun.UMBRAL_CONFIANZA`, 0,25) y la alta —la que crea identidades—
#: en el mínimo por defecto de la regla (`gepp_core.Regla.confianza_minima`, 0,45). Así toda
#: persona que la regla cuenta recibe identidad, y las más débiles solo mantienen una viva.
#: `test_bytetrack_crea_identidades_desde_el_minimo_de_la_regla` los mantiene amarrados.
UMBRAL_ALTO = 0.45
UMBRAL_BAJO = 0.25
UMBRAL_NUEVO = 0.45
TRACK_BUFFER_SEGUNDOS = 1.5
#: Costo de un par bajo el umbral: el húngaro no lo elige mientras exista otro válido.
_PROHIBIDO = 1e6

# Ruido del filtro, proporcional al alto de la caja como en el original. Ajuste propio, no
# una conversión exacta: la desviación de posición es la del original y la de velocidad la
# lleva de "por cuadro a 30 fps" a "por segundo"; la varianza del proceso crece con `dt`.
# Resulta más confiado en su modelo que el original; calibrar con el video propio (#10).
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
        if not 0 <= umbral_bajo < umbral_alto <= umbral_nuevo <= 1:
            raise ValueError("debe cumplirse 0 <= umbral_bajo < umbral_alto <= umbral_nuevo <= 1")
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
        self._cuadro_anterior: datetime | None = None

    def reiniciar(self) -> None:
        self._tracks.clear()
        self._siguiente = 1
        self._cuadro_anterior = None

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
        # Primera pasada: las altas contra todos los tracks vivos, también los perdidos.
        pares = self._emparejar([detecciones[i] for i in altas], libres, self._iou_minimo)
        for fila, columna in pares:
            asignado[altas[fila]] = libres[columna]
        usados = {columna for _, columna in pares}
        # Segunda pasada: las bajas solo contra los que se vieron en el cuadro anterior, como
        # en el original: una detección débil no alcanza para revivir un track perdido.
        activos = [
            t
            for k, t in enumerate(libres)
            if k not in usados and t.visto_en == self._cuadro_anterior
        ]
        pares = self._emparejar([detecciones[i] for i in bajas], activos, self._iou_minimo_baja)
        for fila, columna in pares:
            asignado[bajas[fila]] = activos[columna]
        self._cuadro_anterior = ahora

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
        return SeguidorByteTrack._emparejar_por_iou(iou, iou_minimo)

    @staticmethod
    def _emparejar_por_iou(iou: np.ndarray, iou_minimo: float) -> list[tuple[int, int]]:
        """Los pares bajo el umbral se prohíben ANTES de resolver: filtrarlos después deja
        que el húngaro sacrifique un par válido por dos inválidos (el `cost_limit` de
        `lapjv` en el original)."""
        costo = np.where(iou >= iou_minimo, 1.0 - iou, _PROHIBIDO)
        filas, columnas = linear_sum_assignment(costo)
        return [
            (int(f), int(c))
            for f, c in zip(filas, columnas, strict=True)
            if iou[f, c] >= iou_minimo
        ]
