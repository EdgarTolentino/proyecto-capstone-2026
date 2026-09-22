"""El panel de la portada: tres bandas en una sola llamada (contrato, `GET /panel`).

La ventana por defecto son los 7 días que terminan en `now()` **de la base**: la API no lee
el reloj del proceso (ADR-005). Los días se cortan en la hora local de la faena.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from gepp_bd.modelos import Area, Deteccion, Fuente, Hallazgo, Video, Zona
from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.orm import Session

from gepp_api.auth import SesionActual
from gepp_api.servicios.cobertura import cobertura
from gepp_api.servicios.hallazgos import _condicion_turno, serializar

VENTANA_POR_DEFECTO = timedelta(days=7)
DIAS = 7
#: Inicial del día de la semana, lunes primero (etiquetas de `tendencia`).
INICIALES = ("L", "M", "M", "J", "V", "S", "D")
SIN_DATOS = "sin datos"


@dataclass(frozen=True, slots=True)
class Ventana:
    desde: datetime
    hasta: datetime

    @property
    def anterior(self) -> Ventana:
        largo = self.hasta - self.desde
        return Ventana(self.desde - largo, self.desde)


def ventana(bd: Session, desde: datetime | None, hasta: datetime | None) -> Ventana:
    fin = hasta or bd.scalar(select(func.now()))
    assert fin is not None
    return Ventana(desde or fin - VENTANA_POR_DEFECTO, fin)


def dias_locales(hasta: datetime, tz: ZoneInfo, n: int = DIAS) -> list[date]:
    ultimo = hasta.astimezone(tz).date()
    return [ultimo - timedelta(days=n - 1 - i) for i in range(n)]


def _alcance(
    consulta: Select[Any],
    sesion: SesionActual,
    tz: ZoneInfo,
    turno: str | None,
    obra_id: int | None,
) -> Select[Any]:
    """Filtros comunes sobre `Hallazgo`: área del supervisor, obra y turno."""
    if sesion.rol == "supervisor":
        consulta = consulta.where(Hallazgo.area_id == sesion.area_id)
    if obra_id is not None:
        consulta = consulta.where(
            Hallazgo.area_id.in_(select(Area.id).where(Area.faena_id == obra_id))
        )
    if turno:
        consulta = consulta.where(_condicion_turno(turno, tz))
    return consulta


def _hallazgos(
    bd: Session, v: Ventana, sesion: SesionActual, tz: ZoneInfo, turno: str | None, obra: int | None
) -> list[Hallazgo]:
    consulta = select(Hallazgo).where(Hallazgo.ts_inicio >= v.desde, Hallazgo.ts_inicio < v.hasta)
    return list(bd.execute(_alcance(consulta, sesion, tz, turno, obra)).scalars())


def _variacion(actual: float, previo: float) -> float | None:
    return round((actual - previo) / previo, 2) if previo else None


def _serie_diaria(hallazgos: list[Hallazgo], dias: list[date], tz: ZoneInfo) -> list[float]:
    por_dia = Counter(h.ts_inicio.astimezone(tz).date() for h in hallazgos)
    return [float(por_dia.get(d, 0)) for d in dias]


def _cumplimiento(bd: Session, v: Ventana, sesion: SesionActual, obra: int | None) -> float | None:
    """100 x (1 - personas con hallazgo / personas observadas). Persona = (video, track)."""
    personas = (
        select(Deteccion.video_id, Deteccion.track_id)
        .join(Video, Video.id == Deteccion.video_id)
        .join(Fuente, Fuente.id == Video.fuente_id)
        .where(
            Deteccion.clase == "persona",
            Deteccion.track_id.is_not(None),
            Deteccion.capture_ts >= v.desde,
            Deteccion.capture_ts < v.hasta,
        )
        .distinct()
    )
    if sesion.rol == "supervisor":
        personas = personas.where(Fuente.area_id == sesion.area_id)
    if obra is not None:
        personas = personas.where(Fuente.area_id.in_(select(Area.id).where(Area.faena_id == obra)))
    sub = personas.subquery()
    observadas = bd.scalar(select(func.count()).select_from(sub)) or 0
    if observadas == 0:
        return None
    con_hallazgo = (
        bd.scalar(
            select(func.count()).select_from(
                select(Hallazgo.video_id, Hallazgo.track_id)
                .where(
                    tuple_(Hallazgo.video_id, Hallazgo.track_id).in_(
                        select(sub.c.video_id, sub.c.track_id)
                    ),
                    Hallazgo.ts_inicio >= v.desde,
                    Hallazgo.ts_inicio < v.hasta,
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )
    return round(100.0 * (1 - con_hallazgo / observadas), 1)


def _nombre_zona(bd: Session, hallazgos: list[Hallazgo]) -> str:
    if not hallazgos:
        return SIN_DATOS
    conteo = Counter(
        ("zona", h.zona_id) if h.zona_id else ("fuente", h.fuente_id) for h in hallazgos
    )
    (tipo, id_), _ = conteo.most_common(1)[0]
    modelo = Zona if tipo == "zona" else Fuente
    return bd.scalar(select(modelo.nombre).where(modelo.id == id_)) or SIN_DATOS


def _videos_por_dia(bd: Session, dias: list[date], tz: ZoneInfo) -> Counter[date]:
    """Videos `listo` por día LOCAL de la faena."""
    local = func.date(func.timezone(str(tz), Video.creado_en))
    filas = bd.execute(
        select(local, func.count())
        .where(Video.estado == "listo", local >= dias[0], local <= dias[-1])
        .group_by(local)
    ).all()
    return Counter({d: n for d, n in filas})


def panel(
    bd: Session,
    sesion: SesionActual,
    tz: ZoneInfo,
    *,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    turno: str | None = None,
    obra_id: int | None = None,
) -> dict[str, Any]:
    v = ventana(bd, desde, hasta)
    actuales = _hallazgos(bd, v, sesion, tz, turno, obra_id)
    previos = _hallazgos(bd, v.anterior, sesion, tz, turno, obra_id)
    dias = dias_locales(v.hasta, tz)

    abiertos = [h for h in actuales if h.estado == "por_revisar"]
    abiertos_prev = [h for h in previos if h.estado == "por_revisar"]
    criticos = [h for h in abiertos if h.severidad == 4]
    criticos_prev = [h for h in abiertos_prev if h.severidad == 4]
    cumplimiento = _cumplimiento(bd, v, sesion, obra_id)
    cumplimiento_prev = _cumplimiento(bd, v.anterior, sesion, obra_id)
    # "Hoy" es el día local de la faena según el reloj de la BASE, aunque la ventana sea otra.
    hoy = bd.scalar(select(func.date(func.timezone(str(tz), func.now()))))
    videos = _videos_por_dia(bd, dias, tz)
    videos_hoy = _videos_por_dia(bd, [hoy], tz).get(hoy, 0) if hoy is not None else 0

    indicadores = [
        {
            "clave": "hallazgos_abiertos",
            "etiqueta": "Hallazgos abiertos",
            "valor": len(abiertos),
            "unidad": None,
            "variacion": _variacion(len(abiertos), len(abiertos_prev)),
            "serie": _serie_diaria(abiertos, dias, tz),
        },
        {
            "clave": "criticos_sin_revisar",
            "etiqueta": "Críticos sin revisar",
            "valor": len(criticos),
            "unidad": None,
            "variacion": _variacion(len(criticos), len(criticos_prev)),
            "serie": _serie_diaria(criticos, dias, tz),
        },
        {
            "clave": "cumplimiento_epp",
            "etiqueta": "Cumplimiento de EPP",
            "valor": cumplimiento if cumplimiento is not None else SIN_DATOS,
            "unidad": "%" if cumplimiento is not None else None,
            "variacion": (
                _variacion(cumplimiento, cumplimiento_prev)
                if cumplimiento is not None and cumplimiento_prev is not None
                else None
            ),
            "serie": [],
        },
        {
            "clave": "zona_mas_incumplimientos",
            "etiqueta": "Zona con más incumplimientos",
            "valor": _nombre_zona(bd, actuales),
            "unidad": None,
            "variacion": None,
            "serie": [],
        },
        {
            "clave": "videos_procesados_hoy",
            "etiqueta": "Videos procesados hoy",
            "valor": videos_hoy,
            "unidad": None,
            "variacion": None,
            "serie": [float(videos.get(d, 0)) for d in dias],
        },
    ]

    por_dia_sev = Counter((h.ts_inicio.astimezone(tz).date(), h.severidad) for h in actuales)
    tendencia = {
        "etiquetas": [INICIALES[d.weekday()] for d in dias],
        "series": [
            {"severidad": s, "valores": [float(por_dia_sev.get((d, s), 0)) for d in dias]}
            for s in (4, 3, 2, 1)
        ],
    }

    epp = Counter(e for h in actuales for e in h.epp_faltante)
    top = epp.most_common(5)
    ranking = [{"epp": e, "total": n} for e, n in top]
    otros = sum(epp.values()) - sum(n for _, n in top)
    if otros:
        ranking.append({"epp": "otros", "total": otros})

    criticos_recientes = sorted(
        (h for h in actuales if h.severidad == 4), key=lambda h: h.ts_inicio, reverse=True
    )[:8]
    return {
        "indicadores": indicadores,
        "tendencia": tendencia,
        "ranking_epp": ranking,
        "criticos_recientes": serializar(bd, criticos_recientes, {}, tz),
        "cobertura": cobertura(bd, tz),
    }
