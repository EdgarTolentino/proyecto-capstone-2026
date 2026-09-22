"""Detecciones crudas: inserción por lotes y lectura para recalcular sin GPU."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from itertools import groupby

from gepp_core import Caja, ClaseDetectada, Deteccion
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from gepp_bd.modelos import Deteccion as FilaDeteccion

#: Filas por sentencia. Un video de 30 min a 5 fps con 4 cajas por cuadro son ~36 000
#: filas; en lotes de este tamaño se insertan en pocos viajes a la base.
TAMANO_LOTE = 2000


def insertar(
    sesion: Session,
    video_id: int,
    detecciones: Iterable[Deteccion],
    *,
    modelo_version: str,
    zona_id: int | None = None,
) -> int:
    """Inserta las detecciones de un video por lotes. Devuelve cuántas escribió.

    Guarda cajas, nunca imágenes (ADR-006).
    """
    total = 0
    lote: list[dict[str, object]] = []
    for d in detecciones:
        lote.append(
            {
                "video_id": video_id,
                "cuadro_idx": d.cuadro_idx,
                "capture_ts": d.capture_ts,
                "track_id": d.track_id,
                "clase": d.clase.value,
                "confianza": d.confianza,
                "bbox": [d.caja.x1, d.caja.y1, d.caja.x2, d.caja.y2],
                "zona_id": zona_id,
                "modelo_version": modelo_version,
            }
        )
        if len(lote) >= TAMANO_LOTE:
            sesion.execute(insert(FilaDeteccion), lote)
            total += len(lote)
            lote = []
    if lote:
        sesion.execute(insert(FilaDeteccion), lote)
        total += len(lote)
    return total


def a_dominio(fila: FilaDeteccion) -> Deteccion:
    x1, y1, x2, y2 = fila.bbox
    return Deteccion(
        capture_ts=fila.capture_ts,
        cuadro_idx=fila.cuadro_idx,
        clase=ClaseDetectada(fila.clase),
        caja=Caja(x1, y1, x2, y2),
        confianza=fila.confianza,
        track_id=fila.track_id,
    )


def por_cuadro(sesion: Session, video_id: int) -> Iterator[list[Deteccion]]:
    """Las detecciones de un video agrupadas por cuadro, en orden de captura.

    Es exactamente la entrada de `gepp_core.agregar`: con esto una regla nueva se evalúa
    sobre el corpus sin volver a pasar el video por la GPU.
    """
    filas = sesion.execute(
        select(FilaDeteccion)
        .where(FilaDeteccion.video_id == video_id)
        .order_by(FilaDeteccion.cuadro_idx, FilaDeteccion.id)
    ).scalars()
    for _, grupo in groupby(filas, key=lambda f: f.cuadro_idx):
        yield [a_dominio(f) for f in grupo]
