"""Reportes agregados con **supresión en el servidor** (contrato, `GET /reportes/{tipo}`).

Una celda con población n < `N_MINIMO` se devuelve sin valor y con `datos_insuficientes`.
Se oculta también `n`: publicar "n = 2" ya dice que hubo dos casos en ese cruce, que es
justo lo que la supresión protege (con una dotación femenina de ~15 %, una celda chica
reidentifica a la trabajadora; `01-modelo-de-datos.md`, `dotacion`). El frontend no puede
saltársela porque el dato nunca sale del servidor.

Los `n` (y el `valor`, y la `serie` semanal) de una celda visible salen **redondeados al
múltiplo de 5 más cercano** (#140): `GET /reportes/{tipo}` acepta cualquier `desde`/`hasta`, y
restando las respuestas de dos ventanas se despejaba una celda chica (5 casos en una semana y 1 en
la siguiente daban 5 y 6; la resta delataba el 1). Con el redondeo, 5 y 6 salen ambos como 5.
"""

from __future__ import annotations

import csv
import io
import math
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
#: Los `n` visibles se redondean a múltiplos de este valor (#140). Igual a `N_MINIMO` a propósito:
#: una celda visible (n >= 5) nunca se redondea a 0.
MULTIPLO = 5
VENTANA_POR_DEFECTO = timedelta(days=30)
SEMANAS_SERIE = 8

DIMENSION_POR_DEFECTO: dict[str, str | None] = {
    "ranking-epp": "epp",
    "zonas": "zona",
    "mapa-calor": "zona",
    "tendencia": None,
}


def redondear_a_multiplo(x: float) -> int:
    """El múltiplo de `MULTIPLO` más cercano a `x`; un empate (x = 7,5) sube: 10, no 5.

    Con enteros no hay empate (7 → 5, 8 → 10). No se usa `round`: Python redondea el empate al par
    (`round(2.5)` = 2, `round(3.5)` = 4): 7,5 y 12,5 darían 10 y 10, no 10 y 15.
    Un `x` negativo, NaN o infinito es un error de quien llama: no se corrige en silencio.
    """
    if not math.isfinite(x) or x < 0:
        raise ValueError(f"no se puede redondear un conteo de {x!r}")
    return math.floor(x / MULTIPLO + 0.5) * MULTIPLO


def celda(etiqueta: str, n: int, serie: list[float] | None = None) -> dict[str, Any]:
    """Una fila del reporte: suprimida si n < N_MINIMO; si no, `n`, `valor` y `serie` redondeados.

    La supresión y la regla de la serie miran el `n` y las semanas EXACTOS; solo lo que sale
    se redondea (#140).
    """
    if n < N_MINIMO:
        return {"etiqueta": etiqueta, "valor": None, "n": None, "datos_insuficientes": True}
    visible = redondear_a_multiplo(n)
    fila: dict[str, Any] = {
        "etiqueta": etiqueta,
        "valor": float(visible),
        "n": visible,
        "datos_insuficientes": False,
    }
    # Cada semana es una celda: una de 1 a 4 casos no se muestra, y como el total va visible
    # tampoco basta con ocultar solo esa semana (se despeja por diferencia). Va la serie entera
    # o no va. El contrato la declara opcional.
    if serie is not None and all(v == 0 or v >= N_MINIMO for v in serie):
        fila["serie"] = [float(redondear_a_multiplo(v)) for v in serie]
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
