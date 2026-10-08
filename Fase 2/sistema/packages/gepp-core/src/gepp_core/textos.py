"""Texto que sale del servidor hacia una persona: sin rutas del disco.

Python puro, sin tocar el sistema de archivos (ADR-007): la usan el trabajador, que escribe el
motivo de un fallo en la base, y la API, que lo devuelve al navegador.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

#: Lo que no puede ir pegado antes de una ruta para que sea una ruta aparte y no un pedazo de otra
#: cosa: una letra o cifra (`8000/datos/...` en una URL), un punto o una barra (`http://host/x`,
#: `./x`). Un `:` sí puede precederla (`modelo:/srv/epp.onnx`): el `//` de una URL ya queda
#: protegido por la barra.
_ANTES = r"(?<![\w./])"

#: Una ruta absoluta de Linux, terminada en su último componente, que es lo único que se conserva.
_RUTA_ABSOLUTA = re.compile(_ANTES + r"/(?:[^\s'\"<>|:,;()\[\]{}/]+/)*([^\s'\"<>|:,;()\[\]{}/]+)")


def sin_rutas(texto: str, *rutas: str) -> str:
    """El texto con solo nombres de archivo, nunca rutas del servidor.

    Lo que se guarda en `video.error_motivo` lo devuelve `GET /videos` al navegador: una ruta
    absoluta ahí cuenta cómo está armado el disco del servidor. Primero se sustituye cada ruta
    conocida (`rutas`) por su nombre, de la más larga a la más corta: son las únicas que pueden
    llevar espacios, y las que salen en casi todos los mensajes (`FuenteArchivo`, OpenCV,
    `stat`). Solo se sustituye si está aparte (no pegada a lo anterior ni a lo que sigue), para
    no corromper una URL que la contenga. Después, cualquier otra ruta absoluta que se haya
    colado, por su último componente. Las URL (`http://host/...`) no se tocan.

    Quien llama pasa las variantes que conoce de la ruta (la del trabajo y su versión
    resuelta); esta función no toca el disco y nunca lanza.
    """
    for ruta in sorted({r for r in rutas if r}, key=len, reverse=True):
        nombre = PurePosixPath(ruta).name
        patron = _ANTES + re.escape(ruta) + r"(?!\w)"
        texto = re.sub(patron, nombre.replace("\\", "\\\\"), texto)
    return _RUTA_ABSOLUTA.sub(r"\1", texto)
