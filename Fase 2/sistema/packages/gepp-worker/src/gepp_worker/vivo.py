"""Escritor de la vista en vivo: un anillo de los últimos cuadros del video, en memoria.

Excepción acotada a la minimización (`02-privacidad-y-cumplimiento.md`, «Excepción: vista en vivo
del procesamiento»), solo para el prototipo local. Aquí se cumple la parte del trabajador:

- **Apagada por defecto.** Solo con `GEPP_VISTA_EN_VIVO=1`; apagada, no se crea ni se escribe
  nada y los cuadros que el muestreo salta ni siquiera se decodifican.
- **Todos los cuadros del video**, también los que el modelo no analizó. En los saltados, las
  cajas son las del ÚLTIMO cuadro analizado (hasta 0,2 s atrás a 5 fps). A todo cuadro, analizado
  o saltado, se le aplican los polígonos de privacidad: `VistaDeVideo` no existe sin la función
  que los aplica.
- **Anillo por video:** `GEPP_CARPETA_VIVO/<video_id>/<seq:08d>_<pos_ms:09d>.jpg` (por defecto
  `/dev/shm/gepp-vivo`, memoria), subcarpeta 0700. `seq` arranca en 1 en cada intento y crece de a
  1; `pos_ms` es la posición en el VIDEO, en milisegundos. Se escribe a un temporal oculto en la
  misma subcarpeta y se publica con `os.replace`: quien lee ve el cuadro entero o no lo ve.
  Quedan como mucho los últimos 60; los más viejos se borran.
- **Ritmo:** `GEPP_VIVO_FPS` (25 por defecto) limita los cuadros escritos por segundo de VIDEO, no
  de reloj, con la misma regla del muestreo (`gepp_worker.muestreo.pasa`): 25 fps de un origen a
  30 da 25, sin deriva.
- **Efímero:** se borra la subcarpeta al terminar el intento (listo, error o reintento) y todo,
  subcarpetas incluidas, al arrancar el trabajador, por si un corte dejó algo.
- **Falla sin detener:** si escribir falla, se dice por stderr (la primera vez por intento) y el
  análisis sigue.

`/dev/shm` puede ir a swap, y los cuadros son NÍTIDOS y sin rostros tapados (decisión de Edgar
Tolentino del 2026-10-09): lo que llegue a swap puede contener rostros. Solo prototipo
local; ver la excepción en `02-privacidad-y-cumplimiento.md`.
"""

from __future__ import annotations

import math
import os
import shutil
import stat
import sys
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path

import numpy as np
from gepp_core import Deteccion
from gepp_vision.pipeline import CuadroFechado
from gepp_vision.vivo import cuadro_en_vivo

from gepp_worker.fuente import Cuadro
from gepp_worker.muestreo import pasa

CARPETA_POR_DEFECTO = "/dev/shm/gepp-vivo"
#: Cuadros por segundo de video que se escriben a la vista.
FPS_VIVO_POR_DEFECTO = 25.0
VARIABLE_FPS = "GEPP_VIVO_FPS"
#: Cuántos cuadros quedan en memoria por video.
MAXIMO_CUADROS = 60


def fps_configurado(entorno: Mapping[str, str] | None = None) -> float:
    """Lee `GEPP_VIVO_FPS`; 25 si no está. Un valor que no sea un número positivo y finito es un
    error de configuración: falla al arrancar, no una vista que nunca (o siempre) escribe."""
    entorno = os.environ if entorno is None else entorno
    texto = entorno.get(VARIABLE_FPS)
    if texto is None or not texto.strip():
        return FPS_VIVO_POR_DEFECTO
    try:
        valor = float(texto)
    except ValueError:
        raise ValueError(f"{VARIABLE_FPS} debe ser un número, no {texto!r}") from None
    if valor <= 0 or not math.isfinite(valor):
        raise ValueError(f"{VARIABLE_FPS} debe ser positivo, no {texto!r}")
    return valor


def carpeta_configurada(entorno: dict[str, str] | os._Environ[str] | None = None) -> Path | None:
    """La carpeta de la vista en vivo, o None si está apagada (lo normal)."""
    entorno = os.environ if entorno is None else entorno
    if entorno.get("GEPP_VISTA_EN_VIVO", "").strip() != "1":
        return None
    return Path(entorno.get("GEPP_CARPETA_VIVO", "").strip() or CARPETA_POR_DEFECTO)


def nombre_de_cuadro(seq: int, pos_ms: int) -> str:
    return f"{seq:08d}_{pos_ms:09d}.jpg"


def _decir(mensaje: str, e: BaseException) -> None:
    print(f"[trabajador] {mensaje}: {e!r}", file=sys.stderr)


def _quitar(ruta: Path) -> None:
    """Borra un archivo, un enlace o una carpeta entera sin seguir enlaces."""
    if ruta.is_symlink() or ruta.is_file():
        ruta.unlink(missing_ok=True)
    elif ruta.is_dir():
        shutil.rmtree(ruta)


class VistaDeVideo:
    """El anillo de UN intento de UN video. Implementa `ObservadorDeSaltados`.

    Se obtiene con `EscritorVivo.abrir`, que exige la función que aplica los polígonos de
    privacidad: no hay forma de escribir un cuadro sin pasar por ella.
    """

    def __init__(
        self,
        carpeta: Path | None,
        *,
        fps_origen: float,
        fps_vivo: float,
        inicio_captura: datetime,
        enmascarar: Callable[[np.ndarray], np.ndarray],
        maximo: int = MAXIMO_CUADROS,
    ) -> None:
        self._carpeta = carpeta  # None: no se pudo preparar; todo es un no-hacer
        self._fps_origen = fps_origen
        self._fps_vivo = fps_vivo
        self._inicio = inicio_captura
        self._enmascarar = enmascarar
        self._maximo = maximo
        self._seq = 0
        self._escritos: deque[Path] = deque()
        self._ultimas: list[Deteccion] = []  # las del último cuadro analizado
        self._avisado = False

    # ── Lo que llama el muestreador (cuadros saltados) ───────────────────────────────────

    def quiere(self, indice: int) -> bool:
        return self._carpeta is not None and pasa(indice, self._fps_origen, self._fps_vivo)

    def al_saltar(self, cuadro: Cuadro) -> None:
        """Un cuadro que el modelo no analiza: cajas del último análisis."""
        self._escribir(self._enmascarar(cuadro.imagen), cuadro)

    # ── Lo que llama el trabajador (cuadros analizados) ──────────────────────────────────

    def analizado(
        self,
        cuadro: CuadroFechado,
        imagen_enmascarada: np.ndarray,
        detecciones: Iterable[Deteccion],
    ) -> None:
        """Un cuadro analizado: `imagen_enmascarada` es la que vio el detector."""
        self._ultimas = list(detecciones)
        if self.quiere(cuadro.indice):
            self._escribir(imagen_enmascarada, cuadro)

    # ── Escritura ────────────────────────────────────────────────────────────────────────

    def _escribir(self, imagen: np.ndarray, cuadro: CuadroFechado) -> None:
        carpeta = self._carpeta
        if carpeta is None:
            return
        seq = self._seq + 1
        pos_ms = max(0, round((cuadro.capture_ts - self._inicio).total_seconds() * 1000))
        temporal = carpeta / f".{seq:08d}.tmp"
        destino = carpeta / nombre_de_cuadro(seq, pos_ms)
        try:
            datos = cuadro_en_vivo(imagen, self._ultimas)
            fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(datos)
            os.replace(temporal, destino)
        except Exception as e:
            temporal.unlink(missing_ok=True)
            if not self._avisado:  # a 25 cuadros por segundo, un aviso por intento basta
                self._avisado = True
                _decir("no se pudo escribir la vista en vivo", e)
            return
        self._seq = seq
        self._escritos.append(destino)
        while len(self._escritos) > self._maximo:
            try:
                self._escritos.popleft().unlink(missing_ok=True)
            except OSError as e:
                _decir("no se pudo podar la vista en vivo", e)

    def cerrar(self) -> None:
        """Al terminar el intento, pase lo que pase: la subcarpeta entera. Nunca lanza."""
        if self._carpeta is None:
            return
        try:
            _quitar(self._carpeta)
        except OSError as e:
            _decir("no se pudo borrar la vista en vivo", e)
        self._escritos.clear()


class EscritorVivo:
    def __init__(self, carpeta: Path, *, fps: float = FPS_VIVO_POR_DEFECTO) -> None:
        if fps <= 0 or not math.isfinite(fps):
            raise ValueError(f"fps de la vista debe ser positivo, no {fps!r}")
        self._carpeta = carpeta
        self._fps = fps
        self._preparar()

    @property
    def carpeta(self) -> Path:
        return self._carpeta

    def _preparar(self) -> None:
        self._carpeta.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self._carpeta.lstat()  # sin seguir enlaces: un symlink no es nuestra carpeta
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError(f"{self._carpeta} no es una carpeta propia: no se usa para la vista")
        self._carpeta.chmod(0o700)

    def vaciar(self) -> None:
        """Quita todo lo que haya: subcarpetas de corridas anteriores, temporales y archivos
        sueltos de versiones viejas."""
        for entrada in self._carpeta.iterdir():
            try:
                _quitar(entrada)
            except OSError as e:
                _decir("no se pudo vaciar la vista en vivo", e)

    def abrir(
        self,
        video_id: int,
        *,
        fps_origen: float,
        inicio_captura: datetime,
        enmascarar: Callable[[np.ndarray], np.ndarray],
    ) -> VistaDeVideo:
        """El anillo de un intento: parte de una subcarpeta vacía y `seq` en 1. Nunca lanza."""
        subcarpeta: Path | None = self._carpeta / str(int(video_id))
        try:
            assert subcarpeta is not None
            _quitar(subcarpeta)  # lo que dejó un intento anterior de este video
            subcarpeta.mkdir(mode=0o700)
            subcarpeta.chmod(0o700)
        except OSError as e:
            _decir("no se pudo preparar la vista en vivo", e)
            subcarpeta = None
        return VistaDeVideo(
            subcarpeta,
            fps_origen=fps_origen,
            fps_vivo=self._fps,
            inicio_captura=inicio_captura,
            enmascarar=enmascarar,
        )
