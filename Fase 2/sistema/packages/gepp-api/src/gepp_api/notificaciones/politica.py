"""Qué se avisa ya, qué espera y qué baja al resumen. Python puro: se prueba sin red ni base.

Las dos velocidades (ADR-008):

- **Grave** (severidad crítica, o incumplimiento de más de `GRAVE_DURACION_S`): aviso inmediato.
- **Corriente**: ningún aviso individual; entra al **resumen de fin de turno**.

Y la cadena de supresión que protege el presupuesto de `03-alertas.md`:

1. **Agrupación** por (destinatario, área, EPP): "3 personas sin casco" es UN mensaje.
2. **Espera global**: como máximo un aviso cada `ESPERA_GLOBAL` por destinatario (techo duro).
3. **Espera por cámara**: una cámara ya avisada hace menos de `ESPERA_POR_CAMARA` no vuelve a
   interrumpir; lo nuevo de esa cámara baja al resumen.
4. **Presupuesto**: `PRESUPUESTO_POR_TURNO` avisos por turno de 12 h. Lo que excede, al resumen.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from gepp_api.notificaciones.canal import LEYENDA, MAXIMO_CUERPO, MAXIMO_TITULO

GRAVE_SEVERIDAD = 4
GRAVE_DURACION_S = 120.0
ESPERA_GLOBAL = timedelta(minutes=10)
ESPERA_POR_CAMARA = timedelta(minutes=30)
PRESUPUESTO_POR_TURNO = 6

NOMBRE_EPP = {
    "casco": "casco",
    "chaleco": "chaleco",
    "lentes": "lentes",
    "guantes": "guantes",
    "arnes": "arnés",
    "calzado": "calzado de seguridad",
}


@dataclass(frozen=True, slots=True)
class Pendiente:
    """Una notificación inmediata pendiente, con lo necesario del hallazgo para decidir."""

    id: int
    destinatario: str
    canal: str
    area: str
    fuente_id: int
    epp: tuple[str, ...]
    severidad: int
    duracion_s: float
    ts_inicio: datetime
    ts_fin: datetime | None


def es_grave(p: Pendiente) -> bool:
    return p.severidad >= GRAVE_SEVERIDAD or p.duracion_s > GRAVE_DURACION_S


@dataclass(slots=True)
class Grupo:
    destinatario: str
    canal: str
    area: str
    epp: tuple[str, ...]
    items: list[Pendiente] = field(default_factory=list)

    @property
    def fuentes(self) -> set[int]:
        return {p.fuente_id for p in self.items}


def agrupar(pendientes: Iterable[Pendiente]) -> list[Grupo]:
    grupos: dict[tuple[str, str, str, tuple[str, ...]], Grupo] = {}
    for p in sorted(pendientes, key=lambda x: (x.ts_inicio, x.id)):
        clave = (p.destinatario, p.canal, p.area, p.epp)
        grupos.setdefault(clave, Grupo(p.destinatario, p.canal, p.area, p.epp)).items.append(p)
    # Lo más severo primero: si el presupuesto no alcanza, que alcance para lo crítico.
    return sorted(
        grupos.values(), key=lambda g: (-max(p.severidad for p in g.items), g.items[0].ts_inicio)
    )


class Decision(StrEnum):
    ENVIAR = "enviar"
    ESPERAR = "esperar"
    AL_RESUMEN = "al_resumen"


@dataclass(slots=True)
class Historial:
    """Lo ya enviado en el turno en curso, por destinatario."""

    enviados_en_turno: dict[str, int] = field(default_factory=dict)
    ultimo_envio: dict[str, datetime] = field(default_factory=dict)
    ultimo_por_camara: dict[tuple[str, int], datetime] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Veredicto:
    grupo: Grupo
    decision: Decision
    motivo: str


def decidir(grupos: Sequence[Grupo], historial: Historial, ahora: datetime) -> list[Veredicto]:
    """Aplica espera por cámara, presupuesto y espera global, en ese orden, grupo a grupo.

    Actualiza `historial` con lo que decide enviar, para que dos grupos del mismo destinatario
    en la misma pasada no se salten la espera global.
    """
    veredictos = []
    for g in grupos:
        d = g.destinatario
        recientes = [
            f
            for f in g.fuentes
            if (u := historial.ultimo_por_camara.get((d, f))) and ahora - u < ESPERA_POR_CAMARA
        ]
        if recientes and len(recientes) == len(g.fuentes):
            veredictos.append(Veredicto(g, Decision.AL_RESUMEN, "espera_por_camara"))
            continue
        if historial.enviados_en_turno.get(d, 0) >= PRESUPUESTO_POR_TURNO:
            veredictos.append(Veredicto(g, Decision.AL_RESUMEN, "presupuesto_agotado"))
            continue
        ultimo = historial.ultimo_envio.get(d)
        if ultimo is not None and ahora - ultimo < ESPERA_GLOBAL:
            veredictos.append(Veredicto(g, Decision.ESPERAR, "espera_global"))
            continue
        veredictos.append(Veredicto(g, Decision.ENVIAR, "grave"))
        historial.enviados_en_turno[d] = historial.enviados_en_turno.get(d, 0) + 1
        historial.ultimo_envio[d] = ahora
        for f in g.fuentes:
            historial.ultimo_por_camara[(d, f)] = ahora
    return veredictos


def _epp_texto(epp: Sequence[str]) -> str:
    nombres = [NOMBRE_EPP.get(e, e) for e in epp]
    return (
        " ni ".join(nombres)
        if len(nombres) <= 2
        else ", ".join(nombres[:-1]) + " ni " + nombres[-1]
    )


def _hora(ts: datetime, tz: ZoneInfo) -> str:
    return ts.astimezone(tz).strftime("%H:%M")


def texto_inmediato(g: Grupo, turno: str, tz: ZoneInfo) -> tuple[str, str]:
    """Al área y al turno, nunca a la persona: "3 personas sin casco", no quiénes."""
    n = len(g.items)
    personas = "1 persona" if n == 1 else f"{n} personas"
    desde = min(p.ts_inicio for p in g.items)
    hasta = max(p.ts_fin or p.ts_inicio for p in g.items)
    titulo = f"{g.area} · turno {turno}"[:MAXIMO_TITULO]
    cuerpo = (
        f"{personas} sin {_epp_texto(g.epp)} entre {_hora(desde, tz)} y {_hora(hasta, tz)}.\n"
        f"{LEYENDA}"
    )
    return titulo, cuerpo[:MAXIMO_CUERPO]


def texto_resumen(filas: Sequence[tuple[str, tuple[str, ...]]], turno: str) -> tuple[str, str]:
    """Resumen de fin de turno: conteos por área y EPP, sin horas ni personas."""
    conteo: dict[tuple[str, tuple[str, ...]], int] = {}
    for area, epp in filas:
        conteo[(area, epp)] = conteo.get((area, epp), 0) + 1
    lineas = [
        f"• {area}: {n} sin {_epp_texto(epp)}"
        for (area, epp), n in sorted(conteo.items(), key=lambda x: -x[1])
    ]
    titulo = f"Resumen del turno {turno}"[:MAXIMO_TITULO]
    cuerpo = "\n".join([f"{len(filas)} incumplimientos de EPP corriente:", *lineas, LEYENDA])
    if len(cuerpo) > MAXIMO_CUERPO:
        cuerpo = cuerpo[: MAXIMO_CUERPO - len(LEYENDA) - 2] + "…\n" + LEYENDA
    return titulo, cuerpo
