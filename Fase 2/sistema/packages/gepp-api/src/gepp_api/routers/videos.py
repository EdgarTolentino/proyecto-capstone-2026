"""Cola de ingesta y reprocesamiento sin GPU."""

from __future__ import annotations

from pathlib import PurePath
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from gepp_bd.modelos import Fuente, Hallazgo, Video
from gepp_bd.repositorios import auditoria, videos
from sqlalchemy import func, select

from gepp_api.auth import Bd, Sesion
from gepp_api.errores import ErrorApi, no_encontrado
from gepp_api.servicios.hallazgos import cursor_de, desplazamiento_de, iso
from gepp_api.servicios.recalculo import recalcular_video

router = APIRouter(tags=["Videos"])


def video_a_json(bd: Bd, v: Video, tz: ZoneInfo) -> dict[str, Any]:
    fuente = bd.get(Fuente, v.fuente_id)
    fps_objetivo = fuente.fps_objetivo if fuente else None
    fps_efectivo = (
        min(fps_objetivo, v.fps_declarado) if fps_objetivo and v.fps_declarado else fps_objetivo
    )
    salida = {
        "id": v.id,
        "archivo": PurePath(v.ruta).name,
        "hash_abreviado": v.hash_sha256[:8],
        "fuente": {"id": fuente.id, "nombre": fuente.nombre} if fuente else None,
        "duracion_s": v.duracion_s,
        "bytes": v.bytes,
        "ancho": v.ancho,
        "alto": v.alto,
        "capture_ts_inicio": iso(v.capture_ts_inicio, tz),
        "origen_capture_ts": v.origen_capture_ts,
        "estado": v.estado,
        # El trabajador no publica avance parcial todavía: solo se sabe que empezó o terminó.
        "progreso": 1.0 if v.estado == "listo" else None,
        "error_motivo": v.error_motivo,
        "intentos": v.intentos,
        "fps_efectivo": fps_efectivo,
        "cuadros_analizados": v.cuadros_analizados,
        "proceso_ms": v.proceso_ms,
        "hallazgos_generados": bd.scalar(select(func.count()).where(Hallazgo.video_id == v.id))
        or 0,
    }
    # En el contrato estos campos son opcionales pero NO admiten nulo: sin dato, se omiten.
    for campo in ("duracion_s", "ancho", "alto"):
        if salida[campo] is None:
            del salida[campo]
    return salida


@router.get("/videos", operation_id="listarVideos")
def listar_videos(
    request: Request,
    bd: Bd,
    sesion: Sesion,
    estado: str | None = None,
    fuente_id: int | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    sesion.exigir("ver_hallazgos")
    consulta = select(Video)
    if estado:
        consulta = consulta.where(Video.estado == estado)
    if fuente_id is not None:
        consulta = consulta.where(Video.fuente_id == fuente_id)
    desplazamiento = desplazamiento_de(cursor)
    filas = list(
        bd.execute(
            consulta.order_by(Video.creado_en.desc(), Video.id.desc())
            .offset(desplazamiento)
            .limit(limite + 1)
        ).scalars()
    )
    tz = request.app.state.config.zona_horaria
    return {
        "items": [video_a_json(bd, v, tz) for v in filas[:limite]],
        "siguiente_cursor": cursor_de(desplazamiento + limite) if len(filas) > limite else None,
    }


@router.post("/videos/{id}/reprocesar", operation_id="reprocesarVideo", status_code=202)
def reprocesar_video(id: int, request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    """Un video `listo` se recalcula con las reglas vigentes sobre las detecciones guardadas,
    sin GPU ni video. Uno que falló (`error` o `reintentando`) vuelve a la cola con los
    intentos en cero: el trabajador lo encola en su próxima vuelta (#74)."""
    sesion.exigir("editar_reglas")
    v = bd.get(Video, id)
    if v is None:
        raise no_encontrado("video", id)
    tz = request.app.state.config.zona_horaria
    if v.estado in ("error", "reintentando"):
        previo = f"estaba {v.estado}: {v.error_motivo}"
        if not videos.pedir_reintento(bd, v.id):
            # El trabajador lo tomó entre la lectura y el UPDATE: ya se está procesando.
            raise ErrorApi(409, "video_no_listo", f"El video {id} ya va a procesarse")
        auditoria.registrar(
            bd,
            usuario_id=sesion.id,
            rol=sesion.rol,
            accion="video:reintentar",
            entidad="video",
            entidad_id=v.id,
            motivo=previo,
        )
        bd.refresh(v)
        return video_a_json(bd, v, tz)
    if v.estado != "listo":
        raise ErrorApi(409, "video_no_listo", f"El video {id} está {v.estado}: ya va a procesarse")
    resultado = recalcular_video(bd, v)
    auditoria.registrar(
        bd,
        usuario_id=sesion.id,
        rol=sesion.rol,
        accion="video:reprocesar",
        entidad="video",
        entidad_id=v.id,
        motivo=(
            f"insertados={resultado.insertados} actualizados={resultado.actualizados} "
            f"eliminados={resultado.eliminados} conservados={resultado.conservados} "
            f"sin_gpu_ms={resultado.proceso_ms}"
        ),
    )
    return video_a_json(bd, v, tz)
