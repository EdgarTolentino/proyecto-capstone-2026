"""Atiende los pedidos de procesar un video desde la web (`pedido_ingesta`, ADR-012).

La API deja un pedido `pendiente` con el nombre del archivo y la cámara; este módulo, dentro del
trabajador, hace el resto, uno por vuelta del bucle:

1. Toma el pedido más antiguo (`tomado`) y vuelve a validar el nombre contra la carpeta de
   entrada: se valida dos veces, la API al recibirlo y aquí al tomarlo, porque entre una y otra
   el archivo puede haber cambiado.
2. Abre el archivo con `O_NOFOLLOW`, comprueba que el descriptor es el mismo archivo que vio la
   validación (inodo y dispositivo) y calcula el SHA-256 **leyendo del descriptor**. Mide tamaño
   y fecha de modificación antes y después: un archivo que se sigue copiando, o que alguien
   reemplazó mientras se leía, se rechaza en vez de registrar un hash que no es el suyo.
3. Si el hash ya tiene una fila `video` se rechaza («ya registrado como cámara X») y no se toca
   esa fila. Si no, crea el `video` con la ruta de entrada y la cámara del pedido, lo encola en
   Redis y cierra el pedido como `registrado`.

La base manda sobre Redis: si encolar falla después de crear la fila, el pedido igual queda
`registrado`, porque `Trabajador.reencolar_pedidos` encola todo `video` en `en_cola` que Redis no
tenga. Los motivos que se guardan (y que la API devuelve) nunca llevan rutas del servidor.

**Un solo trabajador atiende pedidos**: lo asegura un candado consultivo de PostgreSQL
(`pg_try_advisory_lock`) que vive mientras viva la conexión. Si otro proceso lo tiene, este no
atiende pedidos y lo dice; no muere. Quien tiene el candado recupera, al arrancar, los pedidos que
un trabajador anterior dejó `tomado`.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gepp_bd.modelos import Fuente
from gepp_bd.repositorios import pedidos, videos
from gepp_bd.sesion import transaccion
from gepp_core.archivos import ErrorArchivo, validar_nombre_en_carpeta
from gepp_core.textos import sin_rutas
from sqlalchemy import Connection, Engine, text

from gepp_worker.cola import ColaTrabajos, Trabajo
from gepp_worker.fuente_archivo import OrigenReloj, validar_ruta
from gepp_worker.vigilante import BLOQUE_HASH

#: Clave del candado consultivo: «GEPP» en ASCII y un 1. Cabe en un bigint de PostgreSQL.
CLAVE_CANDADO = 0x4745505001

CAMBIO = "el archivo cambió mientras se leía; vuelve a pedirlo cuando termine de copiarse"
REEMPLAZADO = "el archivo fue reemplazado o es un enlace; vuelve a pedirlo"


def variantes_de(ruta: str) -> tuple[str, ...]:
    """La ruta como vino y resuelta (los mensajes de `FuenteArchivo` traen la resuelta). Un
    enlace circular hace fallar a `resolve()` en Python 3.12 (`RuntimeError`): sin la resuelta
    se sanea igual con la regla general, pero el trabajador no puede caerse por esto."""
    try:
        return (ruta, str(Path(ruta).resolve()))
    except (OSError, RuntimeError):
        return (ruta,)


def validar_carpeta_entrada(entrada: str | Path, vigilada: str | Path) -> Path:
    """La carpeta de entrada de los pedidos, ya validada. Lanza `ValueError` si:

    - no existe o no es una carpeta;
    - está bajo `/mnt/` (los discos de Windows no son fiables en WSL2: `validar_ruta`);
    - es la misma que la vigilada o está dentro de ella (o ella dentro de esta): el vigilante
      y los pedidos encolarían el mismo archivo por dos caminos.

    Se comparan las rutas resueltas.
    """
    carpeta = validar_ruta(Path(entrada))
    if not carpeta.is_dir():
        raise ValueError(f"GEPP_CARPETA_ENTRADA no es una carpeta que exista: {carpeta}")
    otra = Path(vigilada).expanduser().resolve()
    if carpeta.is_relative_to(otra) or otra.is_relative_to(carpeta):  # incluye ser la misma
        raise ValueError(
            f"GEPP_CARPETA_ENTRADA ({carpeta}) no puede ser ni estar dentro de "
            f"GEPP_CARPETA_VIGILADA ({otra}), ni al revés"
        )
    return carpeta


@dataclass(frozen=True, slots=True)
class _Medida:
    """Lo que se ve del archivo en un instante."""

    bytes: int
    mtime_ns: int


class _Rechazo(Exception):
    """El pedido no se puede registrar. El mensaje es el motivo que verá quien lo pidió."""

    def __init__(self, motivo: str, medida: _Medida | None = None) -> None:
        super().__init__(motivo)
        self.medida = medida


def _hash_del_descriptor(fd: int) -> str:
    """SHA-256 por bloques, leyendo del descriptor ya abierto: es el mismo archivo que se midió."""
    h = hashlib.sha256()
    while trozo := os.read(fd, BLOQUE_HASH):
        h.update(trozo)
    return h.hexdigest()


class AtencionDePedidos:
    """Un trabajador con el candado atiende los pedidos de una carpeta de entrada."""

    def __init__(self, motor: Engine, cola: ColaTrabajos, carpeta: Path) -> None:
        self._motor = motor
        self._cola = cola
        self._carpeta = carpeta
        self._conexion: Connection | None = None

    @property
    def activa(self) -> bool:
        return self._conexion is not None

    def iniciar(self) -> bool:
        """Toma el candado y recupera lo que un trabajador anterior dejó `tomado`.

        Devuelve False (sin lanzar) si otro proceso ya atiende pedidos."""
        conexion = self._motor.connect()
        libre = conexion.execute(
            text("SELECT pg_try_advisory_lock(:clave)"), {"clave": CLAVE_CANDADO}
        ).scalar_one()
        conexion.commit()
        if not libre:
            conexion.close()
            print("[trabajador] otro proceso atiende los pedidos: este no los atiende", flush=True)
            return False
        self._conexion = conexion  # el candado vive con esta conexión: no se devuelve al pool
        with transaccion(self._motor) as s:
            recuperados = pedidos.recuperar_tomados(s)
        if recuperados:
            print(f"[trabajador] {recuperados} pedido(s) volvieron a pendiente", flush=True)
        return True

    def cerrar(self) -> None:
        if self._conexion is None:
            return
        try:
            self._conexion.execute(
                text("SELECT pg_advisory_unlock(:clave)"), {"clave": CLAVE_CANDADO}
            )
            self._conexion.commit()
        finally:
            self._conexion.close()
            self._conexion = None

    def atender_uno(self) -> bool:
        """Atiende el pedido más antiguo. Devuelve False si no había ninguno."""
        with transaccion(self._motor) as s:
            pedido = pedidos.tomar_siguiente(s)
            if pedido is None:
                return False
            pedido_id, archivo, fuente_id = pedido.id, pedido.archivo, pedido.fuente_id
        medida: _Medida | None = None
        try:
            video_id, medida = self._registrar(archivo, fuente_id)
        except _Rechazo as r:
            self._cerrar_rechazado(pedido_id, str(r), r.medida)
            return True
        except Exception as e:
            rutas = (*variantes_de(str(self._carpeta / archivo)), *variantes_de(str(self._carpeta)))
            motivo = sin_rutas(f"{type(e).__name__}: {e}", *rutas)
            print(f"[trabajador] pedido {pedido_id}: {type(e).__name__}: {e}", file=sys.stderr)
            self._cerrar_rechazado(pedido_id, motivo, medida)
            return True
        with transaccion(self._motor) as s:
            pedidos.registrar(s, pedido_id, video_id, bytes=medida.bytes, mtime_ns=medida.mtime_ns)
        return True

    def _cerrar_rechazado(self, pedido_id: int, motivo: str, medida: _Medida | None) -> None:
        with transaccion(self._motor) as s:
            pedidos.rechazar(
                s,
                pedido_id,
                motivo,
                bytes=medida.bytes if medida else None,
                mtime_ns=medida.mtime_ns if medida else None,
            )

    def _registrar(self, archivo: str, fuente_id: int) -> tuple[int, _Medida]:
        """Valida, mide y hashea el archivo y crea (o reconoce) su fila `video`. Devuelve el
        `video_id` y lo medido. Lanza `_Rechazo` si el pedido no puede registrarse."""
        try:
            ruta = validar_nombre_en_carpeta(self._carpeta, archivo)
        except ErrorArchivo as e:
            raise _Rechazo(str(e)) from None
        hash_sha256, medida = self._hash_estable(ruta)

        with transaccion(self._motor) as s:
            existente = videos.por_hash(s, hash_sha256)
            if existente is not None:
                # Un pedido que se cayó a medias vuelve a `pendiente` y encuentra su propia
                # fila: misma ruta, misma cámara y todavía en cola. Es el mismo pedido.
                if (
                    existente.ruta == str(ruta)
                    and existente.fuente_id == fuente_id
                    and existente.estado == "en_cola"
                ):
                    return existente.id, medida
                camara = s.get(Fuente, existente.fuente_id)
                nombre = camara.nombre if camara else f"{existente.fuente_id}"
                raise _Rechazo(f"ya registrado como cámara {nombre}", medida)
            if s.get(Fuente, fuente_id) is None:
                raise _Rechazo("la cámara del pedido ya no existe", medida)
            video, creado = videos.registrar(
                s,
                videos.NuevoVideo(
                    fuente_id=fuente_id,
                    ruta=str(ruta),
                    hash_sha256=hash_sha256,
                    bytes=medida.bytes,
                    capture_ts_inicio=datetime.fromtimestamp(medida.mtime_ns / 1e9, tz=UTC),
                    origen_capture_ts=OrigenReloj.MTIME.value,
                ),
            )
            if not creado:  # otro camino la creó entre la consulta y la inserción
                raise _Rechazo("ya registrado por otra vía", medida)
            video_id = video.id
        try:
            self._cola.encolar(Trabajo(str(ruta), hash_sha256, medida.bytes, fuente_id))
        except Exception as e:
            # La base manda: `reencolar_pedidos` encola todo `en_cola` que Redis no tenga.
            aviso = f"no se pudo encolar ahora ({type(e).__name__}): {e}"
            print(f"[trabajador] {aviso}", file=sys.stderr)
        return video_id, medida

    def _hash_estable(self, ruta: Path) -> tuple[str, _Medida]:
        """El hash del archivo, solo si no cambió mientras se leía."""
        try:
            visto = ruta.lstat()  # la misma que usó la validación: no sigue enlaces
        except OSError:
            raise _Rechazo("no hay un archivo con ese nombre en la carpeta") from None
        try:
            fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as e:
            if e.errno == errno.ELOOP:  # se volvió un enlace después de validarlo
                raise _Rechazo(REEMPLAZADO) from None
            raise _Rechazo(f"no se pudo abrir el archivo: {e.strerror}") from None
        try:
            abierto = os.fstat(fd)
            if (abierto.st_ino, abierto.st_dev) != (visto.st_ino, visto.st_dev) or not stat.S_ISREG(
                abierto.st_mode
            ):
                raise _Rechazo(REEMPLAZADO)
            antes = _Medida(abierto.st_size, abierto.st_mtime_ns)
            digest = _hash_del_descriptor(fd)
            try:
                en_la_carpeta = ruta.lstat()  # ¿sigue siendo este archivo con este nombre?
            except OSError:
                raise _Rechazo(CAMBIO, antes) from None
        finally:
            os.close(fd)
        en_el_nombre = (en_la_carpeta.st_ino, en_la_carpeta.st_dev)
        if en_el_nombre != (abierto.st_ino, abierto.st_dev):
            raise _Rechazo(CAMBIO, antes)  # el nombre ya apunta a otro archivo
        # Mismo inodo que el descriptor: si el tamaño o la fecha cambiaron, lo escribieron mientras
        # se leía. (Sin un `fstat` aparte: sobre el mismo inodo daría lo mismo.)
        if (en_la_carpeta.st_size, en_la_carpeta.st_mtime_ns) != (antes.bytes, antes.mtime_ns):
            raise _Rechazo(CAMBIO, antes)
        return digest, antes
