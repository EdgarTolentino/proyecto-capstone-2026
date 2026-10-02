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
5. un objeto en el solape lo ven entero dos o cuatro mosaicos. Esas copias se emparejan
   **uno a uno** (método húngaro sobre la distancia entre centros) y de cada par queda la
   de mayor confianza. Solo se emparejan detecciones de mosaicos distintos, de la misma
   clase, con centros a menos de medio lado de la más chica, y **solo si cada mosaico
   debía ver entera a la otra**: si no la contiene, no puede ser su copia;
6. devuelve las cajas a coordenadas del cuadro.

Por qué así y no fusionando por IoU, como la primera versión. Esa fallaba en las dos
direcciones: con un solape fijo del 20 %, una persona de 60 px salía dos veces (revisión del
#31); dos mosaicos que ven a la misma persona con contexto distinto dan cajas con IoU 0,60,
justo en el umbral (visto en el video de prueba); y fusionar por contención borraba a una
persona tapada por otra. Comparar centros tolera que cada mosaico dibuje la caja algo
distinta; el emparejamiento uno a uno impide que una copia se coma a una persona vecina; y
lo que el modelo ve junto en un mismo mosaico (un casco dentro de su persona) nunca se
compara. Una segunda revisión encontró que, sin la condición de contención, una persona
tapada en el solape se borraba al compararla con la del mosaico que no la veía.

Solo se analiza el recorte: es la zona donde se evalúa EPP (las reglas trabajan por zonas).
Hubo una opción para sumar un pase sobre el cuadro completo y se quitó: dos cajas del mismo
objeto a escalas distintas nunca coinciden, y repartir objetos entre los dos pases perdía o
duplicaba los que quedaban en el borde del recorte (segunda revisión del #31).

Un objeto más grande que `objeto_max_px` puede quedar cortado en todos los mosaicos y
perderse: `objeto_max_px` se elige con el objeto más grande de la zona.

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
from scipy.optimize import linear_sum_assignment

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


def _contiene(region: Caja, caja: Caja) -> bool:
    e = 1e-9
    return (
        caja.x1 >= region.x1 - e
        and caja.y1 >= region.y1 - e
        and caja.x2 <= region.x2 + e
        and caja.y2 <= region.y2 + e
    )


def _copias(a: Deteccion, region_a: Caja, b: Deteccion, region_b: Caja) -> bool:
    """¿Pueden ser el mismo objeto visto por dos mosaicos?"""
    if a.clase is not b.clase or not (_contiene(region_a, b.caja) and _contiene(region_b, a.caja)):
        return False
    (ax, ay), (bx, by) = a.caja.centro, b.caja.centro
    chica = a.caja if a.caja.area <= b.caja.area else b.caja
    return (
        abs(ax - bx) < DISTANCIA_MISMO_OBJETO * chica.ancho
        and abs(ay - by) < DISTANCIA_MISMO_OBJETO * chica.alto
    )


def sin_repetidos(por_mosaico: list[tuple[Caja, list[Deteccion]]]) -> list[Deteccion]:
    """Une las detecciones de todos los mosaicos (cada una con la región del cuadro que cubre
    su mosaico). Las copias del mismo objeto en mosaicos distintos se emparejan uno a uno y
    queda la de mayor confianza; las de un mismo mosaico nunca se comparan."""
    quedan: list[tuple[Deteccion, Caja, int]] = []
    for i, (region, detecciones) in enumerate(por_mosaico):
        # Solo hay detecciones de mosaicos anteriores: las de este se agregan al final, así
        # que dos del mismo mosaico nunca se comparan.
        previas = list(enumerate(quedan))
        posibles = [[_copias(d, region, q, rq) for _, (q, rq, _) in previas] for d in detecciones]
        emparejadas: set[int] = set()
        if previas and detecciones:
            costo = np.array(
                [
                    [
                        abs(d.caja.centro[0] - q.caja.centro[0])
                        + abs(d.caja.centro[1] - q.caja.centro[1])
                        if posibles[f][c]
                        else 1e6
                        for c, (_, (q, _, _)) in enumerate(previas)
                    ]
                    for f, d in enumerate(detecciones)
                ]
            )
            for f, c in zip(*linear_sum_assignment(costo), strict=True):
                if not posibles[f][c]:
                    continue
                k = previas[c][0]
                if detecciones[f].confianza > quedan[k][0].confianza:
                    quedan[k] = (detecciones[f], region, i)
                emparejadas.add(int(f))
        quedan += [(d, region, i) for f, d in enumerate(detecciones) if f not in emparejadas]
    return [d for d, _, _ in quedan]


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
            f"mosaico[{r.x1:.4f},{r.y1:.4f},{r.x2:.4f},{r.y2:.4f}"
            f"x{m.factor:g}/{m.lado}/{m.objeto_max_px}px]:{self._interno.version}"
        )

    def validar(self, ancho: int, alto: int) -> None:
        """Falla si, para cuadros de este tamaño, la configuración pasa de `MAX_MOSAICOS`.
        Para llamarla al abrir la fuente, antes del primer cuadro."""
        _, _, columnas, filas = self._geometria(ancho, alto)
        if len(columnas) * len(filas) > MAX_MOSAICOS:
            raise ValueError(
                f"{len(columnas) * len(filas)} mosaicos por cuadro (tope {MAX_MOSAICOS}): "
                "achique el recorte, el factor u objeto_max_px"
            )

    def _geometria(self, ancho: int, alto: int) -> tuple[int, int, list[int], list[int]]:
        """Tamaño de la zona ampliada y posiciones de los mosaicos."""
        m = self._mosaico
        x0, x1 = round(m.recorte.x1 * ancho), round(m.recorte.x2 * ancho)
        y0, y1 = round(m.recorte.y1 * alto), round(m.recorte.y2 * alto)
        ancho_z = max(round((x1 - x0) * m.factor), 1)
        alto_z = max(round((y1 - y0) * m.factor), 1)
        return (
            ancho_z,
            alto_z,
            posiciones(ancho_z, m.lado, m.solape_px),
            posiciones(alto_z, m.lado, m.solape_px),
        )

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        return sin_repetidos(self._en_mosaicos(imagen, cuadro_idx, capture_ts))

    def _en_mosaicos(
        self, imagen: np.ndarray, cuadro_idx: int, capture_ts: datetime
    ) -> list[tuple[Caja, list[Deteccion]]]:
        """Por mosaico: la región del cuadro que cubre y sus detecciones, en coordenadas del
        cuadro."""
        alto, ancho = imagen.shape[:2]
        m = self._mosaico
        x0, y0 = round(m.recorte.x1 * ancho), round(m.recorte.y1 * alto)
        x1, y1 = round(m.recorte.x2 * ancho), round(m.recorte.y2 * alto)
        if x1 <= x0 or y1 <= y0:
            return []
        self.validar(ancho, alto)
        ancho_z, alto_z, columnas, filas = self._geometria(ancho, alto)
        ampliada = cv2.resize(
            imagen[y0:y1, x0:x1], (ancho_z, alto_z), interpolation=cv2.INTER_LINEAR
        )
        # Escala real tras redondear: píxel ampliado -> píxel del cuadro.
        ex, ey = (x1 - x0) / ancho_z, (y1 - y0) / alto_z

        por_mosaico: list[tuple[Caja, list[Deteccion]]] = []
        for ty in filas:
            for tx in columnas:
                parte = ampliada[ty : ty + m.lado, tx : tx + m.lado]
                alto_p, ancho_p = parte.shape[:2]
                # Un borde es interior si del otro lado sigue habiendo zona ampliada.
                interior = (tx > 0, ty > 0, tx + ancho_p < ancho_z, ty + alto_p < alto_z)
                region = Caja(
                    (x0 + tx * ex) / ancho,
                    (y0 + ty * ey) / alto,
                    (x0 + (tx + ancho_p) * ex) / ancho,
                    (y0 + (ty + alto_p) * ey) / alto,
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
                por_mosaico.append((region, propias))
        return por_mosaico
