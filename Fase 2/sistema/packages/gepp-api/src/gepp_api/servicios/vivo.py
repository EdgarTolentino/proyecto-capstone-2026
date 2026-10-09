"""El anillo de cuadros de la vista en vivo: lo que el trabajador deja en `<carpeta>/<video_id>/`.

Cada cuadro es un JPEG nítido, sin tapar rostros y con las cajas del detector, de nombre
`<seq:08d>_<pos_ms:09d>.jpg`. El trabajador escribe de forma atómica (temporales ocultos con
`.`), poda los más viejos y borra la subcarpeta al terminar; aquí solo se LEE, sin tocar nada y
sin devolver rutas.

Cada archivo se abre una vez (`O_NOFOLLOW`, `O_NONBLOCK`) y la edad y el contenido salen de ese
mismo descriptor, así que el trabajador no puede cambiarlo entre la comprobación y la lectura
(H10). Un archivo que el anillo podó entre el listado y la lectura se salta: no es un error.
"""

from __future__ import annotations

import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path

#: Un cuadro más viejo que esto ya no es «en vivo»: el trabajador se detuvo o el video terminó.
VIGENCIA_S = 10.0
#: Un JPEG de un cuadro pesa kilobytes; algo mayor no es lo que el trabajador escribe.
MAXIMO_BYTES = 8 * 1024 * 1024
#: Con más nuevos que esto se entregan los más recientes: la web prefiere saltar a quedarse atrás.
MAXIMO_POR_RESPUESTA = 30

#: `re.ASCII`: sin él, `\d` aceptaría dígitos de otros alfabetos. Se usa con `fullmatch`.
_NOMBRE = re.compile(r"(\d{8})_(\d{9})\.jpg", re.ASCII)

_BANDERAS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


@dataclass(frozen=True, slots=True)
class Cuadro:
    seq: int
    pos_ms: int
    jpeg: bytes


def _leer(dfd: int, nombre: str) -> tuple[bytes, float] | None:
    """Los bytes y la fecha de modificación (del mismo descriptor), o `None` si no se puede."""
    try:
        fd = os.open(nombre, _BANDERAS, dir_fd=dfd)
    except OSError:
        return None
    try:
        estado = os.fstat(fd)
        # Una tubería, un dispositivo o una carpeta con nombre de cuadro no es un cuadro, aunque
        # tenga bytes y una fecha reciente.
        if not stat.S_ISREG(estado.st_mode):
            return None
        mtime = estado.st_mtime
        datos = os.read(fd, MAXIMO_BYTES + 1)
    except OSError:
        return None
    finally:
        os.close(fd)
    if not datos or len(datos) > MAXIMO_BYTES:
        return None
    return datos, mtime


def _nombres(dfd: int) -> list[tuple[int, int, str]]:
    """`(seq, pos_ms, nombre)` de las entradas con el nombre EXACTO, de viejo a nuevo. Que sean
    archivos regulares (y no enlaces, tuberías o carpetas) lo decide `_leer` al abrir y leer."""
    salida = []
    with os.scandir(dfd) as it:
        for e in it:
            m = _NOMBRE.fullmatch(e.name)
            # `seq` arranca en 1 (contrato: `ultimo_seq >= 1`): el 0 es un nombre inválido.
            if m is not None and int(m[1]) >= 1:
                salida.append((int(m[1]), int(m[2]), e.name))
    salida.sort()
    return salida


def _vigente(fecha: float) -> bool:
    """Un cuadro de más de `VIGENCIA_S` no se sirve; `abs` cubre relojes desfasados (H11)."""
    return abs(time.time() - fecha) <= VIGENCIA_S


def cuadros_desde(
    carpeta: Path, video_id: int, desde: int = 0, maximo: int = MAXIMO_POR_RESPUESTA
) -> tuple[list[Cuadro], int] | None:
    """Los cuadros con `seq > desde` (los `maximo` más nuevos, de viejo a nuevo) y el `seq` del
    más reciente. `None` si no hay anillo, está vacío o su cuadro más reciente no es vigente."""
    # `O_NOFOLLOW` solo protege el último componente de cada apertura: por eso la raíz y la
    # subcarpeta se abren por separado, y ninguna de las dos puede ser un enlace.
    banderas = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        raiz = os.open(carpeta, banderas)
    except OSError:
        return None
    try:
        dfd = os.open(str(video_id), banderas, dir_fd=raiz)
    except OSError:
        return None
    finally:
        os.close(raiz)
    try:
        try:
            nombres = _nombres(dfd)
        except OSError:
            return None
        # El más nuevo que todavía se pueda leer fija la vigencia: los demás son más viejos.
        nuevo: tuple[int, int, bytes, float] | None = None
        for seq, pos, nombre in reversed(nombres):
            leido = _leer(dfd, nombre)
            if leido is not None:
                nuevo = (seq, pos, leido[0], leido[1])
                break
        if nuevo is None or not _vigente(nuevo[3]):  # H11
            return None
        elegidos = [n for n in nombres if n[0] > desde][-maximo:]
        cuadros = []
        for seq, pos, nombre in elegidos:
            if seq == nuevo[0]:
                cuadros.append(Cuadro(seq, pos, nuevo[2]))
            elif (leido := _leer(dfd, nombre)) is not None and _vigente(leido[1]):
                cuadros.append(Cuadro(seq, pos, leido[0]))
        return cuadros, nuevo[0]
    finally:
        os.close(dfd)


def ultimo_cuadro(carpeta: Path, video_id: int) -> bytes | None:
    """Los bytes del cuadro más reciente y vigente, o `None`."""
    visto = cuadros_desde(carpeta, video_id, desde=0, maximo=1)
    if visto is None or not visto[0]:
        return None
    return visto[0][-1].jpeg
