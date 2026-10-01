"""Detector en mosaico: para objetos chicos en cámaras lejanas (#31).

Un modelo achica el cuadro a su resolución de entrada. En el video de prueba, una cámara
fija mira un foso desde arriba: un casco del fondo mide ~8 px en el cuadro de 1080 y, al
pasar el cuadro entero a 384, queda en 1-2 px, donde ningún detector lo ve.

`DetectorMosaico` envuelve a cualquier `Detector`:

1. **recorta** la zona que importa (`Mosaico.recorte`, normalizada al cuadro);
2. la **amplía** `factor` veces;
3. la **parte** en mosaicos de `lado` píxeles con un `solape`, para que un objeto cortado
   por un borde aparezca entero en el mosaico vecino;
4. corre el detector en cada mosaico, devuelve las cajas a coordenadas del cuadro completo y
   **fusiona** las repetidas en los solapes.

Con `con_cuadro_completo`, además corre el detector sobre el cuadro entero y fusiona: las
personas cerca de la cámara, grandes y fuera del recorte, no se pierden.

Con recorte del foso (~800 px), factor 2 y mosaicos de 640, un casco de 8 px llega al modelo
con ~16 px. El costo es correr el modelo varias veces por cuadro: sirve para evaluar y para
el trabajador en GPU, no para tiempo real en CPU.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np
from gepp_core import Caja, Deteccion

from gepp_vision.puertos import Detector

#: Dos cajas de la misma clase que se solapan así son el mismo objeto visto en dos mosaicos.
UMBRAL_FUSION = 0.5
#: Una caja contenida así en otra es el mismo objeto cortado por el borde de un mosaico.
UMBRAL_CONTENIDA = 0.8


@dataclass(frozen=True, slots=True)
class Mosaico:
    recorte: Caja
    factor: float
    lado: int
    solape: float = 0.2
    con_cuadro_completo: bool = False

    def __post_init__(self) -> None:
        if self.factor <= 0:
            raise ValueError("factor debe ser positivo")
        if self.lado <= 0:
            raise ValueError("lado debe ser positivo")
        if not 0 <= self.solape < 1:
            raise ValueError("solape debe estar en [0, 1)")


def posiciones(largo: int, lado: int, solape: float) -> list[int]:
    """Inicio de cada mosaico a lo largo de un eje. El último se alinea al final."""
    if largo <= lado:
        return [0]
    paso = max(int(lado * (1 - solape)), 1)
    inicios = [0]
    while inicios[-1] + lado < largo:
        siguiente = inicios[-1] + paso
        inicios.append(min(siguiente, largo - lado))
    return inicios


def _mismo_objeto(a: Deteccion, b: Deteccion) -> bool:
    if a.clase is not b.clase:
        return False
    inter = a.caja.interseccion(b.caja)
    menor = min(a.caja.area, b.caja.area)
    return a.caja.iou(b.caja) >= UMBRAL_FUSION or (menor > 0 and inter / menor >= UMBRAL_CONTENIDA)


def fusionar(detecciones: list[Deteccion]) -> list[Deteccion]:
    """De cada grupo de repetidas queda la de mayor confianza."""
    quedan: list[Deteccion] = []
    for d in sorted(detecciones, key=lambda d: d.confianza, reverse=True):
        if not any(_mismo_objeto(d, q) for q in quedan):
            quedan.append(d)
    return quedan


class DetectorMosaico:
    """Cumple el protocolo `Detector`."""

    def __init__(self, interno: Detector, mosaico: Mosaico) -> None:
        self._interno = interno
        self._mosaico = mosaico

    @property
    def version(self) -> str:
        m = self._mosaico
        r = m.recorte
        return (
            f"mosaico[{r.x1:.2f},{r.y1:.2f},{r.x2:.2f},{r.y2:.2f}"
            f"x{m.factor:g}/{m.lado}/{m.solape:g}{'+completo' if m.con_cuadro_completo else ''}]"
            f":{self._interno.version}"
        )

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        alto, ancho = imagen.shape[:2]
        m = self._mosaico
        x0, y0 = round(m.recorte.x1 * ancho), round(m.recorte.y1 * alto)
        x1, y1 = round(m.recorte.x2 * ancho), round(m.recorte.y2 * alto)
        if x1 <= x0 or y1 <= y0:
            return []
        zona = imagen[y0:y1, x0:x1]
        ancho_z, alto_z = max(round((x1 - x0) * m.factor), 1), max(round((y1 - y0) * m.factor), 1)
        ampliada = cv2.resize(zona, (ancho_z, alto_z), interpolation=cv2.INTER_LINEAR)
        # Escala real tras redondear: píxel ampliado -> píxel del cuadro.
        ex, ey = (x1 - x0) / ancho_z, (y1 - y0) / alto_z

        todas: list[Deteccion] = []
        if m.con_cuadro_completo:
            todas += self._interno.detectar(imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts)
        for ty in posiciones(alto_z, m.lado, m.solape):
            for tx in posiciones(ancho_z, m.lado, m.solape):
                parte = ampliada[ty : ty + m.lado, tx : tx + m.lado]
                alto_p, ancho_p = parte.shape[:2]
                for d in self._interno.detectar(
                    parte, cuadro_idx=cuadro_idx, capture_ts=capture_ts
                ):
                    c = d.caja
                    cx1 = (x0 + (tx + c.x1 * ancho_p) * ex) / ancho
                    cy1 = (y0 + (ty + c.y1 * alto_p) * ey) / alto
                    cx2 = (x0 + (tx + c.x2 * ancho_p) * ex) / ancho
                    cy2 = (y0 + (ty + c.y2 * alto_p) * ey) / alto
                    cx1, cy1 = max(cx1, 0.0), max(cy1, 0.0)
                    cx2, cy2 = min(cx2, 1.0), min(cy2, 1.0)
                    if cx2 > cx1 and cy2 > cy1:
                        todas.append(
                            Deteccion(
                                capture_ts=d.capture_ts,
                                cuadro_idx=d.cuadro_idx,
                                clase=d.clase,
                                caja=Caja(cx1, cy1, cx2, cy2),
                                confianza=d.confianza,
                                track_id=None,
                            )
                        )
        return fusionar(todas)
