"""Consultas y serialización de hallazgos (bandeja y visor).

Dos reglas del contrato viven aquí:

- Los `contadores` de las pestañas usan **los mismos filtros salvo `estado`**, para que las
  pestañas no mientan al filtrar.
- `reincidente`: la zona acumula más de un hallazgo **en la ventana consultada**. Si el
  hallazgo no tiene zona, se agrupa por cámara.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePath
from typing import Any
from zoneinfo import ZoneInfo

from gepp_bd.modelos import (
    AccionCorrectiva,
    Area,
    Deteccion,
    Evidencia,
    Fuente,
    Hallazgo,
    Regla,
    Usuario,
    Video,
    Zona,
)
from sqlalchemy import ARRAY, ColumnElement, Select, Text, and_, cast, false, func, or_, select
from sqlalchemy.orm import Session

from gepp_api.auth import SesionActual
from gepp_api.config import AVISO_LEGAL, PREFIJO, TURNOS

DESCARTADOS = ("falso_positivo", "duplicado")

ORDENES: dict[str, tuple[ColumnElement[Any], ...]] = {
    "ts_inicio_desc": (Hallazgo.ts_inicio.desc(), Hallazgo.id.desc()),
    "ts_inicio_asc": (Hallazgo.ts_inicio.asc(), Hallazgo.id.asc()),
    "severidad_desc": (Hallazgo.severidad.desc(), Hallazgo.ts_inicio.desc()),
    "duracion_desc": (Hallazgo.duracion_s.desc().nulls_last(), Hallazgo.ts_inicio.desc()),
    "confianza_desc": (Hallazgo.confianza_media.desc(), Hallazgo.ts_inicio.desc()),
}


@dataclass(frozen=True, slots=True)
class Filtros:
    estado: str | None = None
    severidad: Sequence[int] = ()
    area_id: int | None = None
    zona_id: int | None = None
    fuente_id: int | None = None
    epp: Sequence[str] = ()
    desde: datetime | None = None
    hasta: datetime | None = None
    turno: str | None = None
    reincidente: bool | None = None


def iso(ts: datetime | None, tz: ZoneInfo) -> str | None:
    """Hora de captura en la zona horaria de la faena, con su desfase explícito."""
    return ts.astimezone(tz).isoformat() if ts is not None else None


def url_evidencia(evidencia_id: int) -> str:
    return f"{PREFIJO}/evidencias/{evidencia_id}"


def cursor_de(desplazamiento: int) -> str:
    return base64.urlsafe_b64encode(f"o:{desplazamiento}".encode()).decode()


def desplazamiento_de(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        texto = base64.urlsafe_b64decode(cursor.encode()).decode()
        return max(0, int(texto.removeprefix("o:")))
    except (ValueError, UnicodeDecodeError):
        return 0


def _condicion_turno(codigo: str, tz: ZoneInfo) -> Any:
    """El turno se decide con la hora LOCAL de captura en la faena, no con la UTC."""
    turno = next((t for t in TURNOS if t.codigo == codigo), None)
    if turno is None:
        return false()
    hora = func.to_char(func.timezone(str(tz), Hallazgo.ts_inicio), "HH24:MI:SS")
    desde, hasta = turno.desde.strftime("%H:%M:%S"), turno.hasta.strftime("%H:%M:%S")
    if turno.desde <= turno.hasta:
        return and_(hora >= desde, hora < hasta)
    return or_(hora >= desde, hora < hasta)  # cruza la medianoche


def _base(filtros: Filtros, sesion: SesionActual, tz: ZoneInfo) -> Select[Any]:
    """Hallazgos con todos los filtros SALVO estado y reincidente, más la cuenta por zona."""
    clave_zona = func.coalesce(Hallazgo.zona_id, -Hallazgo.fuente_id)
    consulta = select(
        Hallazgo.id.label("id"),
        Hallazgo.estado.label("estado"),
        func.count().over(partition_by=clave_zona).label("n_zona"),
    )
    if filtros.severidad:
        consulta = consulta.where(Hallazgo.severidad.in_(list(filtros.severidad)))
    if filtros.area_id is not None:
        consulta = consulta.where(Hallazgo.area_id == filtros.area_id)
    if filtros.zona_id is not None:
        consulta = consulta.where(Hallazgo.zona_id == filtros.zona_id)
    if filtros.fuente_id is not None:
        consulta = consulta.where(Hallazgo.fuente_id == filtros.fuente_id)
    if filtros.epp:
        consulta = consulta.where(
            Hallazgo.epp_faltante.op("&&")(cast(list(filtros.epp), ARRAY(Text)))
        )
    if filtros.desde is not None:
        consulta = consulta.where(Hallazgo.ts_inicio >= filtros.desde)
    if filtros.hasta is not None:
        consulta = consulta.where(Hallazgo.ts_inicio <= filtros.hasta)
    if filtros.turno:
        consulta = consulta.where(_condicion_turno(filtros.turno, tz))
    if sesion.rol == "supervisor":
        consulta = consulta.where(Hallazgo.area_id == sesion.area_id)
    return consulta


def listar(
    bd: Session,
    filtros: Filtros,
    sesion: SesionActual,
    tz: ZoneInfo,
    *,
    orden: str = "ts_inicio_desc",
    limite: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    base = _base(filtros, sesion, tz).subquery()
    alcance = select(base)
    if filtros.reincidente is not None:
        alcance = alcance.where((base.c.n_zona > 1) == filtros.reincidente)
    alcance_sq = alcance.subquery()

    contadores = bd.execute(
        select(
            func.count().filter(alcance_sq.c.estado == "por_revisar"),
            func.count().filter(alcance_sq.c.estado == "confirmado"),
            func.count().filter(alcance_sq.c.estado.in_(DESCARTADOS)),
            func.count().filter(alcance_sq.c.n_zona > 1),
            func.count(),
        )
    ).one()

    pagina = select(Hallazgo, alcance_sq.c.n_zona).join(alcance_sq, alcance_sq.c.id == Hallazgo.id)
    if filtros.estado:
        pagina = pagina.where(Hallazgo.estado == filtros.estado)
    desplazamiento = desplazamiento_de(cursor)
    filas = bd.execute(
        pagina.order_by(*ORDENES.get(orden, ORDENES["ts_inicio_desc"]))
        .offset(desplazamiento)
        .limit(limite + 1)
    ).all()
    hay_mas = len(filas) > limite
    filas = filas[:limite]
    items = serializar(bd, [f[0] for f in filas], {f[0].id: f[1] > 1 for f in filas}, tz)
    return {
        "items": items,
        "contadores": {
            "por_revisar": contadores[0],
            "confirmado": contadores[1],
            "descartado": contadores[2],
            "reincidente": contadores[3],
            "todos": contadores[4],
        },
        "siguiente_cursor": cursor_de(desplazamiento + limite) if hay_mas else None,
    }


def _referencias(bd: Session, modelo: Any, ids: set[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    filas = bd.execute(select(modelo.id, modelo.nombre).where(modelo.id.in_(ids))).all()
    return {f.id: {"id": f.id, "nombre": f.nombre} for f in filas}


def serializar(
    bd: Session, hallazgos: Sequence[Hallazgo], reincidentes: dict[int, bool], tz: ZoneInfo
) -> list[dict[str, Any]]:
    """Hallazgos al esquema `Hallazgo`: cinco consultas en total, no una por fila."""
    areas = _referencias(bd, Area, {h.area_id for h in hallazgos})
    zonas = _referencias(bd, Zona, {h.zona_id for h in hallazgos if h.zona_id})
    fuentes = _referencias(bd, Fuente, {h.fuente_id for h in hallazgos})
    usuarios = _referencias(bd, Usuario, {h.revisado_por for h in hallazgos if h.revisado_por})
    ids = [h.id for h in hallazgos]
    primera_evidencia = dict(
        bd.execute(
            select(Evidencia.hallazgo_id, func.min(Evidencia.id))
            .where(Evidencia.hallazgo_id.in_(ids))
            .group_by(Evidencia.hallazgo_id)
        )
        .tuples()
        .all()
    )
    salida = []
    for h in hallazgos:
        evidencia = primera_evidencia.get(h.id)
        salida.append(
            {
                "id": h.id,
                "area": areas.get(h.area_id),
                "zona": zonas.get(h.zona_id) if h.zona_id else None,
                "fuente": fuentes.get(h.fuente_id),
                "epp_faltante": list(h.epp_faltante),
                "severidad": h.severidad,
                "ts_inicio": iso(h.ts_inicio, tz),
                "ts_fin": iso(h.ts_fin, tz),
                "duracion_s": round(h.duracion_s or 0.0, 1),
                "cuadros_confirmados": h.cuadros_confirmados,
                "confianza_media": round(h.confianza_media, 2),
                "estado": h.estado,
                "miniatura_url": url_evidencia(evidencia) if evidencia else None,
                "asignado_a": usuarios.get(h.revisado_por) if h.revisado_por else None,
                "reincidente": reincidentes.get(h.id, False),
                "aviso_legal": AVISO_LEGAL,
            }
        )
    return salida


def _es_reincidente(bd: Session, h: Hallazgo) -> bool:
    """En el visor no hay ventana consultada: se mira todo el histórico de la zona."""
    if h.zona_id is not None:
        condicion = Hallazgo.zona_id == h.zona_id
    else:
        condicion = and_(Hallazgo.zona_id.is_(None), Hallazgo.fuente_id == h.fuente_id)
    return (bd.scalar(select(func.count()).where(condicion)) or 0) > 1


def _segundos(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + " s"


def detalle(bd: Session, h: Hallazgo, sesion: SesionActual, tz: ZoneInfo) -> dict[str, Any]:
    (base,) = serializar(bd, [h], {h.id: _es_reincidente(bd, h)}, tz)
    regla = bd.get(Regla, h.regla_id)
    video = bd.get(Video, h.video_id) if h.video_id else None
    fuente = bd.get(Fuente, h.fuente_id)
    zona = bd.get(Zona, h.zona_id) if h.zona_id else None
    evidencias = (
        list(
            bd.execute(
                select(Evidencia).where(Evidencia.hallazgo_id == h.id).order_by(Evidencia.id)
            ).scalars()
        )
        if "ver_evidencia" in sesion.permisos
        else []
    )
    modelo = (
        bd.scalar(select(Deteccion.modelo_version).where(Deteccion.video_id == h.video_id).limit(1))
        if h.video_id
        else None
    )
    acciones = bd.execute(
        select(AccionCorrectiva)
        .where(AccionCorrectiva.hallazgo_id == h.id)
        .order_by(AccionCorrectiva.id)
    ).scalars()
    confirmacion = regla.confirmacion_segundos if regla else 0.0
    umbral = h.ts_inicio if regla is None else h.ts_inicio + timedelta(seconds=confirmacion)
    base.update(
        {
            "recorte_video_url": None,
            "evidencias": [evidencia_a_json(e, tz) for e in evidencias],
            "linea_tiempo": {
                "primera_deteccion": iso(h.ts_inicio, tz),
                "umbral_alcanzado": iso(umbral, tz),
                "fin": iso(h.ts_fin, tz),
            },
            "descripcion_automatica": (
                {
                    "titulo": h.vlm_titulo,
                    "descripcion": h.vlm_descripcion,
                    "confianza": h.vlm_confianza,
                    "modelo": h.vlm_modelo,
                }
                if h.vlm_titulo
                else None
            ),
            "por_que_se_disparo": {
                "regla_id": h.regla_id,
                "regla_nombre": regla.nombre if regla else "",
                "regla_version": h.regla_version,
                "zona": zona.nombre if zona else (fuente.nombre if fuente else ""),
                "epp_exigido": sorted(regla.epp_exigido) if regla else [],
                "umbral_configurado": f"Incumplimiento sostenido durante {_segundos(confirmacion)}",
                "valores_observados": (
                    f"{h.cuadros_confirmados} cuadros en {_segundos(h.duracion_s or 0.0)}"
                ),
                "confianza_minima": regla.confianza_minima if regla else None,
                "base_licitud": regla.base_licitud if regla else None,
                "norma_fundante": regla.norma_fundante if regla else None,
            },
            "tecnicos": {
                "video_archivo": PurePath(video.ruta).name if video else None,
                "video_hash": f"{video.hash_sha256[:8]}…{video.hash_sha256[-4:]}"
                if video
                else None,
                "segundo_en_video": round(
                    (h.ts_inicio - video.capture_ts_inicio).total_seconds(), 1
                )
                if video
                else None,
                "fps_muestreo": fuente.fps_objetivo if fuente else None,
                "modelo_version": modelo,
                "track_id": h.track_id,
            },
            "acciones": [accion_a_json(a, tz) for a in acciones],
        }
    )
    # Campos opcionales que el contrato NO admite nulos: sin dato (p. ej. un hallazgo cuyo
    # video se borró), se omiten en vez de mandar null.
    for bloque in ("por_que_se_disparo", "tecnicos"):
        base[bloque] = {k: v for k, v in base[bloque].items() if v is not None}
    return base


def evidencia_a_json(e: Evidencia, tz: ZoneInfo) -> dict[str, Any]:
    return {
        "id": e.id,
        "cuadro_idx": e.cuadro_idx,
        "capture_ts": iso(e.capture_ts, tz),
        "anonimizado": True,
        "url": url_evidencia(e.id),
        "purgar_el": e.purgar_el.isoformat(),
    }


def accion_a_json(a: AccionCorrectiva, tz: ZoneInfo) -> dict[str, Any]:
    return {
        "id": a.id,
        "responsable_id": a.responsable_id,
        "descripcion": a.descripcion,
        "plazo": a.plazo.isoformat(),
        "estado": a.estado,
        "cerrada_en": iso(a.cerrada_en, tz),
        "comentario_cierre": a.comentario_cierre,
    }
