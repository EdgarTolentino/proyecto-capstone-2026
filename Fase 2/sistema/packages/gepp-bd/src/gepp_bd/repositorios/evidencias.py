"""Evidencias: la fila que apunta al recorte anonimizado en disco."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from gepp_bd.modelos import Evidencia


def insertar(
    sesion: Session,
    *,
    hallazgo_id: int,
    ruta: str,
    hash_sha256: str,
    cuadro_idx: int,
    capture_ts: datetime,
    purgar_el: date,
) -> Evidencia:
    """Registra un recorte. Siempre `anonimizado = true`: no existe otra versión en disco."""
    if capture_ts.tzinfo is None:
        raise ValueError("capture_ts debe llevar zona horaria (ver ADR-005)")
    fila = Evidencia(
        hallazgo_id=hallazgo_id,
        ruta=ruta,
        hash_sha256=hash_sha256,
        cuadro_idx=cuadro_idx,
        capture_ts=capture_ts,
        anonimizado=True,
        purgar_el=purgar_el,
    )
    sesion.add(fila)
    sesion.flush()
    return fila
