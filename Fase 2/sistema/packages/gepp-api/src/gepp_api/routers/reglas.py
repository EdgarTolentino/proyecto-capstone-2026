"""Editor de reglas y simulador "¿y si...?".

Editar NO modifica la versión vigente: crea la siguiente y desactiva la anterior. Los
hallazgos viejos siguen apuntando a la versión con que se dispararon.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from gepp_bd.modelos import Area, Fuente, Hallazgo, Regla, Video
from gepp_bd.repositorios import auditoria, reglas
from gepp_core import Regla as ReglaDominio
from gepp_core import Severidad, TipoEPP
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gepp_api.auth import Bd, Sesion
from gepp_api.errores import ErrorApi, no_encontrado
from gepp_api.esquemas import ReglaEntrada, Simulacion
from gepp_api.servicios.hallazgos import iso
from gepp_api.servicios.recalculo import evaluar

router = APIRouter(tags=["Reglas"])


def _hora(texto: str | None) -> time | None:
    if not texto:
        return None
    try:
        return time.fromisoformat(texto)
    except ValueError as e:
        raise ErrorApi(422, "hora_invalida", f"Hora inválida: {texto!r} (formato HH:MM)") from e


def _zona(entrada: ReglaEntrada) -> int | None:
    if len(entrada.zona_ids) > 1:
        # El esquema guarda una zona por regla. Varias zonas = varias reglas.
        raise ErrorApi(422, "una_zona_por_regla", "La v1 admite una sola zona por regla")
    return entrada.zona_ids[0] if entrada.zona_ids else None


def regla_a_json(bd: Session, r: Regla, tz: ZoneInfo) -> dict[str, Any]:
    ahora = bd.execute(select(func.now())).scalar_one()
    # Hallazgos de TODAS las versiones de la regla: la pregunta es cuánto dispara esta regla.
    versiones = select(Regla.id).where(Regla.area_id == r.area_id, Regla.nombre == r.nombre)
    ultimos_30d = select(func.count()).where(
        Hallazgo.regla_id.in_(versiones), Hallazgo.ts_inicio >= ahora - timedelta(days=30)
    )
    return {
        "id": r.id,
        "version": r.version,
        "nombre": r.nombre,
        "area_id": r.area_id,
        "zona_ids": [r.zona_id] if r.zona_id else [],
        "epp_exigido": sorted(r.epp_exigido),
        "confirmacion_segundos": r.confirmacion_segundos,
        "cierre_segundos": r.cierre_segundos,
        "confianza_minima": round(r.confianza_minima, 2),
        "severidad": r.severidad,
        "turno": r.turno,
        "hora_desde": r.hora_desde.strftime("%H:%M") if r.hora_desde else None,
        "hora_hasta": r.hora_hasta.strftime("%H:%M") if r.hora_hasta else None,
        "activa": r.activa,
        "base_licitud": r.base_licitud,
        "norma_fundante": r.norma_fundante,
        "finalidad_declarada": r.finalidad_declarada,
        "retencion_dias": r.retencion_dias,
        # Sin columnas todavía: llegan con las alertas (PT-13).
        "destinatarios": [],
        # La tabla `zona x EPP x evaluable` de V2 (#3) aún no existe: todo se declara evaluable.
        "evaluable": True,
        "hallazgos_30d": bd.scalar(ultimos_30d) or 0,
        "creada_en": iso(r.creada_en, tz),
    }


def _definicion(entrada: ReglaEntrada, sesion_id: int) -> reglas.DefinicionRegla:
    return reglas.DefinicionRegla(
        area_id=entrada.area_id,
        nombre=entrada.nombre,
        epp_exigido=frozenset(TipoEPP(e) for e in entrada.epp_exigido),
        severidad=Severidad(entrada.severidad),
        base_licitud=entrada.base_licitud,
        finalidad_declarada=entrada.finalidad_declarada,
        norma_fundante=entrada.norma_fundante,
        zona_id=_zona(entrada),
        confirmacion_segundos=entrada.confirmacion_segundos,
        cierre_segundos=entrada.cierre_segundos,
        confianza_minima=entrada.confianza_minima,
        turno=entrada.turno,
        hora_desde=_hora(entrada.hora_desde),
        hora_hasta=_hora(entrada.hora_hasta),
        retencion_dias=entrada.retencion_dias,
        creada_por=sesion_id,
    )


@router.get("/reglas", operation_id="listarReglas")
def listar_reglas(
    request: Request, bd: Bd, sesion: Sesion, area_id: int | None = None, activa: bool | None = None
) -> list[dict[str, Any]]:
    sesion.exigir("ver_hallazgos")
    consulta = select(Regla)
    if area_id is not None:
        consulta = consulta.where(Regla.area_id == area_id)
    if activa is not None:
        consulta = consulta.where(Regla.activa.is_(activa))
    tz = request.app.state.config.zona_horaria
    return [
        regla_a_json(bd, r, tz)
        for r in bd.execute(consulta.order_by(Regla.area_id, Regla.nombre, Regla.version)).scalars()
    ]


@router.post("/reglas", operation_id="crearRegla", status_code=201)
def crear_regla(entrada: ReglaEntrada, request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    sesion.exigir("editar_reglas")
    if bd.get(Area, entrada.area_id) is None:
        raise ErrorApi(422, "area_invalida", f"No existe el área {entrada.area_id}")
    try:
        with bd.begin_nested():
            fila = reglas.crear(bd, _definicion(entrada, sesion.id))
    except IntegrityError as e:
        raise ErrorApi(
            409, "regla_existente", "Ya existe una regla con ese nombre en el área: edítala"
        ) from e
    fila.activa = entrada.activa
    auditoria.registrar(
        bd,
        usuario_id=sesion.id,
        rol=sesion.rol,
        accion="regla:crear",
        entidad="regla",
        entidad_id=fila.id,
    )
    bd.flush()
    bd.refresh(fila)
    return regla_a_json(bd, fila, request.app.state.config.zona_horaria)


def _regla(bd: Bd, id: int) -> Regla:
    r = bd.get(Regla, id)
    if r is None:
        raise no_encontrado("regla", id)
    return r


@router.get("/reglas/{id}", operation_id="obtenerRegla")
def obtener_regla(id: int, request: Request, bd: Bd, sesion: Sesion) -> dict[str, Any]:
    sesion.exigir("ver_hallazgos")
    return regla_a_json(bd, _regla(bd, id), request.app.state.config.zona_horaria)


@router.put("/reglas/{id}", operation_id="actualizarRegla")
def actualizar_regla(
    id: int, entrada: ReglaEntrada, request: Request, bd: Bd, sesion: Sesion
) -> dict[str, Any]:
    sesion.exigir("editar_reglas")
    actual = _regla(bd, id)
    if (entrada.nombre, entrada.area_id) != (actual.nombre, actual.area_id):
        raise ErrorApi(
            422, "identidad_de_regla", "Nombre y área identifican a la regla: crea una regla nueva"
        )
    defn = _definicion(entrada, sesion.id)
    cambios = {
        campo: getattr(defn, campo)
        for campo in reglas.DefinicionRegla.__dataclass_fields__
        if campo not in ("nombre", "area_id")
    }
    try:
        nueva = reglas.nueva_version(bd, id, **cambios)
    except ValueError as e:
        raise ErrorApi(409, "regla_reemplazada", str(e)) from e
    nueva.activa = entrada.activa
    auditoria.registrar(
        bd,
        usuario_id=sesion.id,
        rol=sesion.rol,
        accion="regla:versionar",
        entidad="regla",
        entidad_id=nueva.id,
        motivo=f"v{actual.version} -> v{nueva.version}",
    )
    bd.flush()
    bd.refresh(nueva)
    return regla_a_json(bd, nueva, request.app.state.config.zona_horaria)


@router.post("/reglas/{id}/simular", operation_id="simularRegla")
def simular_regla(
    id: int, cuerpo: Simulacion, request: Request, bd: Bd, sesion: Sesion
) -> dict[str, Any]:
    """Sobre las detecciones YA guardadas: sin GPU y sin volver a leer video."""
    sesion.exigir("editar_reglas")
    vigente = _regla(bd, id)
    if cuerpo.hasta < cuerpo.desde:
        raise ErrorApi(422, "rango_invalido", "hasta debe ser posterior a desde")
    tz: ZoneInfo = request.app.state.config.zona_horaria
    desde = datetime.combine(cuerpo.desde, time(), tz)
    hasta = datetime.combine(cuerpo.hasta + timedelta(days=1), time(), tz)
    videos = list(
        bd.execute(
            select(Video.id)
            .join(Fuente, Fuente.id == Video.fuente_id)
            .where(
                Fuente.area_id == cuerpo.regla.area_id,
                Video.estado == "listo",
                Video.capture_ts_inicio >= desde,
                Video.capture_ts_inicio < hasta,
            )
        ).scalars()
    )
    entrada = cuerpo.regla
    candidata = ReglaDominio(
        id=vigente.id,
        version=vigente.version + 1,
        nombre=entrada.nombre,
        epp_exigido=frozenset(TipoEPP(e) for e in entrada.epp_exigido),
        severidad=Severidad(entrada.severidad),
        confirmacion_segundos=entrada.confirmacion_segundos,
        cierre_segundos=entrada.cierre_segundos,
        confianza_minima=entrada.confianza_minima,
    )
    estimados = [h for v in videos for h in evaluar(bd, v, [candidata])]
    actuales = (
        bd.scalar(
            select(func.count()).where(
                Hallazgo.regla_id == vigente.id, Hallazgo.video_id.in_(videos)
            )
        )
        or 0
    )
    por_severidad: dict[str, int] = {}
    for h in estimados:
        clave = str(int(h.severidad))
        por_severidad[clave] = por_severidad.get(clave, 0) + 1
    turnos = max(1, ((cuerpo.hasta - cuerpo.desde).days + 1) * 2)  # dos turnos de 12 h por día
    return {
        "hallazgos_estimados": len(estimados),
        "contra_version_vigente": {"actuales": actuales, "variacion": len(estimados) - actuales},
        "por_severidad": por_severidad,
        # Una simulación no produce recortes: los ejemplos con evidencia llegan cuando se
        # cruce lo simulado con hallazgos existentes (PT-12).
        "ejemplos": [],
        "alertas_por_turno_estimadas": round(len(estimados) / turnos, 2),
    }
