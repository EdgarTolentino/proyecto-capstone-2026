"""Recalcular sin GPU: reglas sobre las detecciones crudas ya guardadas (ADR-004, ADR-012).

Es el mismo agregador de `gepp_core` que corre el trabajador; aquí la entrada sale de la
tabla `deteccion` en vez del detector. Por eso cambiar un umbral no obliga a volver a pasar
el video por el modelo.

Reprocesar **reemplaza** hallazgos sin duplicar ni pisar decisiones humanas:

- los ya triados (confirmado, falso positivo, duplicado, pospuesto) no se tocan;
- un `por_revisar` que coincide con uno recalculado (misma persona, regla e inicio) se
  actualiza en su lugar y conserva su evidencia;
- un `por_revisar` que la regla vigente ya no produce se elimina, salvo que tenga una acción
  correctiva;
- lo nuevo se inserta.

Reprocesar dos veces seguidas deja la base igual.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from gepp_bd.modelos import AccionCorrectiva, Fuente, Notificacion, Video
from gepp_bd.modelos import Hallazgo as FilaHallazgo
from gepp_bd.repositorios import detecciones, hallazgos, reglas
from gepp_core import Hallazgo, Regla, agregar
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class Resultado:
    insertados: int
    actualizados: int
    eliminados: int
    conservados: int


def evaluar(bd: Session, video_id: int, reglas_dominio: Sequence[Regla]) -> list[Hallazgo]:
    """Los hallazgos que producirían estas reglas sobre un video, sin escribir nada."""
    salida: list[Hallazgo] = []
    for regla in reglas_dominio:
        salida.extend(agregar(regla, detecciones.por_cuadro(bd, video_id)))
    return salida


def _clave(regla_id: int, track_id: int, ts: object) -> tuple[int, int, object]:
    return (regla_id, track_id, ts)


def recalcular_video(bd: Session, video: Video) -> Resultado:
    fuente = bd.get(Fuente, video.fuente_id)
    assert fuente is not None
    vigentes = [reglas.a_dominio(r) for r in reglas.activas(bd, area_id=fuente.area_id)]
    nuevos = evaluar(bd, video.id, vigentes)
    existentes = list(
        bd.execute(select(FilaHallazgo).where(FilaHallazgo.video_id == video.id)).scalars()
    )
    por_clave = {_clave(h.regla_id, h.track_id, h.ts_inicio): h for h in existentes}

    insertados = actualizados = conservados = 0
    vistos: set[tuple[int, int, object]] = set()
    for h in nuevos:
        clave = _clave(h.regla_id, h.track_id, h.ts_inicio)
        vistos.add(clave)
        fila = por_clave.get(clave)
        if fila is None:
            hallazgos.guardar(
                bd,
                h,
                hallazgos.Contexto(fuente_id=fuente.id, area_id=fuente.area_id, video_id=video.id),
            )
            insertados += 1
        elif fila.estado == "por_revisar":
            fila.ts_fin = h.ts_fin
            fila.cuadros_confirmados = h.cuadros_confirmados
            fila.confianza_media = h.confianza_media
            fila.epp_faltante = sorted(e.value for e in h.epp_faltante)
            fila.severidad = int(h.severidad)
            actualizados += 1
        else:
            conservados += 1

    con_accion = set(
        bd.execute(
            select(AccionCorrectiva.hallazgo_id).where(
                AccionCorrectiva.hallazgo_id.in_([h.id for h in existentes])
            )
        ).scalars()
    )
    huerfanos = [h for h in existentes if _clave(h.regla_id, h.track_id, h.ts_inicio) not in vistos]
    # Un hallazgo con acción correctiva ya tiene una decisión humana encima: tampoco se borra.
    obsoletos = [h.id for h in huerfanos if h.estado == "por_revisar" and h.id not in con_accion]
    conservados += len(huerfanos) - len(obsoletos)
    _eliminar(bd, obsoletos)
    bd.flush()
    return Resultado(insertados, actualizados, len(obsoletos), conservados)


def _eliminar(bd: Session, ids: Iterable[int]) -> None:
    lista = list(ids)
    if not lista:
        return
    # El aviso ya enviado es historia: se conserva, desligado del hallazgo que desaparece.
    bd.execute(
        update(Notificacion).where(Notificacion.hallazgo_id.in_(lista)).values(hallazgo_id=None)
    )
    bd.execute(delete(FilaHallazgo).where(FilaHallazgo.id.in_(lista)))
