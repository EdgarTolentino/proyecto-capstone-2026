"""Sesión y permisos. El frontend pinta según `permisos`, no según el rol (contrato, `/yo`)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from gepp_bd.modelos import Usuario
from sqlalchemy import select
from sqlalchemy.orm import Session

from gepp_api.errores import ErrorApi, sin_permiso

#: Quien configura no observa: el administrador NO tiene `ver_evidencia`. No existe ningún
#: permiso de descarga masiva (ver `01-modelo-de-datos.md`, "Roles y qué ve cada uno").
PERMISOS: dict[str, tuple[str, ...]] = {
    "administrador": ("ver_hallazgos", "editar_reglas", "ver_reportes", "ver_auditoria"),
    "prevencionista": (
        "ver_hallazgos",
        "triar_hallazgos",
        "ver_evidencia",
        "ver_reportes",
        "asignar_acciones",
    ),
    "supervisor": ("ver_hallazgos", "triar_hallazgos", "ver_evidencia", "asignar_acciones"),
    "auditor": ("ver_hallazgos", "ver_evidencia", "ver_reportes", "ver_auditoria"),
}


@dataclass(frozen=True, slots=True)
class SesionActual:
    id: int
    nombre: str
    rol: str
    area_id: int | None

    @property
    def permisos(self) -> tuple[str, ...]:
        return PERMISOS[self.rol]

    def exigir(self, permiso: str) -> None:
        if permiso not in self.permisos:
            raise sin_permiso(f"El rol {self.rol} no tiene el permiso {permiso}")

    def puede_ver_area(self, area_id: int) -> bool:
        """El supervisor solo ve su área."""
        return self.rol != "supervisor" or self.area_id == area_id


def sesion_bd(request: Request) -> Iterator[Session]:
    with request.app.state.fabrica() as s, s.begin():
        yield s


Bd = Annotated[Session, Depends(sesion_bd)]


def sesion_actual(request: Request, bd: Bd) -> SesionActual:
    cabecera = request.headers.get("Authorization", "")
    esquema, _, token = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise ErrorApi(401, "no_autenticado", "Falta la cabecera Authorization: Bearer <token>")
    email = request.app.state.config.tokens.get(token)
    usuario = (
        bd.execute(select(Usuario).where(Usuario.email == email, Usuario.activo.is_(True)))
        .scalars()
        .first()
        if email
        else None
    )
    if usuario is None:
        raise ErrorApi(401, "no_autenticado", "Sesión inválida o caducada")
    return SesionActual(usuario.id, usuario.nombre, usuario.rol, usuario.area_id)


Sesion = Annotated[SesionActual, Depends(sesion_actual)]
