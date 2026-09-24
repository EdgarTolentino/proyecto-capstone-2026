"""Videos: registro idempotente por hash y ciclo de estados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gepp_bd.modelos import ESTADOS_VIDEO, ORIGENES_CAPTURE_TS, Video


@dataclass(frozen=True, slots=True)
class NuevoVideo:
    fuente_id: int
    ruta: str
    hash_sha256: str
    bytes: int
    capture_ts_inicio: datetime
    origen_capture_ts: str
    duracion_s: float | None = None
    fps_declarado: float | None = None
    ancho: int | None = None
    alto: int | None = None

    def __post_init__(self) -> None:
        if self.capture_ts_inicio.tzinfo is None:
            raise ValueError("capture_ts_inicio debe llevar zona horaria (ver ADR-005)")
        if self.origen_capture_ts not in ORIGENES_CAPTURE_TS:
            raise ValueError(f"origen_capture_ts inválido: {self.origen_capture_ts!r}")
        if len(self.hash_sha256) != 64:
            raise ValueError("hash_sha256 debe tener 64 caracteres hexadecimales")


def registrar(sesion: Session, nuevo: NuevoVideo) -> tuple[Video, bool]:
    """Registra un video. Devuelve `(video, creado)`.

    Si el hash ya existe no inserta nada y devuelve la fila que ya estaba: copiar el mismo
    archivo dos veces a la carpeta vigilada no duplica ni el video ni sus detecciones.
    """
    sentencia = (
        insert(Video)
        .values(
            fuente_id=nuevo.fuente_id,
            ruta=nuevo.ruta,
            hash_sha256=nuevo.hash_sha256,
            bytes=nuevo.bytes,
            duracion_s=nuevo.duracion_s,
            fps_declarado=nuevo.fps_declarado,
            ancho=nuevo.ancho,
            alto=nuevo.alto,
            capture_ts_inicio=nuevo.capture_ts_inicio,
            origen_capture_ts=nuevo.origen_capture_ts,
        )
        .on_conflict_do_nothing(index_elements=["hash_sha256"])
        .returning(Video.id)
    )
    creado_id = sesion.execute(sentencia).scalar_one_or_none()
    video = sesion.execute(select(Video).where(Video.hash_sha256 == nuevo.hash_sha256)).scalar_one()
    return video, creado_id is not None


def por_hash(sesion: Session, hash_sha256: str) -> Video | None:
    return sesion.execute(
        select(Video).where(Video.hash_sha256 == hash_sha256)
    ).scalar_one_or_none()


def cambiar_estado(
    sesion: Session,
    video_id: int,
    estado: str,
    *,
    error_motivo: str | None = None,
    cuadros_analizados: int | None = None,
    proceso_ms: int | None = None,
) -> None:
    if estado not in ESTADOS_VIDEO:
        raise ValueError(f"estado de video inválido: {estado!r}")
    valores: dict[str, object] = {"estado": estado, "error_motivo": error_motivo}
    if cuadros_analizados is not None:
        valores["cuadros_analizados"] = cuadros_analizados
    if proceso_ms is not None:
        valores["proceso_ms"] = proceso_ms
    sesion.execute(update(Video).where(Video.id == video_id).values(**valores))


def completar_lectura(sesion: Session, video_id: int, leido: NuevoVideo) -> None:
    """Reemplaza los datos de respaldo de un video que un intento anterior no pudo leer."""
    sesion.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(
            duracion_s=leido.duracion_s,
            fps_declarado=leido.fps_declarado,
            ancho=leido.ancho,
            alto=leido.alto,
            capture_ts_inicio=leido.capture_ts_inicio,
            origen_capture_ts=leido.origen_capture_ts,
        )
    )


def anotar_fallo(sesion: Session, video_id: int, motivo: str, *, definitivo: bool) -> None:
    """Un intento fallido: `reintentando` si vuelve a la cola, `error` si ya no."""
    sesion.execute(
        update(Video)
        .where(Video.id == video_id)
        .values(
            estado="error" if definitivo else "reintentando",
            error_motivo=motivo,
            intentos=Video.intentos + 1,
        )
    )


def pedir_reintento(sesion: Session, video_id: int) -> bool:
    """Devuelve a la cola un video que falló, con los intentos en cero. El trabajador lo ve
    en `pedidos_de_reintento` y lo encola en Redis: la API no habla con Redis.

    Devuelve False si el video no estaba en `error` ni en `reintentando`.
    """
    fila = sesion.execute(
        update(Video)
        .where(Video.id == video_id, Video.estado.in_(("error", "reintentando")))
        .values(estado="en_cola", intentos=0, error_motivo=None)
        .returning(Video.id)
    ).scalar_one_or_none()
    return fila is not None


def pedidos_de_reintento(sesion: Session) -> list[Video]:
    """Los videos `en_cola` en la base. El trabajador encola los que Redis no tiene ya."""
    return list(
        sesion.execute(select(Video).where(Video.estado == "en_cola").order_by(Video.id)).scalars()
    )
