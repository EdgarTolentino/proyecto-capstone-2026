"""`FuenteArchivo`: la implementación v1 del puerto `FuenteDeCuadros` (ADR-005).

Es el ÚNICO lugar del sistema donde nace el reloj. `inicio_captura` se deriva, en este
orden, de:

1. un valor inyectado a mano (`origen_reloj = "manual"`), para corregir un video mal fechado;
2. los metadatos del contenedor (`creation_time` según `ffprobe`) → `"metadatos"`;
3. la fecha de modificación del archivo menos su duración → `"mtime"`.

Si el archivo ni siquiera se puede abrir, no hay duración que restar: `reloj_de_respaldo` da
solo su fecha de modificación (el fin de la grabación), también como `"mtime"`.

Nunca de la hora en que se procesa. Los valores de `origen_reloj` son los mismos que admite
la columna `video.origen_capture_ts` (ver `docs/arquitectura/01-modelo-de-datos.md`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np

from gepp_worker.fuente import Cuadro, PropiedadesFuente, instante_de_captura

#: Un `creation_time` anterior a esta fecha es el valor por defecto de un equipo sin
#: reloj configurado (típicamente 1970 o 1904), no una fecha real.
FECHA_MINIMA_CREIBLE = datetime(2000, 1, 1, tzinfo=UTC)


class OrigenReloj(StrEnum):
    """De dónde salió `inicio_captura`. Coincide con el CHECK de `video.origen_capture_ts`."""

    METADATOS = "metadatos"
    MTIME = "mtime"
    MANUAL = "manual"
    OCR = "ocr"  # v2: lectura de la marca de tiempo impresa en el cuadro


@dataclass(frozen=True, slots=True)
class MetadatosContenedor:
    """Lo que interesa del contenedor, según `ffprobe`. Cualquier campo puede faltar."""

    duracion_s: float | None = None
    creation_time: datetime | None = None


def validar_ruta(ruta: Path) -> Path:
    """Rechaza rutas bajo `/mnt/`.

    En WSL2, `/mnt/c/...` es el disco de Windows montado por 9P: inotify no entrega eventos
    y la lectura es lenta. El sistema falla en silencio en lugar de fallar fuerte, así que se
    corta aquí, en la entrada.
    """
    absoluta = ruta.expanduser().resolve()
    if len(absoluta.parts) > 1 and absoluta.parts[1] == "mnt":
        raise ValueError(
            f"ruta bajo /mnt/ rechazada: {absoluta}. En WSL2 los discos de Windows no son "
            "fiables para la ingesta; copia el video al sistema de archivos de Linux."
        )
    return absoluta


def parsear_ffprobe(salida_json: str) -> MetadatosContenedor:
    """Interpreta la salida de `ffprobe -print_format json -show_format`."""
    formato = json.loads(salida_json).get("format", {})
    duracion: float | None = None
    if (valor := formato.get("duration")) is not None:
        try:
            duracion = float(valor)
        except ValueError:
            duracion = None

    creado: datetime | None = None
    if texto := formato.get("tags", {}).get("creation_time"):
        try:
            creado = datetime.fromisoformat(texto)
        except ValueError:
            creado = None
        if creado is not None:
            # La convención de MP4/QuickTime es UTC aunque la marca no lo declare.
            if creado.tzinfo is None:
                creado = creado.replace(tzinfo=UTC)
            if creado < FECHA_MINIMA_CREIBLE:
                creado = None
    return MetadatosContenedor(duracion_s=duracion, creation_time=creado)


def leer_metadatos(ruta: Path, ffprobe: str = "ffprobe") -> MetadatosContenedor:
    """Consulta `ffprobe`. Si no está instalado o falla, devuelve metadatos vacíos."""
    ejecutable = shutil.which(ffprobe)
    if ejecutable is None:
        return MetadatosContenedor()
    resultado = subprocess.run(
        [ejecutable, "-v", "quiet", "-print_format", "json", "-show_format", str(ruta)],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        return MetadatosContenedor()
    return parsear_ffprobe(resultado.stdout)


def resolver_inicio_captura(
    ruta: Path,
    metadatos: MetadatosContenedor,
    duracion_s: float,
    manual: datetime | None = None,
) -> tuple[datetime, OrigenReloj]:
    """Decide el origen del reloj del video. Devuelve el instante en UTC y su origen."""
    if manual is not None:
        if manual.tzinfo is None:
            raise ValueError("inicio_captura manual debe llevar zona horaria (ver ADR-005)")
        return manual.astimezone(UTC), OrigenReloj.MANUAL
    if metadatos.creation_time is not None:
        return metadatos.creation_time.astimezone(UTC), OrigenReloj.METADATOS
    fin, origen = reloj_de_respaldo(ruta)
    return fin - timedelta(seconds=duracion_s), origen


def reloj_de_respaldo(ruta: Path) -> tuple[datetime, OrigenReloj]:
    """El mtime, que marca el FIN de la grabación: la cámara cierra el archivo al terminar.

    Solo, sin restarle la duración, es el reloj de un archivo que no se pudo leer (#29).
    """
    return datetime.fromtimestamp(ruta.stat().st_mtime, tz=UTC), OrigenReloj.MTIME


class FuenteArchivo:
    """Lee un video de disco cuadro a cuadro. Implementa `FuenteDeCuadros`.

    `tomar()` avanza sin decodificar (`grab`); `recuperar()` decodifica el último tomado
    (`retrieve`). Esa separación es la que permite al muestreador saltarse cuadros sin
    pagar su decodificación.
    """

    def __init__(
        self,
        ruta: Path | str,
        *,
        inicio_captura: datetime | None = None,
        ffprobe: str = "ffprobe",
    ) -> None:
        self._ruta = validar_ruta(Path(ruta))
        self._inicio_manual = inicio_captura
        self._ffprobe = ffprobe
        self._captura: cv2.VideoCapture | None = None
        self._props: PropiedadesFuente | None = None
        self._indice = -1
        self._tomado = False

    @property
    def ruta(self) -> Path:
        return self._ruta

    def abrir(self) -> None:
        if not self._ruta.is_file():
            raise FileNotFoundError(f"no existe el video: {self._ruta}")
        captura = cv2.VideoCapture(str(self._ruta))
        if not captura.isOpened():
            raise ValueError(f"OpenCV no pudo abrir el video: {self._ruta}")
        fps = float(captura.get(cv2.CAP_PROP_FPS))
        if fps <= 0:
            captura.release()
            raise ValueError(f"el video no declara fps válidos ({fps}): {self._ruta}")
        total = int(captura.get(cv2.CAP_PROP_FRAME_COUNT))
        metadatos = leer_metadatos(self._ruta, self._ffprobe)
        duracion = metadatos.duracion_s if metadatos.duracion_s else max(total, 0) / fps
        inicio, origen = resolver_inicio_captura(
            self._ruta, metadatos, duracion, self._inicio_manual
        )
        self._props = PropiedadesFuente(
            es_archivo=True,
            fps=fps,
            ancho=int(captura.get(cv2.CAP_PROP_FRAME_WIDTH)),
            alto=int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            cuadros_totales=total if total > 0 else None,
            inicio_captura=inicio,
            origen_reloj=origen.value,
            reconectable=False,
        )
        self._captura = captura
        self._indice = -1
        self._tomado = False

    def tomar(self) -> bool:
        if self._captura is None:
            raise RuntimeError("la fuente no está abierta: llama a abrir() primero")
        self._tomado = bool(self._captura.grab())
        if self._tomado:
            self._indice += 1
        return self._tomado

    def recuperar(self) -> Cuadro | None:
        if self._captura is None or self._props is None or not self._tomado:
            return None
        ok, imagen = self._captura.retrieve()
        if not ok or imagen is None:
            return None
        return Cuadro(
            indice=self._indice,
            capture_ts=instante_de_captura(self._props, self._indice),
            imagen=np.asarray(imagen),
        )

    def cerrar(self) -> None:
        if self._captura is not None:
            self._captura.release()
        self._captura = None
        self._tomado = False

    def propiedades(self) -> PropiedadesFuente:
        if self._props is None:
            raise RuntimeError("la fuente no está abierta: llama a abrir() primero")
        return self._props
