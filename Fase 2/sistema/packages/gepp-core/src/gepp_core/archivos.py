"""Nombres de archivo de video dentro de una carpeta de entrada.

Función pura sobre `Path`: sin red, sin base y sin Redis. La usan la API (al recibir el pedido)
y el trabajador (al tomarlo): se valida dos veces, con la misma regla.

Quien llama entrega un NOMBRE, nunca una ruta. Lo que impide salir de la carpeta es que el nombre
no puede llevar separadores ni empezar con punto, y que la entrada no sea un enlace simbólico.
"""

from __future__ import annotations

import stat
from pathlib import Path, PurePath

#: Lo que el vigilante y los pedidos aceptan como video.
EXTENSIONES_VIDEO = frozenset({".mp4", ".mov", ".mkv", ".avi"})

#: Límite de un componente de ruta en Linux (ext4), en BYTES y no en caracteres.
MAXIMO_NOMBRE_BYTES = 255


class ErrorArchivo(Exception):
    """Base de los errores de este módulo. Los mensajes nunca llevan rutas del servidor."""


class NombreInvalido(ErrorArchivo):
    """El nombre está mal formado, sin mirar el disco. La API responde 422."""


class ArchivoNoEncontrado(ErrorArchivo):
    """No hay un archivo de video utilizable con ese nombre en la carpeta. La API responde 404.

    Cubre: no existe, es un enlace simbólico, no es un archivo regular (directorio, FIFO…),
    está vacío (0 bytes) o la carpeta no existe ni se puede leer.
    """


def validar_nombre(nombre: str) -> None:
    """Reglas que no necesitan el disco. Lanza `NombreInvalido`."""
    try:
        en_bytes = nombre.encode("utf-8")
    except UnicodeEncodeError:
        raise NombreInvalido("el nombre del archivo no es texto válido") from None
    if len(en_bytes) > MAXIMO_NOMBRE_BYTES:
        raise NombreInvalido(f"el nombre del archivo supera {MAXIMO_NOMBRE_BYTES} bytes")
    if any(c in nombre for c in ("/", "\\", "\x00")):
        raise NombreInvalido("el nombre del archivo no puede llevar separadores de ruta")
    if nombre.startswith("."):
        raise NombreInvalido("el nombre del archivo no puede empezar con punto")
    if PurePath(nombre).suffix.lower() not in EXTENSIONES_VIDEO:
        raise NombreInvalido("la extensión del archivo no es de un video admitido")


def validar_nombre_en_carpeta(carpeta: Path, nombre: str) -> Path:
    """Devuelve `carpeta_resuelta / nombre` si es un archivo de video regular y no vacío.

    Con una sola `lstat` (que NO sigue enlaces) se decide el tipo y el tamaño, así que no hay
    ventana entre "es un enlace" y "es un archivo". No hace falta comprobar que el padre sea la
    carpeta: sin separadores ni punto inicial, `carpeta / nombre` no puede estar en otro lado.
    """
    validar_nombre(nombre)
    try:
        raiz = carpeta.resolve()
        ruta = raiz / nombre
        info = ruta.lstat()
    except (OSError, RuntimeError):  # ENOENT, EACCES, ENAMETOOLONG, ciclo de enlaces…
        raise ArchivoNoEncontrado("no hay un archivo con ese nombre en la carpeta") from None
    if not stat.S_ISREG(info.st_mode):  # enlace, directorio, FIFO, socket, dispositivo
        raise ArchivoNoEncontrado("no hay un archivo con ese nombre en la carpeta")
    if info.st_size == 0:
        raise ArchivoNoEncontrado("el archivo está vacío: espera a que termine de copiarse")
    return ruta
