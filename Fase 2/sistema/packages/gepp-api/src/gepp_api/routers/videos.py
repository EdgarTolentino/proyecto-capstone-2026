"""Cola de ingesta y reprocesamiento sin GPU."""

from __future__ import annotations

from pathlib import PurePath
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from gepp_bd.modelos import Fuente, Hallazgo, Video
from gepp_bd.repositorios import auditoria, videos
from gepp_core.textos import sin_rutas
from sqlalchemy import Select, func, select

from gepp_api.auth import Bd, Sesion, SesionActual
from gepp_api.errores import ErrorApi, no_encontrado
from gepp_api.esquemas import PedidoNuevo
from gepp_api.servicios import ingesta
from gepp_api.servicios.hallazgos import cursor_de, desplazamiento_de, iso
from gepp_api.servicios.recalculo import recalcular_video

router = APIRouter(tags=["Videos"])


def videos_de_su_area(consulta: Select[Any], sesion: SesionActual) -> Select[Any]:
    """El supervisor solo ve los videos de las cámaras de su área; los demás roles, todos.
    Igual que `hallazgos`: el área del video es la de su fuente."""
    if sesion.rol != "supervisor":
        return consulta
    return consulta.where(
        Video.fuente_id.in_(select(Fuente.id).where(Fuente.area_id == sesion.area_id))
    )


def _motivo_publico(v: Video) -> str | None:
    """`error_motivo` sin rutas del servidor; la API sí conoce la ruta de la fila."""
    return sin_rutas(v.error_motivo, v.ruta) if v.error_motivo else v.error_motivo


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
        # Filas escritas antes de que el trabajador sanease el motivo pueden traer rutas.
        "error_motivo": _motivo_publico(v),
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
    consulta = videos_de_su_area(select(Video), sesion)
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


@router.get("/videos/entrada", operation_id="listarEntradaVideos")
def listar_entrada_videos(request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    """Los videos de la carpeta de entrada que se pueden pedir. Solo nombres, nunca rutas."""
    sesion.exigir("editar_reglas")
    config = request.app.state.config
    carpeta = ingesta.carpeta_de_entrada(config.carpeta_entrada)
    return {"items": ingesta.listar_entrada(bd, carpeta, config.zona_horaria)}


@router.get("/videos/pedidos", operation_id="listarPedidos")
def listar_pedidos(request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    sesion.exigir("editar_reglas")
    return {"items": ingesta.listar_pedidos(bd, request.app.state.config.zona_horaria)}


@router.post("/videos", operation_id="pedirIngesta", status_code=202)
def pedir_ingesta(request: Request, cuerpo: PedidoNuevo, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    """Deja un pedido para que el trabajador procese un archivo de la carpeta de entrada.
    No sube nada ni habla con Redis; el hash y el registro del video son del trabajador."""
    sesion.exigir("editar_reglas")
    config = request.app.state.config
    carpeta = ingesta.carpeta_de_entrada(config.carpeta_entrada)
    return ingesta.pedir(bd, sesion, carpeta, cuerpo.archivo, cuerpo.fuente_id, config.zona_horaria)


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
        previo = f"estaba {v.estado}: {_motivo_publico(v)}"
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
