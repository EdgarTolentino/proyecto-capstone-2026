"""Reglas versionadas: cambiar una regla es insertar una fila, nunca un UPDATE de umbrales."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from datetime import time

from gepp_core import Regla, Severidad, TipoEPP
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from gepp_bd.modelos import BASES_LICITUD
from gepp_bd.modelos import Regla as FilaRegla


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
