"""Reglas versionadas: cambiar una regla es insertar una fila, nunca un UPDATE de umbrales."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields, replace
from datetime import time

from gepp_core import Regla, Severidad, TipoEPP, Ventana
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gepp_bd.modelos import BASES_LICITUD, Area, Faena, Fuente, Zona
from gepp_bd.modelos import Regla as FilaRegla
from gepp_bd.turnos import turno


@dataclass(frozen=True, slots=True)
class DefinicionRegla:
    """Lo que define una regla. Todos los umbrales en SEGUNDOS (ADR-005)."""

    area_id: int
    nombre: str
    epp_exigido: frozenset[TipoEPP]
    severidad: Severidad
    base_licitud: str
    finalidad_declarada: str
    norma_fundante: str | None = None
    zona_id: int | None = None
    confirmacion_segundos: float = 2.0
    cierre_segundos: float = 3.0
    confianza_minima: float = 0.45
    turno: str | None = None
    hora_desde: time | None = None
    hora_hasta: time | None = None
    retencion_dias: int = 30
    creada_por: int | None = None

    def __post_init__(self) -> None:
        if not self.epp_exigido:
            raise ValueError("una regla exige al menos un EPP")
        if self.base_licitud not in BASES_LICITUD:
            raise ValueError(f"base_licitud inválida: {self.base_licitud!r}")


def _valores(defn: DefinicionRegla) -> dict[str, object]:
    valores = {f.name: getattr(defn, f.name) for f in fields(defn)}
    valores["epp_exigido"] = sorted(e.value for e in defn.epp_exigido)
    valores["severidad"] = int(defn.severidad)
    return valores


def crear(sesion: Session, defn: DefinicionRegla) -> FilaRegla:
    fila = FilaRegla(version=1, **_valores(defn))
    sesion.add(fila)
    sesion.flush()
    return fila


def fila_sin_guardar(defn: DefinicionRegla, *, id: int, version: int) -> FilaRegla:
    """Una fila transitoria, NO agregada a la sesión: el simulador la evalúa por el mismo
    camino que las reglas guardadas, sin escribir nada."""
    return FilaRegla(id=id, version=version, **_valores(defn))


def definicion_de(fila: FilaRegla) -> DefinicionRegla:
    return DefinicionRegla(
        area_id=fila.area_id,
        nombre=fila.nombre,
        epp_exigido=frozenset(TipoEPP(e) for e in fila.epp_exigido),
        severidad=Severidad(fila.severidad),
        base_licitud=fila.base_licitud,
        finalidad_declarada=fila.finalidad_declarada,
        norma_fundante=fila.norma_fundante,
        zona_id=fila.zona_id,
        confirmacion_segundos=fila.confirmacion_segundos,
        cierre_segundos=fila.cierre_segundos,
        confianza_minima=fila.confianza_minima,
        turno=fila.turno,
        hora_desde=fila.hora_desde,
        hora_hasta=fila.hora_hasta,
        retencion_dias=fila.retencion_dias,
        creada_por=fila.creada_por,
    )


def nueva_version(sesion: Session, regla_id: int, **cambios: object) -> FilaRegla:
    """Crea la versión siguiente con los cambios y desactiva la anterior.

    El nombre no se puede cambiar: es lo que une las versiones de una misma regla. Los
    hallazgos viejos siguen apuntando a su versión, con los umbrales con que se dispararon.
    """
    if "nombre" in cambios or "area_id" in cambios:
        raise ValueError("nombre y área identifican a la regla: crea una regla nueva")
    actual = sesion.get(FilaRegla, regla_id, with_for_update=True)
    if actual is None:
        raise LookupError(f"no existe la regla {regla_id}")
    if not actual.activa:
        raise ValueError(f"la regla {regla_id} ya fue reemplazada: versiona la vigente")
    defn = replace(definicion_de(actual), **cambios)  # type: ignore[arg-type]
    sesion.execute(update(FilaRegla).where(FilaRegla.id == actual.id).values(activa=False))
    fila = FilaRegla(version=actual.version + 1, **_valores(defn))
    sesion.add(fila)
    sesion.flush()
    return fila


def activas(sesion: Session, area_id: int | None = None) -> list[FilaRegla]:
    consulta = select(FilaRegla).where(FilaRegla.activa.is_(True))
    if area_id is not None:
        consulta = consulta.where(FilaRegla.area_id == area_id)
    return list(sesion.execute(consulta.order_by(FilaRegla.id)).scalars())


def a_dominio(fila: FilaRegla, *, solape_zona_minimo: float = 0.50) -> Regla:
    """La fila como `gepp_core.Regla`, lista para el agregador."""
    return Regla(
        id=fila.id,
        version=fila.version,
        nombre=fila.nombre,
        epp_exigido=frozenset(TipoEPP(e) for e in fila.epp_exigido),
        severidad=Severidad(fila.severidad),
        confirmacion_segundos=fila.confirmacion_segundos,
        cierre_segundos=fila.cierre_segundos,
        confianza_minima=fila.confianza_minima,
        solape_zona_minimo=solape_zona_minimo,
    )


def _ventana(fila: FilaRegla, zona_horaria: str) -> Ventana | None:
    """El horario explícito manda sobre el turno: es más específico."""
    if fila.hora_desde is not None and fila.hora_hasta is not None:
        return Ventana(fila.hora_desde, fila.hora_hasta, zona_horaria)
    if fila.turno:
        t = turno(fila.turno)
        if t is None:
            raise ValueError(f"la regla {fila.id} usa el turno {fila.turno!r}, que no existe")
        return Ventana(t.desde, t.hasta, zona_horaria)
    return None


def epp_evaluable_en(zonas: Iterable[Zona]) -> frozenset[TipoEPP] | None:
    """Unión de lo evaluable en esas zonas. `None` si ninguna está medida (no restringe)."""
    medidas = [z.evaluable for z in zonas if z.evaluable is not None]
    if not medidas:
        return None
    return frozenset(TipoEPP(e) for lista in medidas for e in lista)


def en_fuente(sesion: Session, fila: FilaRegla, fuente: Fuente) -> Regla | None:
    """La regla tal como se aplica en UNA cámara, o `None` si ahí no se puede aplicar.

    - Con zona propia: solo en la cámara de esa zona, dentro de su polígono.
    - Sin zona: en toda cámara del área; si la cámara tiene UNA zona de interés, dentro de
      ella (con varias, en todo el cuadro: el dominio admite un polígono por regla).
    - Exige solo lo evaluable (V2, #3). Si no queda nada que la cámara resuelva, la regla no
      se aplica: **el motor nunca exige lo que la cámara no ve**.
    """
    zona_horaria = sesion.execute(
        select(Faena.zona_horaria)
        .join(Area, Area.faena_id == Faena.id)
        .where(Area.id == fuente.area_id)
    ).scalar_one()
    if fila.zona_id is not None:
        zona = sesion.get(Zona, fila.zona_id)
        if zona is None or zona.fuente_id != fuente.id:
            return None
        zonas = [zona]
    else:
        zonas = list(
            sesion.execute(
                select(Zona).where(Zona.fuente_id == fuente.id, Zona.tipo == "interes")
            ).scalars()
        )
    exigido = frozenset(TipoEPP(e) for e in fila.epp_exigido)
    evaluable = epp_evaluable_en(zonas)
    if evaluable is not None:
        exigido &= evaluable
    if not exigido:
        return None
    unica = zonas[0] if len(zonas) == 1 else None
    base = a_dominio(fila, solape_zona_minimo=unica.solape_minimo if unica else 0.50)
    return replace(
        base,
        epp_exigido=exigido,
        zona=tuple((float(x), float(y)) for x, y in unica.poligono) if unica else None,
        ventana=_ventana(fila, zona_horaria),
    )


def para_fuente(sesion: Session, fuente: Fuente) -> list[Regla]:
    """Las reglas activas del área, tal como se aplican en esta cámara."""
    salida = (en_fuente(sesion, r, fuente) for r in activas(sesion, area_id=fuente.area_id))
    return [r for r in salida if r is not None]
