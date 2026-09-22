"""Auditoría append-only. Este módulo solo sabe insertar; la base impide lo demás."""

from __future__ import annotations

from sqlalchemy.orm import Session

from gepp_bd.modelos import Auditoria


def registrar(
    sesion: Session,
    *,
    rol: str,
    accion: str,
    entidad: str,
    entidad_id: int | None = None,
    usuario_id: int | None = None,
    motivo: str | None = None,
    ip: str | None = None,
) -> Auditoria:
    fila = Auditoria(
        usuario_id=usuario_id,
        rol=rol,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        motivo=motivo,
        ip=ip,
    )
    sesion.add(fila)
    sesion.flush()
    return fila
