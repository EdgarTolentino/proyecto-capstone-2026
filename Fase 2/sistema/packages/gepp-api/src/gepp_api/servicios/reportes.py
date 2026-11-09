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
Las filas se ordenan por el valor publicado (no por el exacto), las suprimidas al final y el
desempate por etiqueta: si no, el orden delataba el conteo.

Límite que se declara: con ventanas que SE SOLAPAN todavía se despeja un caso (franjas A = 6,
X = 1, B = 6: A+X, X+B, todo y X dan 5, 5, 15 y suprimido, y eso obliga a X = 1). El redondeo
reduce los despejes, no los elimina; la protección completa son ventanas fijas (cambia el
contrato) y queda para después de H4.
"""

from __future__ import annotations

import csv
import io
import math
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from gepp_bd.modelos import Area, Dotacion, Fuente, Hallazgo, Zona
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gepp_api.config import TURNOS
from gepp_api.errores import ErrorApi

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
    "dotacion": "turno",
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


def _por_valor_publicado(conteo: Counter[str]) -> list[tuple[str, int]]:
    """Mayor a menor por el `n` PUBLICADO (redondeado), las suprimidas al final, y por etiqueta.

    Ordenar por el conteo exacto (`most_common`) delata lo oculto: con A = 4 y B = 1, suprimidas, o
    con 7 y 6, publicados ambos como 5, invertir los conteos invertía las filas.
    """
    return sorted(
        conteo.items(),
        # Suprimida = 0 publicado: queda después de toda fila visible (>= 5).
        key=lambda kn: (-(redondear_a_multiplo(kn[1]) if kn[1] >= N_MINIMO else 0), kn[0]),
    )


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


def _turno_y_fecha(ts: datetime, tz: ZoneInfo) -> tuple[str, date]:
    """Turno de un instante y la fecha en que empezó (el B de las 01:10 es del día anterior)."""
    local = ts.astimezone(tz)
    hora = local.time()
    for t in TURNOS:
        if t.contiene(hora):
            dia = local.date()
            if t.desde > t.hasta and hora < t.hasta:
                dia -= timedelta(days=1)
            return t.codigo, dia
    return "?", local.date()


def _turnos_que_tocan(inicio: datetime, fin: datetime, tz: ZoneInfo) -> set[tuple[date, str]]:
    """(fecha de inicio, turno) de los turnos que intersectan [inicio, fin), como los eventos."""
    tocan: set[tuple[date, str]] = set()
    dia = inicio.astimezone(tz).date() - timedelta(days=1)
    ultimo = (fin - timedelta(microseconds=1)).astimezone(tz).date()
    while dia <= ultimo:
        for t in TURNOS:
            empieza = datetime.combine(dia, t.desde, tzinfo=tz)
            termina = datetime.combine(dia, t.hasta, tzinfo=tz)
            if t.desde >= t.hasta:  # cruza la medianoche
                termina += timedelta(days=1)
            if empieza < fin and termina > inicio:
                tocan.add((dia, t.codigo))
        dia += timedelta(days=1)
    return tocan


def _promedio(valores: list[int]) -> int:
    """Promedio entero, a la mitad hacia arriba (sin coma flotante)."""
    return (2 * sum(valores) + len(valores)) // (2 * len(valores))


def _dotacion_visible(dias: list[tuple[int, int, int]]) -> dict[str, Any]:
    """Total y composición de la dotación del período, TODO O NADA.

    El total es el promedio de los totales diarios exactos y se publica si CADA día tiene al menos
    N_MINIMO personas. La composición (hombres, mujeres, otro) se publica solo si en CADA día cada
    categoría es 0 o >= N_MINIMO y además su promedio publicado también lo es; si no, las tres van
    `null`. Ocultar solo lo chico con el total a la vista se despeja por diferencia (5, 4, 4 con
    total 13), y entre ventanas distintas también (un día con 2 mujeres más otro con 10 dan un
    promedio que obliga al 2): por eso no hay supresión parcial.
    """
    nulo: dict[str, Any] = {"hombres": None, "mujeres": None, "otro": None}
    if min(sum(d) for d in dias) < N_MINIMO:
        return {"total": None, **nulo, "datos_insuficientes": True}
    total = _promedio([sum(d) for d in dias])
    sumas = [sum(d[i] for d in dias) for i in range(3)]
    promedios = [_promedio([d[i] for d in dias]) for i in range(3)]
    por_dia = all(v == 0 or v >= N_MINIMO for d in dias for v in d)
    publicado = all(s == 0 or p >= N_MINIMO for s, p in zip(sumas, promedios, strict=True))
    if not (por_dia and publicado):
        return {"total": total, **nulo, "datos_insuficientes": True}
    return {
        "total": total,
        "hombres": promedios[0],
        "mujeres": promedios[1],
        "otro": promedios[2],
        "datos_insuficientes": False,
    }


def _fila_dotacion(
    etiqueta: str,
    incumplimientos: int,
    dias: list[tuple[int, int, int]],
    fuera: int,
) -> dict[str, Any]:
    """Incumplimientos por cada 100 trabajadores de la dotación (dato administrativo).

    `dias`: dotaciones diarias registradas; `fuera`: incumplimientos de días sin registro. La
    dotación del período es el promedio de los totales diarios exactos y la tasa sale del `n` que
    `celda` deja VISIBLE (con el exacto, multiplicar por el total lo devolvería). Sin tasa si algún
    día tiene menos de N_MINIMO personas o si hay incumplimientos en días sin registro.
    """
    base = celda(etiqueta, incumplimientos)
    fila: dict[str, Any] = {
        "etiqueta": etiqueta,
        "valor": None,
        "n": base["n"],
        "datos_insuficientes": True,
    }
    totales = [sum(d) for d in dias]
    if base["n"] is None:
        fila["razon"] = "n_insuficiente"
    elif not dias:
        fila["razon"] = "sin_dotacion"
    elif min(totales) < N_MINIMO:
        fila["razon"] = "dotacion_insuficiente"
    elif fuera:
        fila["razon"] = "dotacion_incompleta"
    else:
        fila["valor"] = base["n"] * 100 * len(totales) / sum(totales)
        fila["datos_insuficientes"] = False
    if dias:
        fila["dotacion"] = _dotacion_visible(dias)
    return fila


def _reporte_dotacion(
    bd: Session,
    tz: ZoneInfo,
    hallazgos: list[Hallazgo],
    inicio: datetime,
    fin: datetime,
    area_id: int | None,
) -> list[dict[str, Any]]:
    """Una fila por área y turno, con la dotación de los turnos de la ventana que la tienen."""
    tocan = _turnos_que_tocan(inicio, fin, tz)
    consulta = select(Dotacion).where(
        Dotacion.fecha >= min(f for f, _ in tocan), Dotacion.fecha <= max(f for f, _ in tocan)
    )
    if area_id is not None:
        consulta = consulta.where(Dotacion.area_id == area_id)
    registros: dict[tuple[int, str], dict[date, tuple[int, int, int]]] = {}
    for d in bd.execute(consulta).scalars():
        if (d.fecha, d.turno) not in tocan:
            continue
        registros.setdefault((d.area_id, d.turno), {})[d.fecha] = (
            d.n_hombres,
            d.n_mujeres,
            d.n_otro,
        )
    eventos: Counter[tuple[int, str, date]] = Counter()
    for h in hallazgos:
        turno, fecha = _turno_y_fecha(h.ts_inicio, tz)
        eventos[(h.area_id, turno, fecha)] += 1
    areas = dict(bd.execute(select(Area.id, Area.nombre)).all())
    filas = []
    for clave in sorted(set(registros) | {(a, t) for a, t, _ in eventos}):
        dias = registros.get(clave, {})
        propios = {f: n for (a, t, f), n in eventos.items() if (a, t) == clave}
        fuera = sum(n for f, n in propios.items() if f not in dias)
        etiqueta = f"{areas.get(clave[0], f'Área {clave[0]}')} · Turno {clave[1]}"
        filas.append(
            _fila_dotacion(etiqueta, sum(propios.values()), [dias[f] for f in sorted(dias)], fuera)
        )
    return sorted(filas, key=lambda f: f["etiqueta"])


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
    zonas = dict(bd.execute(select(Zona.id, Zona.nombre)).all())
    fuentes = dict(bd.execute(select(Fuente.id, Fuente.nombre)).all())
    dimension = segmentacion or DIMENSION_POR_DEFECTO[tipo]
    claves = _claves(dimension, tz, zonas, fuentes)

    filas: list[dict[str, Any]]
    if tipo == "dotacion":
        if segmentacion not in (None, "turno"):
            raise ErrorApi(
                422, "peticion_invalida", "La tasa por dotación se reporta por área y turno"
            )
        filas = _reporte_dotacion(bd, tz, hallazgos, inicio, fin, area_id)
    elif tipo == "mapa-calor":
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
            for k, n in _por_valor_publicado(conteo)
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
