"""Muestreo a cadencia fija: de los fps de la fuente a `fps_objetivo` (5 por defecto).

Por qué 5 y no 2: a 2 fps una persona caminando recorre más de un ancho de caja entre
cuadros y ByteTrack fragmenta el track (ver `00-arquitectura.md`).

El muestreador envuelve una fuente y es él mismo una `FuenteDeCuadros`: aguas abajo nadie
distingue si recibe el video completo o muestreado. Los cuadros conservan su **índice de
origen**, de modo que `capture_ts = inicio_captura + indice / fps_origen` sigue siendo
verdad (ADR-005).

La selección se hace por **instante objetivo**, no por paso entero: pasa el primer cuadro de
origen que alcanza cada tic de `1 / fps_objetivo`. Con un paso entero (cada 5 cuadros a
25 fps, cada 6 a 30, ¿cada 4 o 5 a 24?) la cadencia real cambia según el origen y la
deriva se acumula; así, no.
"""

from __future__ import annotations

import math
import os
from fractions import Fraction

from gepp_worker.fuente import Cuadro, FuenteDeCuadros, PropiedadesFuente

FPS_OBJETIVO_POR_DEFECTO = 5.0
VARIABLE_FPS_OBJETIVO = "GEPP_FPS_OBJETIVO"


def fps_objetivo_configurado() -> float:
    """Lee `GEPP_FPS_OBJETIVO` del entorno; 5 si no está."""
    texto = os.environ.get(VARIABLE_FPS_OBJETIVO)
    if texto is None or not texto.strip():
        return FPS_OBJETIVO_POR_DEFECTO
    valor = float(texto)
    if valor <= 0 or not math.isfinite(valor):
        raise ValueError(f"{VARIABLE_FPS_OBJETIVO} debe ser positivo, no {texto!r}")
    return valor


def _como_fraccion(fps: float) -> Fraction:
    # 29,97 es 30000/1001: con fracciones exactas la selección no deriva en videos largos.
    return Fraction(fps).limit_denominator(1001)


def pasa(indice: int, fps_origen: float, fps_objetivo: float) -> bool:
    """¿El cuadro de origen `indice` es el primero en alcanzar un tic del objetivo?

    El cuadro i ocupa el instante i / fps_origen; en unidades de tic eso es
    i · fps_objetivo / fps_origen. Pasa cuando el tic entero cambia respecto del cuadro
    anterior. Si el origen es más lento que el objetivo, pasan todos.
    """
    if indice < 0:
        raise ValueError("el índice no puede ser negativo")
    if fps_origen <= 0 or fps_objetivo <= 0:
        raise ValueError("los fps deben ser positivos")
    if fps_origen <= fps_objetivo or indice == 0:
        return True
    razon = _como_fraccion(fps_objetivo) / _como_fraccion(fps_origen)
    return math.floor(indice * razon) != math.floor((indice - 1) * razon)


class Muestreador:
    """Envuelve una `FuenteDeCuadros` y deja pasar solo los cuadros del objetivo.

    `tomar()` avanza la fuente, sin decodificar, hasta el próximo cuadro que pasa;
    `recuperar()` decodifica solo ese.
    """

    def __init__(self, fuente: FuenteDeCuadros, fps_objetivo: float | None = None) -> None:
        objetivo = fps_objetivo_configurado() if fps_objetivo is None else fps_objetivo
        if objetivo <= 0:
            raise ValueError("fps_objetivo debe ser positivo")
        self._fuente = fuente
        self._fps_objetivo = objetivo
        self._indice = -1

    @property
    def fps_efectivo(self) -> float:
        """Cadencia real que ve el pipeline. Es la que convierte segundos a cuadros."""
        return min(self._fps_objetivo, self._fuente.propiedades().fps)

    def abrir(self) -> None:
        self._fuente.abrir()
        self._indice = -1

    def tomar(self) -> bool:
        fps_origen = self._fuente.propiedades().fps
        while self._fuente.tomar():
            self._indice += 1
            if pasa(self._indice, fps_origen, self._fps_objetivo):
                return True
        return False

    def recuperar(self) -> Cuadro | None:
        return self._fuente.recuperar()

    def cerrar(self) -> None:
        self._fuente.cerrar()

    def propiedades(self) -> PropiedadesFuente:
        """Las de la fuente, intactas: `fps` es el de origen, el que fecha los cuadros."""
        return self._fuente.propiedades()
