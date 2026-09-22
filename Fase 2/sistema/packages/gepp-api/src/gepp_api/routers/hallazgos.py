"""Bandeja de triage y visor de evidencia: el corazón del producto."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from gepp_bd.modelos import AccionCorrectiva, Evidencia, Hallazgo, Usuario
from gepp_bd.repositorios import auditoria
from sqlalchemy import func, update

from gepp_api.auth import Bd, Sesion, SesionActual
from gepp_api.errores import ErrorApi, no_encontrado, sin_permiso
from gepp_api.esquemas import AccionCorrectivaNueva, DecisionTriage, TriageLote
from gepp_api.servicios import hallazgos as servicio

router = APIRouter(tags=["Hallazgos"])

#: Desde estos estados se puede resolver. Lo demás ya lo resolvió alguien: 409.
RESOLUBLES = ("por_revisar", "pospuesto")


def _lista(texto: str | None) -> list[str]:
    return [p.strip() for p in texto.split(",") if p.strip()] if texto else []


@router.get("/hallazgos", operation_id="listarHallazgos")
def listar_hallazgos(
    request: Request,
    bd: Bd,
    sesion: Sesion,
    estado: str | None = None,
    severidad: str | None = None,
    area_id: int | None = None,
    zona_id: int | None = None,
    fuente_id: int | None = None,
    epp: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    turno: str | None = None,
    reincidente: bool | None = None,
    orden: str = "ts_inicio_desc",
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    sesion.exigir("ver_hallazgos")
    try:
        severidades = [int(s) for s in _lista(severidad)]
    except ValueError as e:
        raise ErrorApi(422, "peticion_invalida", "severidad debe ser 1, 2, 3 o 4") from e
    filtros = servicio.Filtros(
        estado=estado,
        severidad=severidades,
        area_id=area_id,
        zona_id=zona_id,
        fuente_id=fuente_id,
        epp=_lista(epp),
        desde=desde,
        hasta=hasta,
        turno=turno,
        reincidente=reincidente,
    )
    tz = request.app.state.config.zona_horaria
    return servicio.listar(bd, filtros, sesion, tz, orden=orden, limite=limite, cursor=cursor)


def _hallazgo_visible(bd: Bd, sesion: SesionActual, hallazgo_id: int) -> Hallazgo:
    h = bd.get(Hallazgo, hallazgo_id)
    if h is None:
        raise no_encontrado("hallazgo", hallazgo_id)
    if not sesion.puede_ver_area(h.area_id):
        raise sin_permiso("El hallazgo es de otra área")
    return h


@router.get("/hallazgos/{id}", operation_id="obtenerHallazgo")
def obtener_hallazgo(id: int, request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    sesion.exigir("ver_hallazgos")
    h = _hallazgo_visible(bd, sesion, id)
    return servicio.detalle(bd, h, sesion, request.app.state.config.zona_horaria)


@router.get("/evidencias/{id}", operation_id="obtenerEvidencia", response_class=FileResponse)
def obtener_evidencia(id: int, bd: Bd, sesion: Sesion) -> FileResponse:
    """El recorte ya anonimizado. No existe otra versión (ADR-006)."""
    sesion.exigir("ver_evidencia")
    e = bd.get(Evidencia, id)
    if e is None or not e.anonimizado:
        raise no_encontrado("evidencia", id)
    _hallazgo_visible(bd, sesion, e.hallazgo_id)
    ruta = Path(e.ruta)
    if not ruta.is_file():
        raise ErrorApi(404, "evidencia_purgada", f"La evidencia {id} ya no está en disco")
    return FileResponse(ruta, media_type="image/jpeg", headers={"Cache-Control": "private"})


def _resolver(bd: Bd, sesion: SesionActual, h: Hallazgo, decision: DecisionTriage) -> str | None:
    """Aplica la decisión. Devuelve el motivo si NO se pudo, para el triage en lote."""
    if h.estado not in RESOLUBLES:
        return "ya resuelto por otro usuario"
    if decision.estado == "falso_positivo" and not (decision.motivo or "").strip():
        raise ErrorApi(
            422,
            "motivo_obligatorio",
            "Un falso positivo exige motivo: alimenta el análisis de error",
        )
    # WHERE sobre el estado: si otro usuario resolvió entre la lectura y la escritura, no pisa.
    aplicado = bd.execute(
        update(Hallazgo)
        .where(Hallazgo.id == h.id, Hallazgo.estado.in_(RESOLUBLES))
        .values(estado=decision.estado, revisado_por=sesion.id, revisado_en=func.now())
        .returning(Hallazgo.id)
    ).scalar_one_or_none()
    if aplicado is None:
        return "ya resuelto por otro usuario"
    auditoria.registrar(
        bd,
        usuario_id=sesion.id,
        rol=sesion.rol,
        accion=f"triage:{decision.estado}",
        entidad="hallazgo",
        entidad_id=h.id,
        motivo=decision.motivo,
    )
    bd.refresh(h)
    return None


@router.post("/hallazgos/{id}/triage", operation_id="triarHallazgo")
def triar_hallazgo(
    id: int, decision: DecisionTriage, request: Request, bd: Bd, sesion: Sesion
) -> dict[str, Any]:
    sesion.exigir("triar_hallazgos")
    h = _hallazgo_visible(bd, sesion, id)
    motivo = _resolver(bd, sesion, h, decision)
    if motivo is not None:
        raise ErrorApi(409, "hallazgo_ya_resuelto", f"El hallazgo {id} está {h.estado}")
    tz = request.app.state.config.zona_horaria
    (salida,) = servicio.serializar(bd, [h], {}, tz)
    return salida


@router.post("/hallazgos/triage-lote", operation_id="triarLote")
def triar_lote(cuerpo: TriageLote, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    sesion.exigir("triar_hallazgos")
    aplicados, omitidos = 0, []
    for hallazgo_id in dict.fromkeys(cuerpo.ids):
        h = bd.get(Hallazgo, hallazgo_id)
        if h is None:
            omitidos.append({"id": hallazgo_id, "motivo": "no existe"})
            continue
        if not sesion.puede_ver_area(h.area_id):
            omitidos.append({"id": hallazgo_id, "motivo": "otra área"})
            continue
        motivo = _resolver(bd, sesion, h, cuerpo.decision)
        if motivo is None:
            aplicados += 1
        else:
            omitidos.append({"id": hallazgo_id, "motivo": motivo})
    return {"aplicados": aplicados, "omitidos": omitidos}


@router.post("/hallazgos/{id}/acciones", operation_id="crearAccionCorrectiva", status_code=201)
def crear_accion(
    id: int, accion: AccionCorrectivaNueva, request: Request, bd: Bd, sesion: Sesion
) -> dict[str, Any]:
    sesion.exigir("asignar_acciones")
    h = _hallazgo_visible(bd, sesion, id)
    responsable = bd.get(Usuario, accion.responsable_id)
    if responsable is None or not responsable.activo:
        raise ErrorApi(422, "responsable_invalido", "El responsable no existe o está inactivo")
    fila = AccionCorrectiva(
        hallazgo_id=h.id,
        responsable_id=responsable.id,
        descripcion=accion.descripcion,
        plazo=accion.plazo,
    )
    bd.add(fila)
    bd.flush()
    auditoria.registrar(
        bd,
        usuario_id=sesion.id,
        rol=sesion.rol,
        accion="accion:crear",
        entidad="accion_correctiva",
        entidad_id=fila.id,
    )
    bd.refresh(fila)
    return servicio.accion_a_json(fila, request.app.state.config.zona_horaria)


__all__ = ["router"]
