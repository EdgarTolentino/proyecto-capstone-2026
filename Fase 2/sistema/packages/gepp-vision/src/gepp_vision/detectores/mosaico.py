"""Detector en mosaico: para objetos chicos en cámaras lejanas (#31).

Un modelo achica el cuadro a su resolución de entrada. En el video de prueba, una cámara
fija mira un foso desde arriba: un casco del fondo mide ~8 px en el cuadro de 1080 y, al
pasar el cuadro entero a 384, queda en 1-2 px, donde ningún detector lo ve.

`DetectorMosaico` envuelve a cualquier `Detector`:

1. **recorta** la zona que importa (`Mosaico.recorte`, normalizada al cuadro);
2. la **amplía** `factor` veces;
3. la **parte** en mosaicos de `lado` píxeles (el de entrada del modelo, para que no los
   vuelva a achicar) que se solapan lo suficiente para que **cualquier objeto de hasta
   `objeto_max_px` quepa entero en al menos uno**;
4. corre el detector en cada mosaico y descarta las cajas que tocan un borde interior:
   son pedazos de un objeto que otro mosaico ve entero;
5. un objeto en el solape lo ven entero dos o cuatro mosaicos: de esos grupos (**solo entre
   mosaicos distintos**, misma clase, centros a menos de medio lado del más chico) queda el
   de mayor confianza;
6. devuelve las cajas a coordenadas del cuadro.

Por qué así y no fusionando por IoU, como la primera versión. Esa fallaba en las dos
direcciones: con un solape fijo del 20 %, una persona de 60 px salía dos veces (revisión del
#31); dos mosaicos que ven a la misma persona con contexto distinto dan cajas con IoU 0,60,
justo en el umbral (visto en el video de prueba); y fusionar por contención borraba a una
persona tapada por otra. Comparar centros tolera que cada mosaico dibuje la caja algo
distinta, y lo que el modelo ve junto en un mismo mosaico (un casco dentro de su persona,
una persona tapada por otra) nunca se compara.

Los objetos más grandes que `objeto_max_px` (alguien que pasa junto a la cámara) quedan
cortados en todos los mosaicos y se descartan: para eso está `con_cuadro_completo`, que
además corre el detector sobre el cuadro entero. Los dos pases quedan **disjuntos**: el
completo aporta lo que el mosaico no puede ver (lo que no cae entero dentro del recorte, o
es más grande que `objeto_max_px`), y el mosaico, lo demás. Por eso, con pase completo, el
borde del recorte cuenta como borde interior: lo que lo cruza lo aporta el pase completo.

Con recorte del foso (~800 px), factor 2 y mosaicos de 384, un casco de 8 px llega al modelo
con ~16 px. El costo es correr el modelo decenas de veces por cuadro (`MAX_MOSAICOS` pone
el tope): sirve para evaluar y para el trabajador en GPU, no para tiempo real en CPU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np
from gepp_core import Caja, Deteccion

from gepp_vision.puertos import Detector

#: A esta distancia (px del mosaico) de un borde interior, la caja se considera cortada.
MARGEN_BORDE = 1
#: Dos detecciones de mosaicos distintos con los centros a menos de esta fracción del lado
#: más corto de la más chica son el mismo objeto.
DISTANCIA_MISMO_OBJETO = 0.5
#: Holgura del solape sobre el objeto más grande: el modelo puede dibujar la caja algo más
#: grande o corrida, y una caja que toca el borde se descarta como pedazo.
HOLGURA_SOLAPE = 1.2
#: Mosaicos por cuadro sobre los que se rechaza la configuración: el costo se dispara sin
#: avisar (con factor 2, lado 384 y sin recorte, 1920x1080 serían 231).
MAX_MOSAICOS = 64


@dataclass(frozen=True, slots=True)
class Mosaico:
    recorte: Caja
    factor: float
    lado: int
    #: Lado del objeto más grande que tiene que caber entero en un mosaico, en px del cuadro.
    objeto_max_px: int
    con_cuadro_completo: bool = False

    def __post_init__(self) -> None:
        if self.factor <= 0:
            raise ValueError("factor debe ser positivo")
        if self.lado <= 0 or self.objeto_max_px <= 0:
            raise ValueError("lado y objeto_max_px deben ser positivos")
        if self.solape_px >= self.lado:
            raise ValueError(
                f"un objeto de {self.objeto_max_px} px ampliado {self.factor:g}x no cabe "
                f"entero en mosaicos de {self.lado}: use mosaicos más grandes o menos factor"
            )

    @property
    def solape_px(self) -> int:
        """Solape entre mosaicos vecinos, en px ampliados: el objeto más grande, con holgura."""
        return math.ceil(self.objeto_max_px * self.factor * HOLGURA_SOLAPE) + 2 * MARGEN_BORDE + 2


def posiciones(largo: int, lado: int, solape: int) -> list[int]:
    """Inicio de cada mosaico a lo largo de un eje, con al menos `solape` px compartidos
    entre vecinos. El último se alinea al final."""
    if largo <= lado:
        return [0]
    paso = max(lado - solape, 1)
    inicios = [0]
    while inicios[-1] + lado < largo:
        inicios.append(min(inicios[-1] + paso, largo - lado))
    return inicios


def _mismo_objeto(a: Deteccion, b: Deteccion) -> bool:
    if a.clase is not b.clase:
        return False
    (ax, ay), (bx, by) = a.caja.centro, b.caja.centro
    chica = a.caja if a.caja.area <= b.caja.area else b.caja
    # Las cajas están normalizadas: se compara en las mismas unidades por eje.
    return (
        abs(ax - bx) < DISTANCIA_MISMO_OBJETO * chica.ancho
        and abs(ay - by) < DISTANCIA_MISMO_OBJETO * chica.alto
    )


def sin_repetidos(por_mosaico: list[list[Deteccion]]) -> list[Deteccion]:
    """Une las detecciones de todos los mosaicos. Si dos de mosaicos DISTINTOS son el mismo
    objeto, queda la de mayor confianza; las de un mismo mosaico nunca se comparan."""
    ordenadas = sorted(
        ((d, i) for i, ds in enumerate(por_mosaico) for d in ds),
        key=lambda par: par[0].confianza,
        reverse=True,
    )
    quedan: list[tuple[Deteccion, int]] = []
    for d, i in ordenadas:
        if not any(j != i and _mismo_objeto(d, q) for q, j in quedan):
            quedan.append((d, i))
    return [d for d, _ in quedan]


class DetectorMosaico:
    """Cumple el protocolo `Detector`."""

    def __init__(self, interno: Detector, mosaico: Mosaico) -> None:
        self._interno = interno
        self._mosaico = mosaico

    @property
    def version(self) -> str:
        m = self._mosaico
        r = m.recorte
        completo = "+completo" if m.con_cuadro_completo else ""
        return (
            f"mosaico[{r.x1:.4f},{r.y1:.4f},{r.x2:.4f},{r.y2:.4f}"
            f"x{m.factor:g}/{m.lado}/{m.objeto_max_px}px{completo}]:{self._interno.version}"
        )

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        todas = sin_repetidos(self._en_mosaicos(imagen, cuadro_idx, capture_ts))
        if self._mosaico.con_cuadro_completo:
            alto, ancho = imagen.shape[:2]
            todas += [
                d
                for d in self._interno.detectar(
                    imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts
                )
                if not self._la_ve_el_mosaico(d.caja, ancho, alto)
            ]
        return todas

    def _la_ve_el_mosaico(self, caja: Caja, ancho: int, alto: int) -> bool:
        """Cae entera dentro del recorte y cabe entera en un mosaico."""
        r = self._mosaico.recorte
        dentro = caja.x1 >= r.x1 and caja.y1 >= r.y1 and caja.x2 <= r.x2 and caja.y2 <= r.y2
        cabe = max(caja.ancho * ancho, caja.alto * alto) <= self._mosaico.objeto_max_px
        return dentro and cabe

    def _en_mosaicos(
        self, imagen: np.ndarray, cuadro_idx: int, capture_ts: datetime
    ) -> list[list[Deteccion]]:
        """Las detecciones de cada mosaico, ya en coordenadas del cuadro."""
        alto, ancho = imagen.shape[:2]
        m = self._mosaico
        x0, y0 = round(m.recorte.x1 * ancho), round(m.recorte.y1 * alto)
        x1, y1 = round(m.recorte.x2 * ancho), round(m.recorte.y2 * alto)
        if x1 <= x0 or y1 <= y0:
            return []
        ancho_z = max(round((x1 - x0) * m.factor), 1)
        alto_z = max(round((y1 - y0) * m.factor), 1)
        columnas = posiciones(ancho_z, m.lado, m.solape_px)
        filas = posiciones(alto_z, m.lado, m.solape_px)
        if len(columnas) * len(filas) > MAX_MOSAICOS:
            raise ValueError(
                f"{len(columnas) * len(filas)} mosaicos por cuadro (tope {MAX_MOSAICOS}): "
                "achique el recorte, el factor u objeto_max_px"
            )
        ampliada = cv2.resize(
            imagen[y0:y1, x0:x1], (ancho_z, alto_z), interpolation=cv2.INTER_LINEAR
        )
        # Escala real tras redondear: píxel ampliado -> píxel del cuadro.
        ex, ey = (x1 - x0) / ancho_z, (y1 - y0) / alto_z
        # Con pase completo, el borde del recorte es interior salvo donde coincide con el
        # del cuadro: lo que lo cruza lo aporta el pase completo, entero.
        borde_recorte = (
            (x0 > 0, y0 > 0, x1 < ancho, y1 < alto) if m.con_cuadro_completo else (False,) * 4
        )

        por_mosaico: list[list[Deteccion]] = []
        for ty in filas:
            for tx in columnas:
                parte = ampliada[ty : ty + m.lado, tx : tx + m.lado]
                alto_p, ancho_p = parte.shape[:2]
                # Un borde es interior si del otro lado sigue habiendo zona ampliada.
                interior = (
                    tx > 0 or borde_recorte[0],
                    ty > 0 or borde_recorte[1],
                    tx + ancho_p < ancho_z or borde_recorte[2],
                    ty + alto_p < alto_z or borde_recorte[3],
                )
                propias: list[Deteccion] = []
                for d in self._interno.detectar(
                    parte, cuadro_idx=cuadro_idx, capture_ts=capture_ts
                ):
                    c = d.caja
                    px1, py1 = c.x1 * ancho_p, c.y1 * alto_p
                    px2, py2 = c.x2 * ancho_p, c.y2 * alto_p
                    toca = (
                        px1 <= MARGEN_BORDE,
                        py1 <= MARGEN_BORDE,
                        px2 >= ancho_p - MARGEN_BORDE,
                        py2 >= alto_p - MARGEN_BORDE,
                    )
                    if any(t and i for t, i in zip(toca, interior, strict=True)):
                        continue  # un pedazo: el mosaico vecino lo ve entero
                    lado_px = max((px2 - px1) * ex, (py2 - py1) * ey)
                    if m.con_cuadro_completo and lado_px > m.objeto_max_px:
                        continue  # más grande de lo previsto: lo aporta el pase completo
                    cx1 = max((x0 + (tx + px1) * ex) / ancho, 0.0)
                    cy1 = max((y0 + (ty + py1) * ey) / alto, 0.0)
                    cx2 = min((x0 + (tx + px2) * ex) / ancho, 1.0)
                    cy2 = min((y0 + (ty + py2) * ey) / alto, 1.0)
                    if cx2 > cx1 and cy2 > cy1:
                        propias.append(
                            Deteccion(
                                capture_ts=d.capture_ts,
                                cuadro_idx=d.cuadro_idx,
                                clase=d.clase,
                                caja=Caja(cx1, cy1, cx2, cy2),
                                confianza=d.confianza,
                                track_id=None,
                            )
                        )
                por_mosaico.append(propias)
        return por_mosaico
