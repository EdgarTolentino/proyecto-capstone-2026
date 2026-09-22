"""Reportes agregados con **supresión en el servidor** (contrato, `GET /reportes/{tipo}`).

Una celda con población n < `N_MINIMO` se devuelve sin valor y con `datos_insuficientes`.
Se oculta también `n`: publicar "n = 2" ya dice que hubo dos casos en ese cruce, que es
justo lo que la supresión protege (con una dotación femenina de ~15 %, una celda chica
reidentifica a la trabajadora; `01-modelo-de-datos.md`, `dotacion`). El frontend no puede
saltársela porque el dato nunca sale del servidor.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from gepp_bd.modelos import Fuente, Hallazgo, Zona
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gepp_api.config import TURNOS

#: Población mínima de una celda para mostrar su valor.
N_MINIMO = 5
VENTANA_POR_DEFECTO = timedelta(days=30)
SEMANAS_SERIE = 8

DIMENSION_POR_DEFECTO: dict[str, str | None] = {
    "ranking-epp": "epp",
    "zonas": "zona",
    "mapa-calor": "zona",
    "tendencia": None,
}


def celda(etiqueta: str, n: int, serie: list[float] | None = None) -> dict[str, Any]:
    """Una fila del reporte, ya suprimida si n < N_MINIMO."""
    if n < N_MINIMO:
        return {"etiqueta": etiqueta, "valor": None, "n": None, "datos_insuficientes": True}
    fila: dict[str, Any] = {
        "etiqueta": etiqueta,
        "valor": float(n),
        "n": n,
        "datos_insuficientes": False,
    }
    if serie is not None:
        fila["serie"] = serie
    return fila


def _turno(ts: datetime, tz: ZoneInfo) -> str:
    hora = ts.astimezone(tz).time()
    return next((t.codigo for t in TURNOS if t.contiene(hora)), "?")


def _claves(
    dimension: str | None,
    tz: ZoneInfo,
    zonas: dict[int, str],
    fuentes: dict[int, str],
) -> Callable[[Hallazgo], Iterable[str]]:
    """Etiquetas de la dimensión para un hallazgo (varias si es `epp`)."""

    def camara(h: Hallazgo) -> str:
        return fuentes.get(h.fuente_id, f"Fuente {h.fuente_id}")

    def claves(h: Hallazgo) -> Iterable[str]:
        if dimension == "epp":
            return list(h.epp_faltante)
        if dimension == "zona":
            # Sin zona dibujada, el lugar es la cámara.
            return [zonas[h.zona_id] if h.zona_id in zonas else camara(h)]
        if dimension == "camara":
            return [camara(h)]
        if dimension == "turno":
            return [f"Turno {_turno(h.ts_inicio, tz)}"]
        return [""]

    return claves


def _con(prefijo: str, sufijo: str) -> str:
    return f"{prefijo} · {sufijo}" if prefijo else sufijo


def reporte(
    bd: Session,
    tipo: str,
    tz: ZoneInfo,
    *,
    segmentacion: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    area_id: int | None = None,
) -> dict[str, Any]:
    fin = hasta or bd.scalar(select(func.now()))
    assert fin is not None
    inicio = desde or fin - VENTANA_POR_DEFECTO
    inicio_serie = min(inicio, fin - timedelta(weeks=SEMANAS_SERIE))
    consulta = select(Hallazgo).where(Hallazgo.ts_inicio >= inicio_serie, Hallazgo.ts_inicio < fin)
    if area_id is not None:
        consulta = consulta.where(Hallazgo.area_id == area_id)
    todos = list(bd.execute(consulta).scalars())
    hallazgos = [h for h in todos if h.ts_inicio >= inicio]
    zonas = dict(bd.execute(select(Zona.id, Zona.nombre)).tuples().all())
    fuentes = dict(bd.execute(select(Fuente.id, Fuente.nombre)).tuples().all())
    dimension = segmentacion or DIMENSION_POR_DEFECTO[tipo]
    claves = _claves(dimension, tz, zonas, fuentes)

    filas: list[dict[str, Any]]
    if tipo == "mapa-calor":
        conteo = Counter(
            _con(k, f"{h.ts_inicio.astimezone(tz).hour:02d}h") for h in hallazgos for k in claves(h)
        )
        filas = [celda(k, n) for k, n in sorted(conteo.items())]
    elif tipo == "tendencia":
        conteo = Counter(
            _con(k, h.ts_inicio.astimezone(tz).date().isoformat())
            for h in hallazgos
            for k in claves(h)
        )
        filas = [celda(k, n) for k, n in sorted(conteo.items())]
    else:
        conteo = Counter(k for h in hallazgos for k in claves(h))
        semanal: dict[str, Counter[int]] = {}
        if tipo == "zonas":
            for h in todos:
                semana = int((fin - h.ts_inicio) / timedelta(weeks=1))
                if semana < SEMANAS_SERIE:
                    for k in claves(h):
                        semanal.setdefault(k, Counter())[SEMANAS_SERIE - 1 - semana] += 1
        filas = [
            celda(
                k,
                n,
                [float(semanal.get(k, Counter())[i]) for i in range(SEMANAS_SERIE)]
                if tipo == "zonas"
                else None,
            )
            for k, n in conteo.most_common()
        ]
    return {"tipo": tipo, "segmentacion": dimension, "filas": filas}


def a_csv(datos: dict[str, Any]) -> str:
    """La misma supresión que el JSON: una celda insuficiente sale sin valor ni n."""
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(["etiqueta", "valor", "n", "datos_insuficientes"])
    for f in datos["filas"]:
        escritor.writerow(
            [
                f["etiqueta"],
                "" if f["valor"] is None else f["valor"],
                "" if f["n"] is None else f["n"],
                "true" if f["datos_insuficientes"] else "false",
            ]
        )
    return salida.getvalue()
